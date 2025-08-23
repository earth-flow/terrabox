"""Routes related to user registration and account connections."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from ..models import (
    Connection, ConnectedAccount, User, UserCreate, UserResponse, 
    TokenResponse, ApiKeyCreate, ApiKeyResponse, ApiKeyListResponse, UserLogin,
    OAuthProviderResponse, OAuthAuthRequest, OAuthAuthResponse, OAuthCallbackRequest,
    UserOAuthAccountResponse
)
from pydantic import BaseModel
from ..core.schemas import (
    CreateConnectionRequest, CreateConnectionResponse, ConnectionStatusResponse,
    ConnectedAccountOut, ApiKeyCreateRequest, ApiKeyListResponse
)
from ..db.session import get_db
from ..db import models as m
from ..core.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
    generate_api_key,
    hash_api_key,
    validate_password_strength,
    mask_key,
    generate_public_id
)
from ..core.services import AuthService
from ..core.oauth_service import OAuthService
from .deps import current_user_from_api_key, current_user_from_jwt
from ..core.utils.rate_limit import auth_rate_limiter


# =============================================================================
# SDK Router (API Key Authentication)
# =============================================================================

sdk_router = APIRouter(prefix="/v1/sdk", tags=["auth-sdk"])


# =============================================================================
# GUI Router (JWT Authentication)
# =============================================================================

gui_router = APIRouter(prefix="/v1/gui", tags=["auth-gui"])

# Security scheme for API key authentication
security = HTTPBearer()

# =============================================================================
# Common Routes (No Authentication Required)
# =============================================================================

common_router = APIRouter(prefix="/v1", tags=["auth-common"])

@common_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with username, email and password.
    
    Returns user information and automatically creates an API key.
    """
    # Check rate limit
    auth_rate_limiter.check_rate_limit(request.client.host)
    
    # Validate password strength
    is_valid, message = validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # Create new user using service
    db_user = AuthService.create_user(db, user_data)
    
    # Create default API key using service
    db_api_key = AuthService.create_user_api_key(db, db_user.id, "Default API Key")
    
    return UserResponse(
        id=db_user.id,
        user_id=db_user.user_id,
        email=db_user.email,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
        api_key=db_api_key.key  # Return the raw API key only once
    )

@sdk_router.post("/auth/connections", response_model=CreateConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection_sdk(payload: CreateConnectionRequest, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Initiate a connection for a toolkit (SDK version).

    Returns a connection identifier and a redirect URL which the
    client should open in a browser.  The platform will mark the
    connection as authorised when the user completes the flow.  For
    this simplified implementation authorisation occurs when the
    client polls the connection status.
    """
    # 使用服务层的共同逻辑
    db_conn = AuthService.create_connection(db, current_user, payload.toolkit, payload.user_id)
    
    return CreateConnectionResponse(
        connection_id=db_conn.connection_id,
        redirect_url=db_conn.redirect_url,
        status=db_conn.status,
    )

@sdk_router.get("/auth/connections/{connection_id}", response_model=ConnectionStatusResponse)
def get_connection_status_sdk(connection_id: str, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Check the status of a connection (SDK version).

    Poll this endpoint to determine when the user has finished the
    third‑party authentication flow.  When the status transitions to
    ``authorized`` a connected account record will have been
    created.
    """
    # 使用服务层的共同逻辑
    db_conn = AuthService.get_connection_status(db, current_user, connection_id)
    
    return ConnectionStatusResponse(
        connection_id=connection_id,
        status=db_conn.status,
        connected_account_id=str(db_conn.connected_account_id_fk) if db_conn.connected_account_id_fk else None,
    )

@gui_router.post("/auth/connections", response_model=CreateConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection_gui(payload: CreateConnectionRequest, current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """Initiate a connection for a toolkit (GUI version with JWT auth)."""
    # 使用服务层的共同逻辑
    db_conn = AuthService.create_connection(db, current_user, payload.toolkit, payload.user_id)
    
    return CreateConnectionResponse(
        connection_id=db_conn.connection_id,
        redirect_url=db_conn.redirect_url,
        status=db_conn.status,
    )

@gui_router.get("/auth/connections/{connection_id}", response_model=ConnectionStatusResponse)
def get_connection_status_gui(connection_id: str, current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """Check the status of a connection (GUI version with JWT auth)."""
    # 使用服务层的共同逻辑
    db_conn = AuthService.get_connection_status(db, current_user, connection_id)
    
    return ConnectionStatusResponse(
        connection_id=connection_id,
        status=db_conn.status,
        connected_account_id=str(db_conn.connected_account_id_fk) if db_conn.connected_account_id_fk else None,
    )

@gui_router.get("/auth/connected-accounts", response_model=list[ConnectedAccountOut])
def list_connected_accounts_gui(user_id: str, toolkit: str | None = None, current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """List all connected accounts for a user (GUI version with JWT auth)."""
    # 使用服务层的共同逻辑
    accounts = AuthService.list_connected_accounts(db, current_user, user_id, toolkit)
    
    return [
        ConnectedAccountOut(
            id=str(acc.id),
            user_id=current_user.user_id,
            toolkit=acc.toolkit,
            display_name=acc.display_name,
            status="active",
        )
        for acc in accounts
    ]

@gui_router.delete("/auth/connected-accounts/{connected_account_id}", response_model=ConnectedAccountOut)
def revoke_connected_account_gui(connected_account_id: str, current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """Revoke (delete) a connected account (GUI version with JWT auth)."""
    # 使用服务层的共同逻辑
    acc = AuthService.revoke_connected_account(db, current_user, connected_account_id)
    
    return ConnectedAccountOut(
        id=str(acc.id),
        user_id=current_user.user_id,
        toolkit=acc.toolkit,
        display_name=acc.display_name,
        status="revoked",
    )


@sdk_router.get("/auth/connected-accounts", response_model=list[ConnectedAccountOut])
def list_connected_accounts_sdk(user_id: str, toolkit: str | None = None, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """List all connected accounts for a user (SDK version)."""
    # 使用服务层的共同逻辑
    accounts = AuthService.list_connected_accounts(db, current_user, user_id, toolkit)
    
    return [
        ConnectedAccountOut(
            id=str(acc.id),
            user_id=current_user.user_id,
            toolkit=acc.toolkit,
            display_name=acc.display_name,
            status="active",
        )
        for acc in accounts
    ]


@sdk_router.delete("/auth/connected-accounts/{connected_account_id}", response_model=ConnectedAccountOut)
def revoke_connected_account_sdk(connected_account_id: str, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Revoke (delete) a connected account (SDK version).

    Only the owning user may revoke their account.  Returns the
    deleted record.
    """
    # 使用服务层的共同逻辑
    acc = AuthService.revoke_connected_account(db, current_user, connected_account_id)
    
    return ConnectedAccountOut(
        id=str(acc.id),
        user_id=current_user.user_id,
        toolkit=acc.toolkit,
        display_name=acc.display_name,
        status="revoked",
    )


@common_router.post("/login", response_model=TokenResponse)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = AuthService.authenticate_user(db, user_data)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 生成访问令牌
    access_token, expires_in = create_access_token(data={"sub": user.user_id})
    
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.from_orm(user)
    )


# =============================================================================
# SDK Router (API Key Authentication)
# =============================================================================

sdk_router = APIRouter(prefix="/v1/sdk", tags=["auth-sdk"])

@gui_router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: ApiKeyCreateRequest,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Create a new API key for the authenticated user (GUI version)."""
    # Check user's API key limit
    existing_keys = db.query(m.ApiKey).filter(
        m.ApiKey.user_id_fk == current_user.id,
        m.ApiKey.is_active == True
    ).count()
    
    if existing_keys >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of API keys (5) reached"
        )
    
    # Generate new API key with prefix
    raw_key = generate_api_key(prefix=request.prefix)
    key_hash = hash_api_key(raw_key)
    
    # Create API key record
    db_api_key = m.ApiKey(
        user_id_fk=current_user.id,
        public_id=generate_public_id(),
        label=request.label,
        secret_hash=key_hash,
        prefix=request.prefix,
        is_active=True
    )
    db.add(db_api_key)
    db.commit()
    db.refresh(db_api_key)
    
    return ApiKeyResponse(
        id=db_api_key.id,
        name=db_api_key.label,
        key=raw_key,  # Only returned once
        key_preview=mask_key(raw_key),
        is_active=db_api_key.is_active,
        created_at=db_api_key.created_at,
        last_used_at=db_api_key.last_used_at
    )


@gui_router.get("/api-keys", response_model=list[ApiKeyListResponse])
def list_api_keys(
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """List all API keys for the authenticated user (GUI version)."""
    api_keys = db.query(m.ApiKey).filter(
        m.ApiKey.user_id_fk == current_user.id
    ).order_by(m.ApiKey.created_at.desc()).all()
    
    return [
        ApiKeyListResponse(
            id=key.id,
            public_id=key.public_id,
            label=key.label,
            prefix=key.prefix,
            key_preview=mask_key(f"{key.prefix}_{'*' * 32}"),
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at
        )
        for key in api_keys
    ]


@gui_router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Revoke (deactivate) an API key (GUI version)."""
    api_key = db.query(m.ApiKey).filter(
        m.ApiKey.id == key_id,
        m.ApiKey.user_id_fk == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Deactivate the key
    api_key.is_active = False
    db.commit()
    
    return None


@gui_router.delete("/api-keys/{key_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_deactivated_api_key(
    key_id: int,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Permanently remove a deactivated API key (GUI version)."""
    api_key = db.query(m.ApiKey).filter(
        m.ApiKey.id == key_id,
        m.ApiKey.user_id_fk == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check if the key is already deactivated
    if api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove active API key. Please revoke it first."
        )
    
    # Permanently delete the key
    db.delete(api_key)
    db.commit()
    
    return None


@gui_router.get("/me", response_model=UserResponse)
def get_current_user(current_user: m.User = Depends(current_user_from_jwt)):
    """获取当前登录用户的信息 (GUI version)"""
    return UserResponse.from_orm(current_user)


# =============================================================================
# OAuth Authentication Endpoints
# =============================================================================

@common_router.get("/oauth/providers", response_model=List[OAuthProviderResponse])
def get_oauth_providers(db: Session = Depends(get_db)):
    """获取可用的OAuth提供商列表"""
    providers = db.query(m.OAuthProvider).filter(m.OAuthProvider.is_active == True).all()
    return [OAuthProviderResponse.from_orm(provider) for provider in providers]


@common_router.post("/oauth/auth", response_model=OAuthAuthResponse)
def initiate_oauth_auth(request: OAuthAuthRequest, db: Session = Depends(get_db)):
    """发起OAuth认证"""
    try:
        auth_url, state = OAuthService.generate_auth_url(
            db=db,
            provider_name=request.provider,
            redirect_uri=request.redirect_uri
        )
        return OAuthAuthResponse(auth_url=auth_url, state=state)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# 用于存储已处理的授权码，防止重复使用
_processed_codes = set()

@common_router.post("/oauth/callback", response_model=TokenResponse)
async def oauth_callback(request: OAuthCallbackRequest, db: Session = Depends(get_db)):
    """处理OAuth回调"""
    # 防止授权码重复使用
    if request.code in _processed_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has already been used"
        )
    
    try:
        # 交换访问令牌 - 使用默认redirect_uri，因为OAuthCallbackRequest中没有这个字段
        token_data = await OAuthService.exchange_code_for_token(
            db=db,
            provider_name=request.provider,
            code=request.code,
            redirect_uri="http://localhost:3000/auth/callback"
        )
        
        # 获取用户信息
        oauth_user_info = await OAuthService.get_user_info(
            db=db,
            provider_name=request.provider,
            access_token=token_data["access_token"]
        )
        
        # 查找现有用户
        user = OAuthService.find_user_by_oauth(db, request.provider, oauth_user_info.oauth_user_id)
        
        if user:
            # 更新OAuth账户信息
            OAuthService.create_or_update_oauth_account(
                db=db,
                user_id=user.id,
                provider_name=request.provider,
                oauth_user_info=oauth_user_info,
                token_data=token_data
            )
        else:
            # 创建新用户
            user = AuthService.create_user(
                db=db,
                user_create=UserCreate(
                    email=oauth_user_info.email,
                    password="oauth_user_no_password"  # OAuth用户不需要密码
                )
            )
            
            # 创建OAuth账户关联
            OAuthService.create_or_update_oauth_account(
                db=db,
                user_id=user.id,
                provider_name=request.provider,
                oauth_user_info=oauth_user_info,
                token_data=token_data
            )
        
        # 标记授权码为已使用
        _processed_codes.add(request.code)
        
        # 生成JWT令牌
        access_token, expires_in = create_access_token(data={"sub": user.user_id})
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserResponse.from_orm(user)
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed"
        )


@gui_router.get("/oauth/accounts", response_model=List[UserOAuthAccountResponse])
def get_user_oauth_accounts(current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """获取当前用户的OAuth账户列表"""
    oauth_accounts = OAuthService.get_user_oauth_accounts(db, current_user.id)
    
    result = []
    for account in oauth_accounts:
        result.append(UserOAuthAccountResponse(
            id=account.id,
            provider_name=account.provider.name,
            provider_display_name=account.provider.display_name,
            oauth_user_id=account.oauth_user_id,
            email=account.email or "",
            display_name=account.display_name or "",
            avatar_url=account.avatar_url,
            is_primary=account.is_primary,
            created_at=account.created_at
        ))
    
    return result


@gui_router.delete("/oauth/accounts/{account_id}")
def remove_oauth_account(account_id: int, current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """移除OAuth账户关联"""
    oauth_account = db.query(m.UserOAuthAccount).filter(
        m.UserOAuthAccount.id == account_id,
        m.UserOAuthAccount.user_id_fk == current_user.id
    ).first()
    
    if not oauth_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth账户不存在"
        )
    
    # 检查是否为主要登录方式且用户没有密码
    if oauth_account.is_primary and not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法移除主要登录方式，请先设置密码或添加其他登录方式"
        )
    
    db.delete(oauth_account)
    db.commit()
    
    return {"message": "OAuth账户已移除"}