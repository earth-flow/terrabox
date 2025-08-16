"""Authentication dependencies for FastAPI routes."""

from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db import models
from ..security import hash_api_key, verify_token

# HTTP Bearer token scheme for JWT
security = HTTPBearer(auto_error=False)

def current_user_from_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> models.User:
    """从API Key获取当前用户（用于SDK）"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    # 哈希API密钥进行查找
    hashed_key = hash_api_key(x_api_key)
    
    # 查找API密钥
    api_key_obj = db.query(models.ApiKey).filter(
        models.ApiKey.secret_hash == hashed_key,
        models.ApiKey.is_active == True
    ).first()
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # 获取用户
    user = db.query(models.User).filter(
        models.User.id == api_key_obj.user_id_fk,
        models.User.is_active == True
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user

def current_user_from_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """从JWT令牌获取当前用户（用于GUI）"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # 验证JWT令牌
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # 从payload中获取用户ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # 查找用户
    user = db.query(models.User).filter(
        models.User.id == int(user_id),
        models.User.is_active == True
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user

def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> models.User:
    """验证API密钥并返回用户（兼容现有代码）"""
    return current_user_from_api_key(x_api_key, db)