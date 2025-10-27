"""
异步工具服务 - 纯服务层

提供批量工具执行的核心业务逻辑，支持：
- 批量并发执行
- 智能缓存（LRU + TTL）
- 完整日志追踪
- 连接管理
- 性能监控
"""

import asyncio
import hashlib
import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .async_tool_config import AsyncToolServerConfig
from .async_tool_manager import AsyncToolManager
from ...db.session import SessionLocal

logger = logging.getLogger(__name__)

# 全局配置和管理器实例
_config = AsyncToolServerConfig()
_manager: Optional[AsyncToolManager] = None
_semaphore: Optional[asyncio.Semaphore] = None

# LRU 缓存（带 TTL）
class CacheEntry:
    """缓存条目，包含数据和过期时间"""
    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.expires_at = time.time() + ttl
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

# 使用 LRU 缓存替代 WeakValueDictionary
@lru_cache(maxsize=None)
def _get_cache():
    """获取缓存实例（延迟初始化）"""
    return {}

def _get_from_cache(key: str) -> Optional[Any]:
    """从缓存获取数据"""
    cache = _get_cache()
    entry = cache.get(key)
    if entry and not entry.is_expired():
        return entry.data
    elif entry:
        # 清理过期条目
        cache.pop(key, None)
    return None

def _set_to_cache(key: str, data: Any):
    """设置缓存数据"""
    if not _config.hash_requests:
        return
    
    cache = _get_cache()
    
    # 清理过期条目（简单策略）
    if len(cache) > _config.cache_max_size:
        expired_keys = [k for k, v in cache.items() if v.is_expired()]
        for k in expired_keys:
            cache.pop(k, None)
        
        # 如果还是太多，清理最老的条目
        if len(cache) > _config.cache_max_size:
            oldest_keys = sorted(cache.keys())[:len(cache) - _config.cache_max_size + 100]
            for k in oldest_keys:
                cache.pop(k, None)
    
    cache[key] = CacheEntry(data, _config.cache_ttl)


class ActionRequest(BaseModel):
    """批量动作请求体"""
    trajectory_ids: List[str] = Field(..., description="轨迹ID列表")
    actions: List[str] = Field(..., description="动作字符串列表")
    extra_fields: List[Dict[str, Any]] = Field(default_factory=list, description="额外字段列表")
    user_id: Optional[str] = Field(None, description="用户ID（用于连接管理）")
    trace_id: Optional[str] = Field(None, description="追踪ID（用于日志）")


class AgentResponse(BaseModel):
    """批量动作响应体"""
    observations: List[Any] = Field(..., description="观察结果列表")
    dones: List[bool] = Field(..., description="完成状态列表")
    valids: List[bool] = Field(..., description="有效性状态列表")
    trace_id: str = Field(..., description="追踪ID")
    processing_time_ms: float = Field(..., description="处理时间（毫秒）")


class AsyncToolsService:
    """异步工具服务类 - 处理批量工具执行的核心业务逻辑"""
    
    def __init__(self, db: Session):
        self.db = db
        self._ensure_manager_and_semaphore()
    
    def _ensure_manager_and_semaphore(self):
        """确保管理器和信号量已初始化"""
        global _manager, _semaphore
        
        if _manager is None:
            _manager = AsyncToolManager(_config, self.db)
        
        if _semaphore is None:
            _semaphore = asyncio.Semaphore(_config.max_concurrent_requests)
    
    def _hash_req(self, req: ActionRequest) -> str:
        """生成请求哈希（用于缓存）"""
        # 创建请求的标准化表示
        normalized = {
            "actions": req.actions,
            "extra_fields": req.extra_fields,
            "user_id": req.user_id
        }
        
        # 生成 SHA256 哈希
        content = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def execute_batch_actions(
        self, 
        request: ActionRequest, 
        user_id: str
    ) -> Tuple[AgentResponse, Dict[str, str]]:
        """执行批量工具动作
        
        Args:
            request: 批量动作请求
            user_id: 用户ID
            
        Returns:
            Tuple[AgentResponse, Dict[str, str]]: 响应数据和响应头
        """
        start_time = time.time()
        
        # 生成或使用提供的追踪ID
        trace_id = request.trace_id or str(uuid.uuid4())
        
        logger.info(f"[{trace_id}] Received batch request: {len(request.actions)} actions")
        
        # 输入验证
        if len(request.actions) != len(request.trajectory_ids):
            raise ValueError("actions and trajectory_ids must have the same length")
        
        if request.extra_fields and len(request.extra_fields) != len(request.actions):
            raise ValueError("extra_fields must have the same length as actions")
        
        # 填充默认的 extra_fields
        if not request.extra_fields:
            request.extra_fields = [{}] * len(request.actions)
        
        # 缓存检查
        cache_key = None
        headers = {"X-Trace-ID": trace_id}
        
        if _config.hash_requests:
            cache_key = self._hash_req(request)
            cached_result = _get_from_cache(cache_key)
            if cached_result:
                logger.info(f"[{trace_id}] Cache hit for request")
                # 更新追踪ID
                cached_result["trace_id"] = trace_id
                headers["X-Cache-Status"] = "hit"
                return AgentResponse(**cached_result), headers
        
        # 获取信号量并执行批量处理
        await _semaphore.acquire()
        try:
            obs, dones, valids, returned_trace_id = await asyncio.wait_for(
                _manager.process_actions(
                    request.trajectory_ids,
                    request.actions,
                    request.extra_fields,
                    user_id,
                    trace_id
                ),
                timeout=_config.request_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"[{trace_id}] Request timeout after {_config.request_timeout}s")
            raise TimeoutError(f"Request timeout after {_config.request_timeout} seconds")
        finally:
            _semaphore.release()
        
        # 计算处理时间
        processing_time_ms = (time.time() - start_time) * 1000
        
        # 构建响应
        result = {
            "observations": obs,
            "dones": dones,
            "valids": valids,
            "trace_id": returned_trace_id,
            "processing_time_ms": processing_time_ms
        }
        
        # 缓存结果
        if cache_key:
            _set_to_cache(cache_key, result)
            headers["X-Cache-Status"] = "miss"
        
        # 设置响应头
        headers["X-Trace-ID"] = returned_trace_id
        headers["X-Processing-Time-MS"] = str(processing_time_ms)
        
        logger.info(f"[{returned_trace_id}] Request completed in {processing_time_ms:.2f}ms")
        
        return AgentResponse(**result), headers
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康检查状态"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "config": {
                "max_concurrent_requests": _config.max_concurrent_requests,
                "request_timeout": _config.request_timeout,
                "hash_requests": _config.hash_requests,
                "cache_max_size": _config.cache_max_size
            }
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        cache = _get_cache()
        
        # 统计缓存状态
        total_entries = len(cache)
        expired_entries = sum(1 for entry in cache.values() if entry.is_expired())
        active_entries = total_entries - expired_entries
        
        # 获取信号量状态
        semaphore_available = _semaphore._value if _semaphore else 0
        semaphore_total = _config.max_concurrent_requests
        
        return {
            "timestamp": time.time(),
            "concurrency": {
                "available_slots": semaphore_available,
                "total_slots": semaphore_total,
                "active_requests": semaphore_total - semaphore_available
            },
            "cache": {
                "total_entries": total_entries,
                "active_entries": active_entries,
                "expired_entries": expired_entries,
                "max_size": _config.cache_max_size,
                "enabled": _config.hash_requests
            },
            "pools": {
                "thread_pool_size": _config.resolved_pool(),
                "process_pool_size": _config.resolved_process_pool(),
                "parse_pool_size": _config.resolved_parse_pool()
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置信息"""
        return {
            "max_concurrent_requests": _config.max_concurrent_requests,
            "request_timeout": _config.request_timeout,
            "thread_pool_size": _config.resolved_pool(),
            "process_pool_size": _config.resolved_process_pool(),
            "parse_pool_size": _config.resolved_parse_pool(),
            "hash_requests": _config.hash_requests,
            "cache_max_size": _config.cache_max_size,
            "cache_ttl": _config.cache_ttl,
            "parse_chunk_size": _config.parse_chunk_size
        }