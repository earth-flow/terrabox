"""
Async Tool Server Configuration
"""

from typing import Optional
from pydantic import BaseModel, Field


class AsyncToolServerConfig(BaseModel):
    """Async Tool Server Configuration"""
    
    max_concurrent_requests: int = Field(default=100, description="Maximum concurrent requests")
    request_timeout: float = Field(default=30.0, description="Request timeout (seconds)")
    thread_pool_size: Optional[int] = Field(default=None, description="Thread pool size")
    
    # Cache configuration
    hash_requests: bool = Field(default=True, description="Enable request hash caching")
    cache_max_size: int = Field(default=1000, description="LRU cache max size")
    cache_ttl: int = Field(default=3600, description="Cache TTL (seconds)")
    
    # Process pool configuration
    process_pool_size: Optional[int] = Field(default=None, description="Process pool size (CPU-bound tools)")
    
    # Parsing configuration
    parse_pool_size: Optional[int] = Field(default=None, description="Parsing thread pool size")
    parse_chunk_size: int = Field(default=50, description="Batch parsing chunk size")
    
    def resolved_pool(self) -> int:
        """Resolve thread pool size"""
        import os
        return self.thread_pool_size or min(32, (os.cpu_count() or 1) + 4)
    
    def resolved_process_pool(self) -> int:
        """Resolve process pool size"""
        import os
        return self.process_pool_size or min(8, max(1, (os.cpu_count() or 1) // 4))
    
    def resolved_parse_pool(self) -> int:
        """Resolve parsing thread pool size"""
        import os
        return self.parse_pool_size or min(16, max(4, (os.cpu_count() or 1) // 2))