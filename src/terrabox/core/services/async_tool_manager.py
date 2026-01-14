"""
Async Tool Manager - Core Scheduler

Responsibilities:
- Parse/Identify tools -> Group by tool -> Concurrent execution (async await; sync using thread pool) -> Aggregate results (aligned with index)
- Support explicit tool specification and automatic tool identification
- Compatible with both async and sync handler forms
- Support batch parsing, process pool, connection management, and complete log tracing
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

from ..registry import get_handler, list_toolkits, list_tools  # Functions to retrieve existing tools
from .async_tool_config import AsyncToolServerConfig

logger = logging.getLogger(__name__)

# CPU-intensive tool list (configurable)
CPU_INTENSIVE_TOOLS = {
    "image_processing", "ml_inference", "data_analysis", 
    "geospatial_compute", "statistical_compute"
}

class AsyncToolManager:
    """Async Tool Manager - Core scheduler for batch tool execution"""
    
    def __init__(self, cfg: AsyncToolServerConfig, db: Optional[Session] = None):
        """Initialize Tool Manager
        
        Args:
            cfg: Async tool server configuration
            db: Database session (for connection management)
        """
        self.cfg = cfg
        self.db = db
        
        # Thread pool (for sync tools and batch parsing)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=cfg.resolved_pool(),
            thread_name_prefix="tool_worker"
        )
        
        # Process pool (for CPU-intensive tools)
        self.process_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=min(cfg.resolved_pool() // 4, 8),  # Smaller process pool
            mp_context=None  # Use default context
        )
        
        # Batch parsing thread pool
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
        """Process batch action execution
        
        Args:
            trajectory_ids: List of trajectory IDs
            actions: List of action strings
            extra_fields: List of extra fields containing tool info
            user_id: User ID (for connection management)
            trace_id: Trace ID (for logging)
            
        Returns:
            Tuple[observations, dones, valids, trace_id]: Observations, completion status, validity status, trace ID
        """
        # Generate trace ID
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        start_time = time.time()
        n = len(actions)
        
        logger.info(f"[{trace_id}] Starting batch processing: {n} actions")
        
        obs: List[Union[str, dict]] = [None] * n
        dones: List[bool] = [False] * n
        valids: List[bool] = [False] * n
        
        try:
            # 1) Batch identify tools (using thread pool for chunk processing)
            groups = await self._batch_parse_actions(actions, extra_fields, trace_id)
            
            # 2) Handle connection management
            if user_id and self.db:
                groups = await self._resolve_connections(groups, extra_fields, user_id, trace_id)
            
            # 3) Concurrent execution: Create tasks by group
            tasks: List[Tuple[str, List[int], Any]] = []
            for slug, idxs in groups.items():
                if slug is None:
                    # Handle unspecified tools
                    for k in idxs:
                        obs[k] = {
                            "invalid_reason": "no tool specified",
                            "available": "set extra_fields[i]['tool'] or use recognizable action format",
                            "trace_id": trace_id
                        }
                        dones[k] = True
                        valids[k] = False
                    continue
                
                # Prepare batch input for the tool
                actions_i = [actions[k] for k in idxs]
                extras_i = [extra_fields[k] for k in idxs]
                task = self._create_task(slug, actions_i, extras_i, trace_id, user_id)
                tasks.append((slug, idxs, task))
            
            # 4) Aggregate results (fallback for exceptions)
            for slug, idxs, task in tasks:
                try:
                    res = await task if inspect.isawaitable(task) else task
                    tool_obs, tool_done, tool_valid = res
                    
                    # Align results back to original positions
                    for j, k in enumerate(idxs):
                        obs[k] = tool_obs[j]
                        dones[k] = tool_done[j]
                        valids[k] = tool_valid[j]
                        
                        # Add trace info
                        if isinstance(obs[k], dict):
                            obs[k]["trace_id"] = trace_id
                        
                except Exception as e:
                    logger.error(f"[{trace_id}] Tool {slug} execution failed: {e}")
                    # Fallback: Mark all requests in this tool group as error
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
            # Global exception fallback
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
        """Batch parse actions to identify tools (using thread pool chunk processing)
        
        Args:
            actions: List of action strings
            extra_fields: List of extra fields
            trace_id: Trace ID
            
        Returns:
            Dict[tool_slug, indices]: Tool grouping results
        """
        groups: Dict[Optional[str], List[int]] = {}
        
        # First handle explicitly specified tools
        for i, ef in enumerate(extra_fields):
            slug = ef.get("tool")
            if slug:
                groups.setdefault(slug, []).append(i)
            else:
                groups.setdefault(None, []).append(i)
        
        # Batch parse for unspecified tools
        unspecified_indices = groups.get(None, [])
        if unspecified_indices:
            logger.info(f"[{trace_id}] Parsing {len(unspecified_indices)} unspecified actions")
            
            # Process in chunks to avoid large batch blocking
            chunk_size = 50  # Process 50 actions per chunk
            chunks = [
                unspecified_indices[i:i + chunk_size] 
                for i in range(0, len(unspecified_indices), chunk_size)
            ]
            
            # Process chunks in parallel
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
            
            # Wait for all parse tasks to complete
            chunk_results = await asyncio.gather(*parse_tasks, return_exceptions=True)
            
            # Merge parse results
            groups.pop(None, None)  # Remove original None group
            
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
        """Parse action chunk to identify tools (executed in thread pool)
        
        Args:
            actions: List of action strings
            indices: Corresponding original indices
            trace_id: Trace ID
            
        Returns:
            Dict[tool_slug, indices]: Tool grouping results
        """
        chunk_groups: Dict[Optional[str], List[int]] = {}
        
        # Simple tool identification rules (extensible)
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
            
            # Try to match tool patterns
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
        """Resolve connection info, handle connection/app_key
        
        Args:
            groups: Tool groups
            extra_fields: List of extra fields
            user_id: User ID
            trace_id: Trace ID
            
        Returns:
            Dict[tool_slug, indices]: Updated tool groups
        """
        if not self.db:
            return groups
        
        from .connection_service import ConnectionService
        
        logger.info(f"[{trace_id}] Resolving connections for user {user_id}")
        
        # Resolve connection for each tool group
        for slug, indices in groups.items():
            if slug is None:
                continue
            
            for i in indices:
                ef = extra_fields[i]
                
                # Check if connection or app_key is specified
                connection_id = ef.get("connection")
                app_key = ef.get("app_key")
                
                if connection_id:
                    # Use specified connection ID directly
                    ef["resolved_connection_id"] = connection_id
                elif app_key:
                    # Find connection by app_key
                    try:
                        connection = ConnectionService.select_connection(self.db, user_id, app_key)
                        if connection:
                            ef["resolved_connection_id"] = str(connection.id)
                        else:
                            logger.warning(f"[{trace_id}] No connection found for app_key: {app_key}")
                    except Exception as e:
                        logger.error(f"[{trace_id}] Failed to resolve connection for app_key {app_key}: {e}")
                else:
                    # Try to auto-find connection for tool
                    try:
                        # Find corresponding toolkit for the tool
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
        """Create tool execution task, compatible with async/sync handler, supports process pool
        
        Args:
            slug: Tool identifier
            acts: List of actions
            extras: List of extra fields
            trace_id: Trace ID
            user_id: User ID
            
        Returns:
            Task or Future: Async task or Future object
        """
        try:
            handler = get_handler(slug)
        except Exception as e:
            logger.error(f"[{trace_id}] Tool '{slug}' not found: {e}")
            # Tool not found or failed to retrieve
            def error_result():
                return (
                    [{"error": f"Tool '{slug}' not found: {str(e)}", "trace_id": trace_id}] * len(acts),
                    [True] * len(acts),
                    [False] * len(acts)
                )
            return error_result()
        
        # Determine if it is a CPU-intensive tool
        is_cpu_intensive = any(keyword in slug.lower() for keyword in CPU_INTENSIVE_TOOLS)
        
        if inspect.iscoroutinefunction(handler):
            # Async handler: Create async task directly
            async def run_async_batch():
                O, D, V = [], [], []
                for a, ef in zip(acts, extras):
                    try:
                        # Prepare context
                        context = self._prepare_context(ef, user_id, trace_id)
                        
                        # Parse action parameters
                        try:
                            import json
                            arguments = json.loads(a) if isinstance(a, str) else a
                        except (json.JSONDecodeError, TypeError):
                            # If parsing fails, use original string as action parameter
                            arguments = {"action": a}
                        
                        # Execute tool
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
            # Sync handler: Choose thread pool or process pool
            loop = asyncio.get_event_loop()
            
            def run_sync_batch():
                O, D, V = [], [], []
                for a, ef in zip(acts, extras):
                    try:
                        # Prepare context
                        context = self._prepare_context(ef, user_id, trace_id)
                        
                        # Parse action parameters
                        try:
                            import json
                            arguments = json.loads(a) if isinstance(a, str) else a
                        except (json.JSONDecodeError, TypeError):
                            # If parsing fails, use original string as action parameter
                            arguments = {"action": a}
                        
                        # Execute tool
                        r = handler(arguments, context)
                        O.append(r.get("obs", r))
                        D.append(bool(r.get("done", False)))
                        V.append(bool(r.get("valid", True)))
                        
                    except Exception as e:
                        O.append({"error": str(e), "trace_id": trace_id})
                        D.append(True)
                        V.append(False)
                return O, D, V
            
            # Select executor pool
            executor = self.process_pool if is_cpu_intensive else self.thread_pool
            logger.debug(f"[{trace_id}] Using {'process' if is_cpu_intensive else 'thread'} pool for tool {slug}")
            
            return loop.run_in_executor(executor, run_sync_batch)

    def _prepare_context(
        self, 
        extra_field: Dict[str, Any], 
        user_id: Optional[str], 
        trace_id: str
    ) -> Dict[str, Any]:
        """Prepare tool execution context
        
        Args:
            extra_field: Extra fields
            user_id: User ID
            trace_id: Trace ID
            
        Returns:
            Dict: Tool execution context
        """
        context = {
            "trace_id": trace_id,
            "timestamp": time.time()
        }
        
        if user_id:
            context["user_id"] = user_id
        
        # Add connection info
        if "resolved_connection_id" in extra_field:
            context["connection_id"] = extra_field["resolved_connection_id"]
        
        # Merge other metadata
        for key, value in extra_field.items():
            if key not in ["tool", "connection", "app_key", "resolved_connection_id"]:
                context[key] = value
        
        return context
    
    def __del__(self):
        """Clean up resources"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=False)
        if hasattr(self, 'process_pool'):
            self.process_pool.shutdown(wait=False)
        if hasattr(self, 'parse_pool'):
            self.parse_pool.shutdown(wait=False)
