"""API request and response schemas."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# Tool-related schemas
class ToolSpecOut(BaseModel):
    """Tool specification output schema."""
    slug: str
    name: str
    description: str
    requires_connection: bool
    status: str = "available"  # available, unavailable
    toolkit_slug: Optional[str] = None
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
    connected_account_id: Optional[str] = None
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


class ConnectedAccountOut(BaseModel):
    """Connected account output schema."""
    id: str
    user_id: str
    toolkit: str
    display_name: str
    status: str


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