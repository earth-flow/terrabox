"""
Async Tool Service - Pure Service Layer

Provides core business logic for batch tool execution, supporting:
- Batch concurrent execution
- Smart caching (LRU + TTL)
- Complete log tracing
- Connection management
- Performance monitoring
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

# Global config and manager instance
_config = AsyncToolServerConfig()
_manager: Optional[AsyncToolManager] = None
_semaphore: Optional[asyncio.Semaphore] = None

# LRU Cache (with TTL)
class CacheEntry:
    """Cache entry, containing data and expiration time"""
    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.expires_at = time.time() + ttl
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

# Use LRU cache instead of WeakValueDictionary
@lru_cache(maxsize=None)
def _get_cache():
    """Get cache instance (lazy initialization)"""
    return {}

def _get_from_cache(key: str) -> Optional[Any]:
    """Get data from cache"""
    cache = _get_cache()
    entry = cache.get(key)
    if entry and not entry.is_expired():
        return entry.data
    elif entry:
        # Clean up expired entry
        cache.pop(key, None)
    return None

def _set_to_cache(key: str, data: Any):
    """Set cache data"""
    if not _config.hash_requests:
        return
    
    cache = _get_cache()
    
    # Clean up expired entries (simple strategy)
    if len(cache) > _config.cache_max_size:
        expired_keys = [k for k, v in cache.items() if v.is_expired()]
        for k in expired_keys:
            cache.pop(k, None)
        
        # If still too many, remove oldest entries
        if len(cache) > _config.cache_max_size:
            oldest_keys = sorted(cache.keys())[:len(cache) - _config.cache_max_size + 100]
            for k in oldest_keys:
                cache.pop(k, None)
    
    cache[key] = CacheEntry(data, _config.cache_ttl)


class ActionRequest(BaseModel):
    """Batch action request body"""
    trajectory_ids: List[str] = Field(..., description="List of trajectory IDs")
    actions: List[str] = Field(..., description="List of action strings")
    extra_fields: List[Dict[str, Any]] = Field(default_factory=list, description="List of extra fields")
    user_id: Optional[str] = Field(None, description="User ID (for connection management)")
    trace_id: Optional[str] = Field(None, description="Trace ID (for logging)")


class AgentResponse(BaseModel):
    """Batch action response body"""
    observations: List[Any] = Field(..., description="List of observations")
    dones: List[bool] = Field(..., description="List of completion statuses")
    valids: List[bool] = Field(..., description="List of validity statuses")
    trace_id: str = Field(..., description="Trace ID")
    processing_time_ms: float = Field(..., description="Processing time (ms)")


class AsyncToolsService:
    """Async Tools Service Class - Handles core business logic for batch tool execution"""
    
    def __init__(self, db: Session):
        self.db = db
        self._ensure_manager_and_semaphore()
    
    def _ensure_manager_and_semaphore(self):
        """Ensure manager and semaphore are initialized"""
        global _manager, _semaphore
        
        if _manager is None:
            _manager = AsyncToolManager(_config, self.db)
        
        if _semaphore is None:
            _semaphore = asyncio.Semaphore(_config.max_concurrent_requests)
    
    def _hash_req(self, req: ActionRequest) -> str:
        """Generate request hash (for caching)"""
        # Create normalized representation of request
        normalized = {
            "actions": req.actions,
            "extra_fields": req.extra_fields,
            "user_id": req.user_id
        }
        
        # Generate SHA256 hash
        content = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def execute_batch_actions(
        self, 
        request: ActionRequest, 
        user_id: str
    ) -> Tuple[AgentResponse, Dict[str, str]]:
        """Execute batch tool actions
        
        Args:
            request: Batch action request
            user_id: User ID
            
        Returns:
            Tuple[AgentResponse, Dict[str, str]]: Response data and headers
        """
        start_time = time.time()
        
        # Generate or use provided trace ID
        trace_id = request.trace_id or str(uuid.uuid4())
        
        logger.info(f"[{trace_id}] Received batch request: {len(request.actions)} actions")
        
        # Input validation
        if len(request.actions) != len(request.trajectory_ids):
            raise ValueError("actions and trajectory_ids must have the same length")
        
        if request.extra_fields and len(request.extra_fields) != len(request.actions):
            raise ValueError("extra_fields must have the same length as actions")
        
        # Fill default extra_fields
        if not request.extra_fields:
            request.extra_fields = [{}] * len(request.actions)
        
        # Cache check
        cache_key = None
        headers = {"X-Trace-ID": trace_id}
        
        if _config.hash_requests:
            cache_key = self._hash_req(request)
            cached_result = _get_from_cache(cache_key)
            if cached_result:
                logger.info(f"[{trace_id}] Cache hit for request")
                # Update trace ID
                cached_result["trace_id"] = trace_id
                headers["X-Cache-Status"] = "hit"
                return AgentResponse(**cached_result), headers
        
        # Acquire semaphore and execute batch processing
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
        
        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Build response
        result = {
            "observations": obs,
            "dones": dones,
            "valids": valids,
            "trace_id": returned_trace_id,
            "processing_time_ms": processing_time_ms
        }
        
        # Cache result
        if cache_key:
            _set_to_cache(cache_key, result)
            headers["X-Cache-Status"] = "miss"
        
        # Set response headers
        headers["X-Trace-ID"] = returned_trace_id
        headers["X-Processing-Time-MS"] = str(processing_time_ms)
        
        logger.info(f"[{returned_trace_id}] Request completed in {processing_time_ms:.2f}ms")
        
        return AgentResponse(**result), headers
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status"""
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
        """Get performance metrics"""
        cache = _get_cache()
        
        # Statistics cache status
        total_entries = len(cache)
        expired_entries = sum(1 for entry in cache.values() if entry.is_expired())
        active_entries = total_entries - expired_entries
        
        # Get semaphore status
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
        """Get configuration info"""
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
