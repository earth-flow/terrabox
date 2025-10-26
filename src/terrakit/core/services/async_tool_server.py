"""
异步工具服务器 - FastAPI 路由器

提供批量工具执行的 HTTP API 接口，支持：
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
from typing import Any, Dict, List, Optional
from functools import lru_cache
from weakref import WeakValueDictionary

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from .async_tool_config import AsyncToolServerConfig
from .async_tool_manager import AsyncToolManager
from ...db.session import get_db
from ...db import models
from ...core.services import AuthService

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme for JWT
security = HTTPBearer(auto_error=False)

def current_user_flexible(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """Get current user from either API Key or JWT token"""
    # Try API key first
    if x_api_key:
        try:
            return AuthService.get_current_user_from_api_key(db, x_api_key)
        except HTTPException:
            pass  # Fall through to JWT
    
    # Try JWT token
    if credentials:
        try:
            return AuthService.get_current_user(db, credentials)
        except HTTPException:
            pass  # Fall through to error
    
    # No valid authentication found
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide either X-API-Key header or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

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


def get_manager_and_semaphore(db: Session = Depends(get_db)):
    """获取管理器和信号量（依赖注入）"""
    global _manager, _semaphore
    
    if _manager is None:
        _manager = AsyncToolManager(_config, db)
    
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_config.max_concurrent_requests)
    
    return _manager, _semaphore


async def limit(manager_and_semaphore=Depends(get_manager_and_semaphore)):
    """并发限制依赖"""
    manager, semaphore = manager_and_semaphore
    await semaphore.acquire()
    try:
        yield manager
    finally:
        semaphore.release()


def _hash_req(req: ActionRequest) -> str:
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


# 创建路由器
batch_tools_router = APIRouter(prefix="/v1/tools", tags=["batch-tools"])


@batch_tools_router.post("/get_observation", response_model=AgentResponse)
async def get_observation(
    request: ActionRequest,
    response: Response,
    current_user: models.User = Depends(current_user_flexible),
    manager: AsyncToolManager = Depends(limit)
) -> AgentResponse:
    """批量工具执行端点
    
    执行批量工具动作，支持：
    - 智能缓存（基于请求内容哈希）
    - 并发限制和超时控制
    - 完整的错误处理和日志记录
    - 追踪ID支持
    """
    start_time = time.time()
    
    # 生成或使用提供的追踪ID
    trace_id = request.trace_id or str(uuid.uuid4())
    
    logger.info(f"[{trace_id}] Received batch request: {len(request.actions)} actions")
    
    try:
        # 输入验证
        if len(request.actions) != len(request.trajectory_ids):
            raise HTTPException(
                status_code=400,
                detail="actions and trajectory_ids must have the same length"
            )
        
        if request.extra_fields and len(request.extra_fields) != len(request.actions):
            raise HTTPException(
                status_code=400,
                detail="extra_fields must have the same length as actions"
            )
        
        # 填充默认的 extra_fields
        if not request.extra_fields:
            request.extra_fields = [{}] * len(request.actions)
        
        # 缓存检查
        cache_key = None
        if _config.hash_requests:
            cache_key = _hash_req(request)
            cached_result = _get_from_cache(cache_key)
            if cached_result:
                logger.info(f"[{trace_id}] Cache hit for request")
                # 更新追踪ID
                cached_result["trace_id"] = trace_id
                response.headers["X-Trace-ID"] = trace_id
                response.headers["X-Cache-Status"] = "hit"
                return AgentResponse(**cached_result)
        
        # 执行批量处理
        try:
            obs, dones, valids, returned_trace_id = await asyncio.wait_for(
                manager.process_actions(
                    request.trajectory_ids,
                    request.actions,
                    request.extra_fields,
                    current_user.id,
                    trace_id
                ),
                timeout=_config.request_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"[{trace_id}] Request timeout after {_config.request_timeout}s")
            raise HTTPException(
                status_code=408,
                detail=f"Request timeout after {_config.request_timeout} seconds"
            )
        
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
            response.headers["X-Cache-Status"] = "miss"
        
        # 设置响应头
        response.headers["X-Trace-ID"] = returned_trace_id
        response.headers["X-Processing-Time-MS"] = str(processing_time_ms)
        
        logger.info(f"[{returned_trace_id}] Request completed in {processing_time_ms:.2f}ms")
        
        return AgentResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{trace_id}] Unexpected error: {e}", exc_info=True)
        response.headers["X-Trace-ID"] = trace_id
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@batch_tools_router.get("/health")
async def health_check():
    """健康检查端点"""
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


@batch_tools_router.get("/metrics")
async def get_metrics():
    """性能指标端点"""
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


@batch_tools_router.get("/config")
async def get_config():
    """配置信息端点"""
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