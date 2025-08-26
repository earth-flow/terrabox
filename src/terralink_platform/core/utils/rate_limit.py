"""Simple rate limiting implementation."""

import time
from typing import Dict, Tuple
from fastapi import HTTPException, Request, status
from collections import defaultdict, deque


class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Check if request is allowed for given key.
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        requests = self.requests[key]
        while requests and requests[0] < window_start:
            requests.popleft()
        
        # Check if under limit
        if len(requests) < self.max_requests:
            requests.append(now)
            return True, self.max_requests - len(requests)
        
        return False, 0
    
    def check_rate_limit(self, key: str) -> None:
        """Check rate limit and raise HTTPException if exceeded."""
        allowed, remaining = self.is_allowed(key)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)}
            )


# Global rate limiters
auth_rate_limiter = RateLimiter(max_requests=5, window_seconds=300)  # 5 requests per 5 minutes
general_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100 requests per minute


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Check for forwarded headers first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to client host
    return request.client.host if request.client else "unknown"


def check_auth_rate_limit(request: Request) -> None:
    """Check rate limit for authentication endpoints."""
    client_ip = get_client_ip(request)
    auth_rate_limiter.check_rate_limit(f"auth:{client_ip}")


def check_general_rate_limit(request: Request) -> None:
    """Check general rate limit."""
    client_ip = get_client_ip(request)
    general_rate_limiter.check_rate_limit(f"general:{client_ip}")