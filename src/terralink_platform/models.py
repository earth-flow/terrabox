"""Core data models for the Terralink platform.

These classes define the fundamental entities that the platform
manages. They are deliberately lightweight and use Pydantic
for runtime validation.  Persistence is handled in the in-memory
store defined in :mod:`terralink_platform.data`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    """A registered user of the platform.

    Parameters
    ----------
    user_id:
        A stable identifier for the user.  This should correspond to
        whatever identifier the client SDK uses to scope data.
    email:
        The user's email address, used for authentication and communication.
    api_key:
        An opaque API key assigned to the user.  This must be
        provided in the ``X-API-Key`` header for authenticated
        requests.
    """

    user_id: str
    email: EmailStr
    password: str


class Connection(BaseModel):
    """Represents an OAuth connection attempt.

    When a user wants to connect a toolkit (e.g. GitHub) to their
    account they initiate a connection.  The platform generates
    a connection identifier and redirect URL.  Once the user has
    completed the third‑party OAuth flow the connection transitions
    from ``pending`` to ``authorized`` and a connected account is
    created.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    toolkit: str
    status: str = Field(default="pending")
    connected_account_id: Optional[str] = None
    redirect_url: str = Field(default_factory=str)


class ConnectedAccount(BaseModel):
    """Represents a third‑party account connected to a user.

    Each connected account corresponds to a specific toolkit (e.g.
    GitHub) and contains any additional metadata or credentials
    required to perform authenticated operations.  In this
    simplified implementation the ``token`` field is merely a
    placeholder; in a real platform this would hold encrypted
    access/refresh tokens.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    toolkit: str
    display_name: str
    token: Optional[str] = None


class ToolSpec(BaseModel):
    """Describes a tool that can be executed by the platform.

    The Terralink SDK retrieves these specifications and uses
    them to render the proper function signature for LLMs.  See
    :mod:`terralink_platform.tools` for predefined tool specs.
    """

    slug: str
    description: str
    parameters: Dict[str, Any]
    toolkit: str
    requires_connection: bool = False


class ExecutionContext(BaseModel):
    """Execution context for tool calls.
    
    Provides structured access to user and connection information
    while maintaining backward compatibility with Dict[str, Any].
    """
    user_id: str
    connected_account_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ExecuteRequest(BaseModel):
    """Payload for executing a tool.

    This structure matches the schema expected by the Terralink
    SDK when invoking ``POST /v1/tools/{slug}/execute``.  The
    ``arguments`` key contains the tool parameters and ``context``
    indicates the user and optional connected account under which
    the tool should run.
    """

    arguments: Dict[str, Any]
    context: Dict[str, Any]  # Can be parsed as ExecutionContext


class ExecuteResponse(BaseModel):
    """Standardised response from a tool execution.

    ``ok`` indicates whether the call was successful.  If
    ``ok`` is ``False`` an error message may be provided in
    ``error``.  A ``trace_id`` may be included for audit and
    observability purposes.
    """

    ok: bool
    data: Any = None
    error: Optional[str] = None
    trace_id: Optional[str] = None


class Toolkit(BaseModel):
    """Metadata describing a toolkit.

    The platform can group related tools into toolkits (e.g.
    ``github``).  This model contains basic descriptive fields.
    """

    name: str
    description: str
    version: str = "1.0"


# User Authentication Models

class UserCreate(BaseModel):
    """Schema for user registration."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")


class UserLogin(BaseModel):
    """Schema for user login."""
    email: str  # User email for login
    password: str


class UserResponse(BaseModel):
    """Schema for user response (without sensitive data)."""
    id: int
    user_id: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    api_key: Optional[str] = None  # Only returned during registration

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse


class ApiKeyCreate(BaseModel):
    """Schema for API key creation."""
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyResponse(BaseModel):
    """Schema for API key response."""
    id: int
    name: str
    key: Optional[str] = None  # Only returned once during creation
    key_preview: str  # First 8 characters + "..."
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    """Schema for API key list response."""
    id: int
    public_id: str
    label: Optional[str] = None
    prefix: str
    key_preview: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# OAuth Models

class OAuthProviderResponse(BaseModel):
    """OAuth提供商信息响应"""
    id: int
    name: str
    display_name: str
    auth_url: str
    scopes: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True

class OAuthAuthRequest(BaseModel):
    """OAuth认证请求"""
    provider: str = Field(..., description="OAuth提供商名称 (google, github)")
    redirect_uri: Optional[str] = Field(None, description="认证成功后的重定向URI")

class OAuthAuthResponse(BaseModel):
    """OAuth认证响应"""
    auth_url: str = Field(..., description="OAuth认证URL")
    state: str = Field(..., description="状态参数，用于防止CSRF攻击")

class OAuthCallbackRequest(BaseModel):
    """OAuth回调请求"""
    provider: str = Field(..., description="OAuth提供商名称")
    code: str = Field(..., description="授权码")
    state: str = Field(..., description="状态参数")

class OAuthUserInfo(BaseModel):
    """OAuth用户信息"""
    oauth_user_id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None

class UserOAuthAccountResponse(BaseModel):
    """用户OAuth账户响应"""
    id: int
    provider_name: str
    provider_display_name: str
    oauth_user_id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    is_primary: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Rebuild models to ensure they are fully defined
ApiKeyListResponse.model_rebuild()
OAuthProviderResponse.model_rebuild()
UserOAuthAccountResponse.model_rebuild()
