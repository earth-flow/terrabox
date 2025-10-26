"""
异步工具服务器配置
"""

from typing import Optional
from pydantic import BaseModel, Field


class AsyncToolServerConfig(BaseModel):
    """异步工具服务器配置"""
    
    max_concurrent_requests: int = Field(default=100, description="最大并发请求数")
    request_timeout: float = Field(default=30.0, description="请求超时时间（秒）")
    thread_pool_size: Optional[int] = Field(default=None, description="线程池大小")
    
    # 缓存配置
    hash_requests: bool = Field(default=True, description="是否启用请求哈希缓存")
    cache_max_size: int = Field(default=1000, description="LRU 缓存最大条目数")
    cache_ttl: int = Field(default=3600, description="缓存生存时间（秒）")
    
    # 进程池配置
    process_pool_size: Optional[int] = Field(default=None, description="进程池大小（CPU密集型工具）")
    
    # 解析配置
    parse_pool_size: Optional[int] = Field(default=None, description="解析线程池大小")
    parse_chunk_size: int = Field(default=50, description="批量解析块大小")
    
    def resolved_pool(self) -> int:
        """解析线程池大小"""
        import os
        return self.thread_pool_size or min(32, (os.cpu_count() or 1) + 4)
    
    def resolved_process_pool(self) -> int:
        """解析进程池大小"""
        import os
        return self.process_pool_size or min(8, max(1, (os.cpu_count() or 1) // 4))
    
    def resolved_parse_pool(self) -> int:
        """解析解析线程池大小"""
        import os
        return self.parse_pool_size or min(16, max(4, (os.cpu_count() or 1) // 2))