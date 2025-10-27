"""Routes for toolkits and tool execution."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db import models as m
from .factory import RouterConfig, SDK_CONFIG, GUI_CONFIG
from .deps import current_user_from_api_key, current_user_from_jwt
from ..core.schemas import (
    ToolSpecOut, ToolkitOut, ExecuteRequestIn, ExecuteResponseOut,
)
from ..core.services import ToolService


# Business logic helpers (shared between SDK/GUI)

def _get_tools_with_status(db: Session, user_id: str) -> list[ToolSpecOut]:
    return ToolService.get_tools_with_status(db, user_id)


def _get_tool_with_status_or_404(db: Session, user_id: str, slug: str) -> ToolSpecOut:
    tool = ToolService.get_tool_with_status(db, user_id, slug)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )
    return tool


def _get_toolkits_with_status(db: Session, user_id: str) -> list[ToolkitOut]:
    return ToolService.get_toolkits_with_status(db, user_id)


async def _execute_tool(db: Session, user_id: str, slug: str, request: ExecuteRequestIn) -> ExecuteResponseOut:
    return await ToolService.execute_tool(db, user_id, slug, request)


# =============================================================================
# Router Factory Implementation
# =============================================================================

def make_tools_router(config: RouterConfig) -> APIRouter:
    """Create a tools router with the specified configuration.
    
    Args:
        config: Router configuration (prefix, auth dependency, etc.)
        
    Returns:
        Configured APIRouter with all tools endpoints
    """
    router = APIRouter(
        prefix=config.prefix,
        tags=[f"tools-{config.prefix.split('/')[-1]}"]
    )
    
    @router.get("/tools", response_model=list[ToolSpecOut])
    def get_tools(
        toolkit: str | None = None,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get all tools with their availability status."""
        return _get_tools_with_status(db, current_user.user_id)

    @router.get("/tools/{slug}", response_model=ToolSpecOut)
    def get_tool_detail(
        slug: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get a specific tool with its availability status."""
        return _get_tool_with_status_or_404(db, current_user.user_id, slug)

    @router.get("/toolkits", response_model=list[ToolkitOut])
    def get_toolkits(
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get all toolkits with their tools' availability status."""
        return _get_toolkits_with_status(db, current_user.user_id)

    @router.post("/tools/{slug}/execute", response_model=ExecuteResponseOut)
    async def execute_tool(
        slug: str,
        request: ExecuteRequestIn,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Execute a tool."""
        return await _execute_tool(db, current_user.user_id, slug, request)
    
    return router


# =============================================================================
# Create SDK and GUI routers using factory
# =============================================================================

# Create SDK router (API Key authentication)
sdk_router = make_tools_router(SDK_CONFIG)

# Create GUI router (JWT authentication)  
gui_router = make_tools_router(GUI_CONFIG)


# Export routers for main app
__all__ = ["sdk_router", "gui_router", "make_tools_router"]
