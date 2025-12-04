"""
异步工具管理器 - 核心调度器

职责：
- 解析/识别工具 → 按工具分组 → 并发执行（async 直接 await；sync 用线程池）→ 汇总结果（与 index 对齐）
- 支持显式工具指定和自动工具识别
- 兼容 async/sync handler 两种形态
- 支持批量解析、进程池、连接管理和完整日志追踪
"""

import asyncio
import inspect
import concurrent.futures
import logging
import uuid
import time
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy.orm import Session

from ..runtime_registry import get_handler, list_toolkits, list_tools  # 项目已有的工具获取函数
from .async_tool_config import AsyncToolServerConfig

logger = logging.getLogger(__name__)

# CPU 密集型工具列表（可配置）
CPU_INTENSIVE_TOOLS = {
    "image_processing", "ml_inference", "data_analysis", 
    "geospatial_compute", "statistical_compute"
}

class AsyncToolManager:
    """异步工具管理器 - 负责批量工具执行的核心调度"""
    
    def __init__(self, cfg: AsyncToolServerConfig, db: Optional[Session] = None):
        """初始化工具管理器
        
        Args:
            cfg: 异步工具服务器配置
            db: 数据库会话（用于连接管理）
        """
        self.cfg = cfg
        self.db = db
        
        # 线程池（用于同步工具和批量解析）
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=cfg.resolved_pool(),
            thread_name_prefix="tool_worker"
        )
        
        # 进程池（用于 CPU 密集型工具）
        self.process_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=min(cfg.resolved_pool() // 4, 8),  # 进程池较小
            mp_context=None  # 使用默认上下文
        )
        
        # 批量解析线程池
        self.parse_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(cfg.resolved_pool() // 2, 16),
            thread_name_prefix="parse_worker"
        )

    async def process_actions(
        self,
        trajectory_ids: List[str],
        actions: List[str],
        extra_fields: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Tuple[List[Union[str, dict]], List[bool], List[bool], str]:
        """处理批量动作执行
        
        Args:
            trajectory_ids: 轨迹ID列表
            actions: 动作字符串列表
            extra_fields: 额外字段列表，包含工具信息
            user_id: 用户ID（用于连接管理）
            trace_id: 追踪ID（用于日志）
            
        Returns:
            Tuple[observations, dones, valids, trace_id]: 观察结果、完成状态、有效性状态、追踪ID
        """
        # 生成追踪ID
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        start_time = time.time()
        n = len(actions)
        
        logger.info(f"[{trace_id}] Starting batch processing: {n} actions")
        
        obs: List[Union[str, dict]] = [None] * n
        dones: List[bool] = [False] * n
        valids: List[bool] = [False] * n
        
        try:
            # 1) 批量识别工具（使用线程池进行 chunk 处理）
            groups = await self._batch_parse_actions(actions, extra_fields, trace_id)
            
            # 2) 处理连接管理
            if user_id and self.db:
                groups = await self._resolve_connections(groups, extra_fields, user_id, trace_id)
            
            # 3) 并发执行：按组创建任务
            tasks: List[Tuple[str, List[int], Any]] = []
            for slug, idxs in groups.items():
                if slug is None:
                    # 处理未指定工具的情况
                    for k in idxs:
                        obs[k] = {
                            "invalid_reason": "no tool specified",
                            "available": "set extra_fields[i]['tool'] or use recognizable action format",
                            "trace_id": trace_id
                        }
                        dones[k] = True
                        valids[k] = False
                    continue
                
                # 准备该工具的批量输入
                actions_i = [actions[k] for k in idxs]
                extras_i = [extra_fields[k] for k in idxs]
                task = self._create_task(slug, actions_i, extras_i, trace_id, user_id)
                tasks.append((slug, idxs, task))
            
            # 4) 汇总结果（异常兜底）
            for slug, idxs, task in tasks:
                try:
                    res = await task if inspect.isawaitable(task) else task
                    tool_obs, tool_done, tool_valid = res
                    
                    # 将结果按索引对齐回原始位置
                    for j, k in enumerate(idxs):
                        obs[k] = tool_obs[j]
                        dones[k] = tool_done[j]
                        valids[k] = tool_valid[j]
                        
                        # 添加追踪信息
                        if isinstance(obs[k], dict):
                            obs[k]["trace_id"] = trace_id
                        
                except Exception as e:
                    logger.error(f"[{trace_id}] Tool {slug} execution failed: {e}")
                    # 异常兜底：该工具组的所有请求都标记为错误
                    for k in idxs:
                        obs[k] = {
                            "error": str(e), 
                            "tool": slug,
                            "trace_id": trace_id
                        }
                        dones[k] = True
                        valids[k] = False
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"[{trace_id}] Batch processing completed in {processing_time:.2f}ms")
            
            return obs, dones, valids, trace_id
            
        except Exception as e:
            logger.error(f"[{trace_id}] Batch processing failed: {e}")
            # 全局异常兜底
            for i in range(n):
                obs[i] = {
                    "error": f"Batch processing failed: {str(e)}",
                    "trace_id": trace_id
                }
                dones[i] = True
                valids[i] = False
            
            return obs, dones, valids, trace_id

    async def _batch_parse_actions(
        self, 
        actions: List[str], 
        extra_fields: List[Dict[str, Any]], 
        trace_id: str
    ) -> Dict[Optional[str], List[int]]:
        """批量解析动作，识别工具（使用线程池 chunk 处理）
        
        Args:
            actions: 动作字符串列表
            extra_fields: 额外字段列表
            trace_id: 追踪ID
            
        Returns:
            Dict[tool_slug, indices]: 工具分组结果
        """
        groups: Dict[Optional[str], List[int]] = {}
        
        # 首先处理显式指定的工具
        for i, ef in enumerate(extra_fields):
            slug = ef.get("tool")
            if slug:
                groups.setdefault(slug, []).append(i)
            else:
                groups.setdefault(None, []).append(i)
        
        # 对于未指定工具的动作，进行批量解析
        unspecified_indices = groups.get(None, [])
        if unspecified_indices:
            logger.info(f"[{trace_id}] Parsing {len(unspecified_indices)} unspecified actions")
            
            # 分块处理，避免大批量阻塞
            chunk_size = 50  # 每块处理50个动作
            chunks = [
                unspecified_indices[i:i + chunk_size] 
                for i in range(0, len(unspecified_indices), chunk_size)
            ]
            
            # 并行处理各个块
            loop = asyncio.get_event_loop()
            parse_tasks = []
            
            for chunk_indices in chunks:
                chunk_actions = [actions[i] for i in chunk_indices]
                task = loop.run_in_executor(
                    self.parse_pool,
                    self._parse_actions_chunk,
                    chunk_actions,
                    chunk_indices,
                    trace_id
                )
                parse_tasks.append(task)
            
            # 等待所有解析任务完成
            chunk_results = await asyncio.gather(*parse_tasks, return_exceptions=True)
            
            # 合并解析结果
            groups.pop(None, None)  # 移除原始的 None 组
            
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"[{trace_id}] Parse chunk failed: {result}")
                    continue
                
                for slug, indices in result.items():
                    groups.setdefault(slug, []).extend(indices)
        
        return groups

    def _parse_actions_chunk(
        self, 
        actions: List[str], 
        indices: List[int], 
        trace_id: str
    ) -> Dict[Optional[str], List[int]]:
        """解析动作块，识别工具（在线程池中执行）
        
        Args:
            actions: 动作字符串列表
            indices: 对应的原始索引
            trace_id: 追踪ID
            
        Returns:
            Dict[tool_slug, indices]: 工具分组结果
        """
        chunk_groups: Dict[Optional[str], List[int]] = {}
        
        # 简单的工具识别规则（可扩展）
        tool_patterns = {
            r'search\s*\(': 'search_engine',
            r'calculate\s*\(': 'calculator',
            r'translate\s*\(': 'translator',
            r'image\s*\(': 'image_processing',
            r'geo\s*\(': 'geospatial_compute',
            r'analyze\s*\(': 'data_analysis',
            r'ml\s*\(': 'ml_inference',
        }
        
        for i, action in enumerate(actions):
            original_index = indices[i]
            detected_tool = None
            
            # 尝试匹配工具模式
            for pattern, tool_slug in tool_patterns.items():
                if re.search(pattern, action, re.IGNORECASE):
                    detected_tool = tool_slug
                    break
            
            chunk_groups.setdefault(detected_tool, []).append(original_index)
        
        return chunk_groups

    async def _resolve_connections(
        self,
        groups: Dict[Optional[str], List[int]],
        extra_fields: List[Dict[str, Any]],
        user_id: str,
        trace_id: str
    ) -> Dict[Optional[str], List[int]]:
        """解析连接信息，处理 connection/app_key
        
        Args:
            groups: 工具分组
            extra_fields: 额外字段列表
            user_id: 用户ID
            trace_id: 追踪ID
            
        Returns:
            Dict[tool_slug, indices]: 更新后的工具分组
        """
        if not self.db:
            return groups
        
        from .connection_service import ConnectionService
        
        logger.info(f"[{trace_id}] Resolving connections for user {user_id}")
        
        # 为每个工具组解析连接
        for slug, indices in groups.items():
            if slug is None:
                continue
            
            for i in indices:
                ef = extra_fields[i]
                
                # 检查是否指定了连接或 app_key
                connection_id = ef.get("connection")
                app_key = ef.get("app_key")
                
                if connection_id:
                    # 直接使用指定的连接ID
                    ef["resolved_connection_id"] = connection_id
                elif app_key:
                    # 根据 app_key 查找连接
                    try:
                        connection = ConnectionService.select_connection(self.db, user_id, app_key)
                        if connection:
                            ef["resolved_connection_id"] = str(connection.id)
                        else:
                            logger.warning(f"[{trace_id}] No connection found for app_key: {app_key}")
                    except Exception as e:
                        logger.error(f"[{trace_id}] Failed to resolve connection for app_key {app_key}: {e}")
                else:
                    # 尝试为工具自动查找连接
                    try:
                        # 根据工具查找对应的 toolkit
                        for toolkit in list_toolkits():
                            toolkit_tools = list_tools(toolkit.name)
                            if any(t.slug == slug for t in toolkit_tools):
                                connection = ConnectionService.select_connection(self.db, user_id, toolkit.name)
                                if connection:
                                    ef["resolved_connection_id"] = str(connection.id)
                                break
                    except Exception as e:
                        logger.error(f"[{trace_id}] Failed to auto-resolve connection for tool {slug}: {e}")
        
        return groups

    def _create_task(
        self, 
        slug: str, 
        acts: List[str], 
        extras: List[Dict[str, Any]], 
        trace_id: str,
        user_id: Optional[str] = None
    ):
        """创建工具执行任务，兼容 async/sync handler，支持进程池
        
        Args:
            slug: 工具标识符
            acts: 动作列表
            extras: 额外字段列表
            trace_id: 追踪ID
            user_id: 用户ID
            
        Returns:
            Task or Future: 异步任务或Future对象
        """
        try:
            handler = get_handler(slug)
        except Exception as e:
            logger.error(f"[{trace_id}] Tool '{slug}' not found: {e}")
            # 工具不存在或获取失败
            def error_result():
                return (
                    [{"error": f"Tool '{slug}' not found: {str(e)}", "trace_id": trace_id}] * len(acts),
                    [True] * len(acts),
                    [False] * len(acts)
                )
            return error_result()
        
        # 判断是否为 CPU 密集型工具
        is_cpu_intensive = any(keyword in slug.lower() for keyword in CPU_INTENSIVE_TOOLS)
        
        if inspect.iscoroutinefunction(handler):
            # 异步处理器：直接创建异步任务
            async def run_async_batch():
                O, D, V = [], [], []
                for a, ef in zip(acts, extras):
                    try:
                        # 准备上下文
                        context = self._prepare_context(ef, user_id, trace_id)
                        
                        # 解析action参数
                        try:
                            import json
                            arguments = json.loads(a) if isinstance(a, str) else a
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，使用原始字符串作为action参数
                            arguments = {"action": a}
                        
                        # 执行工具
                        r = await handler(arguments, context)
                        O.append(r.get("obs", r))
                        D.append(bool(r.get("done", False)))
                        V.append(bool(r.get("valid", True)))
                        
                        logger.debug(f"[{trace_id}] Tool {slug} executed successfully")
                        
                    except Exception as e:
                        logger.error(f"[{trace_id}] Tool {slug} execution failed: {e}")
                        O.append({"error": str(e), "trace_id": trace_id})
                        D.append(True)
                        V.append(False)
                return O, D, V

            return asyncio.create_task(run_async_batch())
        
        else:
            # 同步处理器：选择线程池或进程池
            loop = asyncio.get_event_loop()
            
            def run_sync_batch():
                O, D, V = [], [], []
                for a, ef in zip(acts, extras):
                    try:
                        # 准备上下文
                        context = self._prepare_context(ef, user_id, trace_id)
                        
                        # 解析action参数
                        try:
                            import json
                            arguments = json.loads(a) if isinstance(a, str) else a
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，使用原始字符串作为action参数
                            arguments = {"action": a}
                        
                        # 执行工具
                        r = handler(arguments, context)
                        O.append(r.get("obs", r))
                        D.append(bool(r.get("done", False)))
                        V.append(bool(r.get("valid", True)))
                        
                    except Exception as e:
                        O.append({"error": str(e), "trace_id": trace_id})
                        D.append(True)
                        V.append(False)
                return O, D, V
            
            # 选择执行池
            executor = self.process_pool if is_cpu_intensive else self.thread_pool
            logger.debug(f"[{trace_id}] Using {'process' if is_cpu_intensive else 'thread'} pool for tool {slug}")
            
            return loop.run_in_executor(executor, run_sync_batch)

    def _prepare_context(
        self, 
        extra_field: Dict[str, Any], 
        user_id: Optional[str], 
        trace_id: str
    ) -> Dict[str, Any]:
        """准备工具执行上下文
        
        Args:
            extra_field: 额外字段
            user_id: 用户ID
            trace_id: 追踪ID
            
        Returns:
            Dict: 工具执行上下文
        """
        context = {
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        
        if user_id:
            context["user_id"] = user_id
        
        # 添加连接信息
        if "resolved_connection_id" in extra_field:
            context["connection_id"] = extra_field["resolved_connection_id"]
        
        # 合并其他元数据
        for key, value in extra_field.items():
            if key not in ["tool", "connection", "app_key", "resolved_connection_id"]:
                context[key] = value
        
        return context
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=False)
        if hasattr(self, 'process_pool'):
            self.process_pool.shutdown(wait=False)
        if hasattr(self, 'parse_pool'):
            self.parse_pool.shutdown(wait=False)