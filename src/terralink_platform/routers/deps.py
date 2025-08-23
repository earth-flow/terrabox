"""Authentication dependencies for FastAPI routes."""

from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db import models
from ..core.utils.security import hash_api_key, verify_token
from ..core.services import AuthService

# HTTP Bearer token scheme for JWT
security = HTTPBearer(auto_error=False)

def current_user_from_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> models.User:
    """从API Key获取当前用户（用于SDK）"""
    return AuthService.get_current_user_from_api_key(db, x_api_key)

def current_user_from_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """从JWT令牌获取当前用户（用于GUI）"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthService.get_current_user(db, credentials)

def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> models.User:
    """验证API密钥并返回用户（兼容现有代码）"""
    return current_user_from_api_key(x_api_key, db)