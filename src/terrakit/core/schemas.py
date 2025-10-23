"""API request and response schemas."""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, UUID4
from datetime import datetime
from enum import Enum


# OAuth-related schemas
class OAuthUserInfo(BaseModel):
    """OAuth user information model"""
    oauth_user_id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


# User-related schemas
class UserCreate(BaseModel):
    """User creation request model"""
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    """User login request model"""
    email: str
    password: str


class UserResponse(BaseModel):
    """User response model"""
    id: str
    user_id: str
    email: str
    is_active: bool
    created_at: datetime
    api_key: Optional[str] = None  # Only returned once during registration

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=str(obj.id),
            user_id=obj.user_id,
            email=obj.email,
            is_active=obj.is_active,
            created_at=obj.created_at
        )


class TokenResponse(BaseModel):
    """JWT token response model"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class ApiKeyCreate(BaseModel):
    """API key creation request model"""
    label: str = Field(..., min_length=1, max_length=100)
    prefix: str = Field(default="live", pattern="^(test|live)$")


class ApiKeyResponse(BaseModel):
    """API key response model"""
    id: int
    name: str
    key: Optional[str] = None  # Only returned once during creation
    key_preview: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class OAuthProviderResponse(BaseModel):
    """OAuth provider response model"""
    id: int
    name: str
    display_name: str
    auth_url: str
    scopes: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            name=obj.name,
            display_name=obj.display_name,
            auth_url=obj.auth_url,
            scopes=obj.scopes,
            is_active=obj.is_active
        )


class OAuthAuthRequest(BaseModel):
    """OAuth authentication request model"""
    provider: str
    redirect_uri: str
    state: Optional[str] = None


class OAuthAuthResponse(BaseModel):
    """OAuth authentication response model"""
    auth_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request model"""
    provider: str
    code: str
    state: Optional[str] = None


class UserOAuthAccountResponse(BaseModel):
    """User OAuth account response model"""
    id: int
    provider_name: str
    provider_display_name: str
    oauth_user_id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    is_primary: bool
    created_at: datetime


# Tool-related schemas
class ToolSpecOut(BaseModel):
    """Tool specification output model"""
    slug: str
    name: str
    description: str
    requires_connection: bool
    status: str = "available"  # available, unavailable
    toolkit_slug: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ToolkitOut(BaseModel):
    """Toolkit output schema."""
    slug: str
    name: str
    description: str
    tools: List[ToolSpecOut] = []
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ExecuteRequestIn(BaseModel):
    """Tool execution request schema."""
    inputs: Dict[str, Any]
    connection_id: Optional[str] = None  # New connection-based approach
    connected_account_id: Optional[str] = None  # Legacy support
    metadata: Optional[Dict[str, Any]] = None


class ExecuteResponseOut(BaseModel):
    """Tool execution response schema."""
    success: bool
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Connection-related schemas
class ConnectionStatusOut(BaseModel):
    """Connection status output schema."""
    connection_id: str
    toolkit_slug: str
    status: str  # pending, connected, failed
    connected_account_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Pagination schemas
class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = 1
    size: int = 20
    
    class Config:
        validate_assignment = True


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int


# Authentication-related schemas
class CreateConnectionRequest(BaseModel):
    """Request to create a new OAuth connection."""
    toolkit: str
    user_id: str


class CreateConnectionResponse(BaseModel):
    """Response for creating a new OAuth connection."""
    connection_id: str
    redirect_url: str
    status: str


class ConnectionStatusResponse(BaseModel):
    """Response for connection status check."""
    connection_id: str
    status: str
    connected_account_id: Optional[str] = None


# Legacy ConnectedAccountOut removed - using new Connection-based models instead


class ApiKeyCreateRequest(BaseModel):
    """Request to create a new API key."""
    label: str = Field(..., min_length=1, max_length=100)
    prefix: str = Field(default="live", pattern="^(test|live)$")


class ApiKeyListResponse(BaseModel):
    """API key list item response."""
    id: int
    public_id: str
    label: str
    prefix: str
    key_preview: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


# Error schemas
class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


# Connection Management Schemas
class AuthMethodEnum(str, Enum):
    """Authentication method enum."""
    oauth2 = "oauth2"
    api_key = "api_key"
    service_account = "service_account"
    token = "token"
    none = "none"


class ConnectionStatusEnum(str, Enum):
    """Connection status enum."""
    incomplete = "incomplete"
    pending = "pending"
    valid = "valid"
    expired = "expired"
    revoked = "revoked"
    error = "error"


class ConnectionCreateRequest(BaseModel):
    """Request to create a new connection."""
    name: str = Field(..., min_length=1, max_length=100)
    auth_method: AuthMethodEnum
    credentials: Optional[Dict[str, Any]] = None
    scopes: Optional[List[str]] = None
    labels: Optional[Dict[str, Any]] = Field(default_factory=dict)
    redirect_uri: Optional[str] = None
    mcp_transport: Optional[str] = "websocket"
    mcp_endpoint_url: Optional[str] = None
    mcp_protocol_version: Optional[str] = None


class ConnectionOAuth2StartRequest(BaseModel):
    """Request to start OAuth2 flow."""
    name: str = Field(..., min_length=1, max_length=100)
    scopes: Optional[List[str]] = None
    redirect_uri: str
    labels: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ConnectionOAuth2StartResponse(BaseModel):
    """Response for OAuth2 start."""
    connection_id: str
    auth_url: str
    state: str


class ConnectionResponse(BaseModel):
    """Connection response schema (masked)."""
    id: str
    user_id: str
    toolkit_id: int
    name: str
    enabled: bool
    status: ConnectionStatusEnum
    priority: int
    labels: Dict[str, Any]
    last_used_at: Optional[datetime] = None
    auth_method: AuthMethodEnum
    scopes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    mcp_transport: Optional[str] = None
    mcp_endpoint_url: Optional[str] = None
    mcp_protocol_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Create ConnectionResponse with masked sensitive data."""
        from ..core.security import DataMasking, SecurityValidator
        
        # Convert ORM object to dict
        data = {
            'id': obj.id,
            'user_id': obj.user_id,
            'toolkit_id': obj.toolkit_id,
            'name': obj.name,
            'enabled': obj.enabled,
            'status': obj.status,
            'priority': obj.priority,
            'labels': obj.labels or {},
            'last_used_at': obj.last_used_at,
            'auth_method': obj.auth_method,
            'scopes': obj.scopes,
            'expires_at': obj.expires_at,
            'last_error': obj.last_error,
            'mcp_transport': obj.mcp_transport,
            'mcp_endpoint_url': obj.mcp_endpoint_url,
            'mcp_protocol_version': obj.mcp_protocol_version,
            'created_at': obj.created_at,
            'updated_at': obj.updated_at
        }
        
        # Sanitize error message if present
        if data['last_error']:
            data['last_error'] = SecurityValidator.sanitize_error_message(data['last_error'])
        
        return cls(**data)


class ConnectionUpdateRequest(BaseModel):
    """Request to update connection."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    labels: Optional[Dict[str, Any]] = None
    rotate_credentials: Optional[bool] = False


class ConnectionTestResponse(BaseModel):
    """Connection test response."""
    success: bool
    message: str
    tested_at: datetime


class ConnectionRefreshResponse(BaseModel):
    """Connection refresh response."""
    success: bool
    message: str
    expires_at: Optional[datetime] = None
    refreshed_at: datetime


# Tool Override Schemas
class ToolOverrideRequest(BaseModel):
    """Request to create/update tool override."""
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ToolOverrideResponse(BaseModel):
    """Tool override response."""
    id: int
    connection_id: str
    tool_key: str
    enabled: Optional[bool] = None
    config: Dict[str, Any]
    tool_version: Optional[str] = None
    resolved_digest: Optional[str] = None
    is_stale: bool

    class Config:
        from_attributes = True


class EffectiveToolResponse(BaseModel):
    """Effective tool response (merged registry + overrides)."""
    tool_key: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    enabled: bool
    config: Dict[str, Any]
    version: Optional[str] = None
    digest: Optional[str] = None
    is_stale: bool = False
    required_scopes: Optional[List[str]] = None


class EffectiveToolsResponse(BaseModel):
    """Response for effective tools with overrides applied."""
    tools: List[EffectiveToolResponse]
    orphan_overrides: List[Dict[str, Any]]
    connection_id: str
    toolkit_key: str


# App and Tool Registry Schemas
class ToolkitResponse(BaseModel):
    """Response model for toolkit data."""
    id: int
    key: str
    name: str
    description: Optional[str] = None
    toolkit_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToolDefinitionResponse(BaseModel):
    """Tool definition response from registry."""
    tool_key: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    default_enabled: bool = True
    default_config: Optional[Dict[str, Any]] = None
    required_scopes: Optional[List[str]] = None
    version: Optional[str] = None
    digest: Optional[str] = None


# MCP Manifest Schemas
class MCPManifestResponse(BaseModel):
    """MCP manifest response schema."""
    endpoint_url: str
    transport: str = "websocket"
    protocol_version: str = "2024-11-05"
    headers: Optional[Dict[str, str]] = None
    tools: List[Dict[str, Any]]


# Analytics-related schemas
class ToolExecutionResponse(BaseModel):
    """Tool execution record response schema."""
    id: int
    user_id: str
    tool_slug: str
    connection_id: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    ok: Optional[bool] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None
    input_size: Optional[int] = None
    output_size: Optional[int] = None
    cost_estimate: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        import json
        # Parse meta from JSON string if it exists
        meta_data = None
        if obj.meta:
            try:
                meta_data = json.loads(obj.meta) if isinstance(obj.meta, str) else obj.meta
            except (json.JSONDecodeError, TypeError):
                meta_data = None
        
        return cls(
            id=obj.id,
            user_id=obj.user_id_fk,  # Map user_id_fk to user_id
            tool_slug=obj.tool_slug,
            connection_id=obj.connection_id_fk,
            started_at=obj.started_at,
            finished_at=obj.finished_at,
            ok=obj.ok,
            error=obj.error,
            trace_id=obj.trace_id,
            input_size=obj.input_size,
            output_size=obj.output_size,
            cost_estimate=obj.cost_estimate,
            meta=meta_data
        )


class UserToolUsageResponse(BaseModel):
    """User tool usage statistics response schema."""
    tool_slug: str
    tool_name: Optional[str] = None
    usage_count: int
    success_count: int
    failure_count: int
    total_cost: Optional[float] = None
    last_used_at: Optional[datetime] = None


class ToolStatsResponse(BaseModel):
    """Tool statistics response schema."""
    tool_slug: str
    tool_name: Optional[str] = None
    total_executions: int
    unique_users: int
    success_rate: float
    average_cost: Optional[float] = None
    total_cost: Optional[float] = None
    last_used_at: Optional[datetime] = None


class ExecutionHistoryParams(BaseModel):
    """Execution history query parameters."""
    user_id: Optional[str] = None
    tool_slug: Optional[str] = None
    connection_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    success_only: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class UserStatsParams(BaseModel):
    """User statistics query parameters."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tool_slug: Optional[str] = None


class ToolStatsParams(BaseModel):
    """Tool statistics query parameters."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_executions: Optional[int] = Field(default=None, ge=0)
    sort_by: Optional[str] = Field(default="total_executions", pattern="^(total_executions|unique_users|success_rate|total_cost|last_used_at)$")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$")