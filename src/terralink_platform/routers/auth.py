"""Routes related to user registration and account connections."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, Header, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..models import (
    Connection, ConnectedAccount, User, UserCreate, UserResponse, 
    TokenResponse, ApiKeyCreate, ApiKeyResponse, ApiKeyListResponse, UserLogin
)
from ..db.session import get_db
from ..db import models as m
from ..security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
    generate_api_key,
    generate_public_id,
    hash_api_key,
    validate_password_strength,
    mask_key
)
from ..services.auth_service import (
    verify_api_key,
    create_user,
    authenticate_user,
    get_current_user_from_api_key,
    create_user_api_key
)
from .deps import current_user_from_api_key, current_user_from_jwt
from ..rate_limit import check_auth_rate_limit


router = APIRouter(prefix="/v1", tags=["auth"])


# Security scheme for API key authentication
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with username, email and password.
    
    Returns user information and automatically creates an API key.
    """
    # Check rate limit
    check_auth_rate_limit(request)
    
    # Validate password strength
    is_valid, message = validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # Create new user using service
    db_user = create_user(db, user_data)
    
    # Create default API key using service
    db_api_key = create_user_api_key(db, db_user.id, "Default API Key")
    
    return UserResponse(
        id=db_user.id,
        user_id=db_user.user_id,
        email=db_user.email,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
        api_key=db_api_key.key  # Return the raw API key only once
    )


class CreateConnectionRequest(BaseModel):
    toolkit: str
    user_id: str


class CreateConnectionResponse(BaseModel):
    connection_id: str
    redirect_url: str
    status: str


@router.post("/auth/connections", response_model=CreateConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: CreateConnectionRequest, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Initiate an OAuth connection for a toolkit.

    Returns a connection identifier and a redirect URL which the
    client should open in a browser.  The platform will mark the
    connection as authorised when the user completes the flow.  For
    this simplified implementation authorisation occurs when the
    client polls the connection status.
    """
    # Verify user ID matches authenticated user
    if current_user.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")
    
    # Create connection in database
    db_conn = m.AuthConnection(
        user_id_fk=current_user.id,
        toolkit=payload.toolkit,
        redirect_url=f"https://auth.example.com/{uuid.uuid4()}",
        status="pending"
    )
    db.add(db_conn)
    db.commit()
    db.refresh(db_conn)
    
    # Create response model
    conn = Connection(
        id=str(db_conn.id),
        user_id=payload.user_id,
        toolkit=payload.toolkit,
        redirect_url=db_conn.redirect_url,
        status=db_conn.status
    )
    return CreateConnectionResponse(
        connection_id=conn.id,
        redirect_url=conn.redirect_url,
        status=conn.status,
    )


class ConnectionStatusResponse(BaseModel):
    connection_id: str
    status: str
    connected_account_id: str | None = None


@router.get("/auth/connections/{connection_id}", response_model=ConnectionStatusResponse)
def get_connection_status(connection_id: str, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Check the status of a connection.

    Poll this endpoint to determine when the user has finished the
    third‑party OAuth flow.  When the status transitions to
    ``authorized`` a connected account record will have been
    created.
    """
    db_conn = db.query(m.AuthConnection).filter_by(id=int(connection_id)).first()
    if db_conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    # Only allow the owning user to query
    if db_conn.user_id_fk != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to view this connection")
    
    # Simulate user completing OAuth on first poll
    if db_conn.status == "pending":
        # Create connected account
        display_name = f"{db_conn.toolkit} account for {current_user.user_id}"
        db_acc = m.ConnectedAccount(
            user_id_fk=current_user.id,
            toolkit=db_conn.toolkit,
            display_name=display_name,
            token_enc=secrets.token_hex(8)  # In production, this should be encrypted
        )
        db.add(db_acc)
        db_conn.status = "authorized"
        db_conn.connected_account_id = db_acc.id
        db.commit()
        db.refresh(db_acc)
    
    return ConnectionStatusResponse(
        connection_id=str(db_conn.id),
        status=db_conn.status,
        connected_account_id=str(db_conn.connected_account_id) if db_conn.connected_account_id else None,
    )


class ConnectedAccountOut(BaseModel):
    id: str
    user_id: str
    toolkit: str
    display_name: str
    status: str


@router.get("/auth/connected-accounts", response_model=list[ConnectedAccountOut])
def list_connected_accounts(user_id: str, toolkit: str | None = None, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """List all connected accounts for a user.

    The API key must belong to the given user.  Optionally filter
    by toolkit name.
    """
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")
    
    query = db.query(m.ConnectedAccount).filter_by(user_id_fk=current_user.id)
    if toolkit:
        query = query.filter_by(toolkit=toolkit)
    accounts = query.all()
    
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


@router.delete("/auth/connected-accounts/{connected_account_id}", response_model=ConnectedAccountOut)
def revoke_connected_account(connected_account_id: str, current_user: m.User = Depends(current_user_from_api_key), db: Session = Depends(get_db)):
    """Revoke (delete) a connected account.

    Only the owning user may revoke their account.  Returns the
    deleted record.
    """
    acc = db.query(m.ConnectedAccount).filter_by(id=int(connected_account_id)).first()
    if acc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected account not found")
    if acc.user_id_fk != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to remove this account")
    
    # Store info before deletion
    result = ConnectedAccountOut(
        id=str(acc.id),
        user_id=current_user.user_id,
        toolkit=acc.toolkit,
        display_name=acc.display_name,
        status="revoked",
    )
    
    db.delete(acc)
    db.commit()
    
    return result


# JWT Authentication Endpoints

@router.post("/login", response_model=TokenResponse)
def login_user(request: Request, user_data: UserLogin, db: Session = Depends(get_db)):
    """Login user with email/username and password, returns JWT token."""
    # Check rate limit
    check_auth_rate_limit(request)
    
    # Authenticate user
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Create JWT token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=30 * 60,  # 30 minutes
        user=UserResponse(
            id=user.id,
            user_id=user.user_id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=None
        )
    )


# API Key Management Endpoints

class ApiKeyCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    prefix: str = Field(default="live", pattern="^(test|live)$")


class ApiKeyListResponse(BaseModel):
    id: int
    public_id: str
    label: str
    prefix: str
    key_preview: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: ApiKeyCreateRequest,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Create a new API key for the authenticated user."""
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


@router.get("/api-keys")
def list_api_keys(
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """List all API keys for the authenticated user."""
    api_keys = db.query(m.ApiKey).filter(
        m.ApiKey.user_id_fk == current_user.id
    ).order_by(m.ApiKey.created_at.desc()).all()
    
    result = []
    for key in api_keys:
        result.append({
            "id": key.id,
            "public_id": key.public_id,
            "label": key.label,
            "prefix": key.prefix,
            "key_preview": f"tlk_{key.prefix}_{'*' * 8}...****",
            "is_active": key.is_active,
            "created_at": key.created_at.isoformat(),
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None
        })
    
    return result


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Revoke (deactivate) an API key."""
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
