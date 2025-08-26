"""Routes for toolkits and tool execution."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db import models as m
from .deps import current_user_from_api_key, current_user_from_jwt
from ..core.schemas import (
    ToolSpecOut, ToolkitOut, ExecuteRequestIn, ExecuteResponseOut,
)
from ..core.services import ToolService


# =============================================================================
# SDK Router (API Key Authentication)
# =============================================================================

sdk_router = APIRouter(prefix="/v1/sdk", tags=["tools-sdk"])


@sdk_router.get("/tools", response_model=list[ToolSpecOut])
def get_tools_sdk(
    toolkit: str | None = None,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get all tools with their availability status (SDK version)."""
    return ToolService.get_tools_with_status(db, current_user.user_id)


@sdk_router.get("/tools/{slug}", response_model=ToolSpecOut)
def get_tool_detail_sdk(
    slug: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get a specific tool with its availability status (SDK version)."""
    tool = ToolService.get_tool_with_status(db, current_user.user_id, slug)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )
    return tool


@sdk_router.get("/toolkits", response_model=list[ToolkitOut])
def get_toolkits_sdk(
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get all toolkits with their tools' availability status (SDK version)."""
    return ToolService.get_toolkits_with_status(db, current_user.user_id)


@sdk_router.post("/tools/{slug}/execute", response_model=ExecuteResponseOut)
async def execute_tool_sdk(
    slug: str,
    request: ExecuteRequestIn,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Execute a tool (SDK version)."""
    return await ToolService.execute_tool(db, current_user.user_id, slug, request)


# =============================================================================
# GUI Router (JWT Authentication)
# =============================================================================

gui_router = APIRouter(prefix="/v1/gui", tags=["tools-gui"])


@gui_router.get("/tools", response_model=list[ToolSpecOut])
def get_tools_gui(
    toolkit: str | None = None,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get all tools with their availability status (GUI version)."""
    return ToolService.get_tools_with_status(db, current_user.user_id)


@gui_router.get("/tools/{slug}", response_model=ToolSpecOut)
def get_tool_detail_gui(
    slug: str,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get a specific tool with its availability status (GUI version)."""
    tool = ToolService.get_tool_with_status(db, current_user.user_id, slug)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )
    return tool


@gui_router.get("/toolkits", response_model=list[ToolkitOut])
def get_toolkits_gui(
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get all toolkits with their tools' availability status (GUI version)."""
    return ToolService.get_toolkits_with_status(db, current_user.user_id)


@gui_router.post("/tools/{slug}/execute", response_model=ExecuteResponseOut)
async def execute_tool_gui(
    slug: str,
    request: ExecuteRequestIn,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Execute a tool (GUI version)."""
    return await ToolService.execute_tool(db, current_user.user_id, slug, request)


# Export routers for main app
__all__ = ["sdk_router", "gui_router"]
