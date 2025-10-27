"""Routes related to user registration and account connections."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from ..core.schemas import (
    UserCreate, UserResponse, TokenResponse, ApiKeyCreate, ApiKeyResponse, 
    ApiKeyListResponse, UserLogin, OAuthProviderResponse, OAuthAuthRequest, 
    OAuthAuthResponse, OAuthCallbackRequest, UserOAuthAccountResponse,
    ApiKeyCreateRequest
)
from pydantic import BaseModel
from ..db.session import get_db
from ..db import models as m
from ..core.utils.auth import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    validate_password_strength,
    generate_public_id
)
from ..core.security import DataMasking
from ..core.services import AuthService
from ..core.oauth_service import OAuthService
from ..core.utils.config import settings
from .deps import current_user_from_api_key, current_user_from_jwt
from ..core.utils.rate_limit import auth_rate_limiter





# =============================================================================
# GUI Router (JWT Authentication)
# =============================================================================

gui_router = APIRouter(prefix="/v1/gui", tags=["auth-gui"])



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

# Legacy connection endpoints removed - use /v1/connections instead


@common_router.post("/login", response_model=TokenResponse)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """User login"""
    user = AuthService.authenticate_user(db, user_data)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate access token
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
        key_preview=DataMasking.mask_api_key(raw_key),
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
            key_preview=DataMasking.mask_api_key(f"{key.prefix}_{'*' * 32}"),
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
    """Get current logged-in user information (GUI version)"""
    return UserResponse.from_orm(current_user)


# =============================================================================
# OAuth Authentication Endpoints
# =============================================================================

@common_router.get("/oauth/providers", response_model=List[OAuthProviderResponse])
def get_oauth_providers():
    """Get list of available OAuth providers"""
    providers = OAuthService.get_available_providers()
    return [OAuthProviderResponse(**provider) for provider in providers]


@common_router.post("/oauth/auth", response_model=OAuthAuthResponse)
def initiate_oauth_auth(request: OAuthAuthRequest):
    """Initiate OAuth authentication"""
    try:
        auth_url, state = OAuthService.generate_auth_url(
            provider_name=request.provider,
            redirect_uri=request.redirect_uri
        )
        return OAuthAuthResponse(auth_url=auth_url, state=state)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Used to store processed authorization codes to prevent reuse
_processed_codes = set()

@common_router.post("/oauth/callback", response_model=TokenResponse)
async def oauth_callback(request: OAuthCallbackRequest, db: Session = Depends(get_db)):
    """Handle OAuth callback"""
    # Prevent authorization code reuse
    if request.code in _processed_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has already been used"
        )
    
    try:
        # Exchange access token - use provided redirect_uri or default from environment
        redirect_uri = request.redirect_uri or settings.OAUTH_REDIRECT_URI
        token_data = await OAuthService.exchange_code_for_token(
            provider_name=request.provider,
            code=request.code,
            redirect_uri=redirect_uri
        )
        
        # Get user information
        oauth_user_info = await OAuthService.get_user_info(
            provider_name=request.provider,
            access_token=token_data["access_token"]
        )
        
        # Find existing user
        user = OAuthService.find_user_by_oauth(db, request.provider, oauth_user_info.oauth_user_id)
        
        if user:
            # Update OAuth account information
            OAuthService.create_or_update_oauth_account(
                db=db,
                user_id=user.id,
                provider_name=request.provider,
                oauth_user_info=oauth_user_info,
                token_data=token_data
            )
        else:
            # Create new user
            user = AuthService.create_user(
                db=db,
                user_create=UserCreate(
                    email=oauth_user_info.email,
                    password="oauth_user_no_password"  # OAuth users don't need password
                )
            )
            
            # Create OAuth account association
            OAuthService.create_or_update_oauth_account(
                db=db,
                user_id=user.id,
                provider_name=request.provider,
                oauth_user_info=oauth_user_info,
                token_data=token_data
            )
        
        # Mark authorization code as used
        _processed_codes.add(request.code)
        
        # Generate JWT token
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
    except HTTPException:
        # Re-raise HTTPExceptions from OAuth service
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"OAuth callback error for provider {request.provider}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth authentication failed: {str(e)}"
        )


@gui_router.get("/oauth/accounts", response_model=List[UserOAuthAccountResponse])
def get_user_oauth_accounts(current_user: m.User = Depends(current_user_from_jwt), db: Session = Depends(get_db)):
    """Get current user's OAuth account list"""
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
    """Remove OAuth account association"""
    oauth_account = db.query(m.UserOAuthAccount).filter(
        m.UserOAuthAccount.id == account_id,
        m.UserOAuthAccount.user_id_fk == current_user.id
    ).first()
    
    if not oauth_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth account does not exist"
        )
    
    # Check if it's the primary login method and user has no password
    if oauth_account.is_primary and not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove primary login method, please set a password or add other login methods first"
        )
    
    db.delete(oauth_account)
    db.commit()
    
    return {"message": "OAuth account has been removed"}


# Export routers for main app
__all__ = ["common_router", "sdk_router", "gui_router", "make_auth_router"]