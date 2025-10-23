"""Analytics API routes for tool execution statistics and history."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..db.session import get_db
from ..core.services.analytics_service import AnalyticsService
from ..core.schemas import (
    ToolExecutionResponse,
    UserToolUsageResponse, 
    ToolStatsResponse,
    PaginatedResponse,
    UserResponse,
    ExecutionHistoryParams,
    UserStatsParams,
    ToolStatsParams
)
from .deps import current_user_from_api_key, current_user_from_jwt

# Create routers for different authentication methods
sdk_router = APIRouter(prefix="/v1/analytics", tags=["analytics-sdk"])
gui_router = APIRouter(prefix="/v1/gui/analytics", tags=["analytics-gui"])


# SDK Routes (API Key Authentication)
@sdk_router.get("/executions", response_model=PaginatedResponse)
async def get_execution_history_sdk(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    tool_slug: Optional[str] = Query(None, description="Filter by tool slug"),
    connection_id: Optional[str] = Query(None, description="Filter by connection ID"),
    start_date: Optional[datetime] = Query(None, description="Filter executions after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter executions before this date"),
    success_only: Optional[bool] = Query(None, description="Filter only successful executions"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: UserResponse = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get paginated tool execution history with optional filters (SDK)."""
    analytics_service = AnalyticsService(db)
    
    params = ExecutionHistoryParams(
        user_id=user_id,
        tool_slug=tool_slug,
        connection_id=connection_id,
        start_date=start_date,
        end_date=end_date,
        success_only=success_only,
        page=page,
        size=size
    )
    
    return analytics_service.get_execution_history(params)


@sdk_router.get("/executions/{execution_id}", response_model=ToolExecutionResponse)
async def get_execution_by_id_sdk(
    execution_id: int,
    current_user: UserResponse = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get a specific tool execution by ID (SDK)."""
    analytics_service = AnalyticsService(db)
    
    execution = analytics_service.get_execution_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return execution


@sdk_router.get("/users/{user_id}/tool-usage", response_model=List[UserToolUsageResponse])
async def get_user_tool_usage_sdk(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="Filter usage after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter usage before this date"),
    tool_slug: Optional[str] = Query(None, description="Filter by specific tool"),
    current_user: UserResponse = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get tool usage statistics for a specific user (SDK)."""
    analytics_service = AnalyticsService(db)
    
    params = UserStatsParams(
        start_date=start_date,
        end_date=end_date,
        tool_slug=tool_slug
    )
    
    return analytics_service.get_user_tool_usage(user_id, params)


@sdk_router.get("/users/{user_id}/summary", response_model=Dict[str, Any])
async def get_user_execution_summary_sdk(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="Filter summary after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter summary before this date"),
    current_user: UserResponse = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get execution summary for a specific user (SDK)."""
    analytics_service = AnalyticsService(db)
    
    return analytics_service.get_user_execution_summary(user_id, start_date, end_date)


@sdk_router.get("/tools/stats", response_model=List[ToolStatsResponse])
async def get_tool_statistics_sdk(
    start_date: Optional[datetime] = Query(None, description="Filter stats after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter stats before this date"),
    min_executions: Optional[int] = Query(None, ge=0, description="Minimum number of executions"),
    sort_by: str = Query("total_executions", regex="^(total_executions|unique_users|success_rate|total_cost|last_used_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: UserResponse = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get tool usage statistics across all users (SDK)."""
    analytics_service = AnalyticsService(db)
    
    params = ToolStatsParams(
        start_date=start_date,
        end_date=end_date,
        min_executions=min_executions,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    return analytics_service.get_tool_statistics(params)


# GUI Routes (JWT Authentication)
@gui_router.get("/executions", response_model=PaginatedResponse)
async def get_execution_history_gui(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    tool_slug: Optional[str] = Query(None, description="Filter by tool slug"),
    connection_id: Optional[str] = Query(None, description="Filter by connection ID"),
    start_date: Optional[datetime] = Query(None, description="Filter executions after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter executions before this date"),
    success_only: Optional[bool] = Query(None, description="Filter only successful executions"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get paginated tool execution history with optional filters (GUI)."""
    analytics_service = AnalyticsService(db)
    
    # For GUI, if no user_id is specified, default to current user
    if user_id is None:
        user_id = current_user.user_id
    
    params = ExecutionHistoryParams(
        user_id=user_id,
        tool_slug=tool_slug,
        connection_id=connection_id,
        start_date=start_date,
        end_date=end_date,
        success_only=success_only,
        page=page,
        size=size
    )
    
    return analytics_service.get_execution_history(params)


@gui_router.get("/executions/{execution_id}", response_model=ToolExecutionResponse)
async def get_execution_by_id_gui(
    execution_id: int,
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get a specific tool execution by ID (GUI)."""
    analytics_service = AnalyticsService(db)
    
    execution = analytics_service.get_execution_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return execution


@gui_router.get("/my/tool-usage", response_model=List[UserToolUsageResponse])
async def get_my_tool_usage_gui(
    start_date: Optional[datetime] = Query(None, description="Filter usage after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter usage before this date"),
    tool_slug: Optional[str] = Query(None, description="Filter by specific tool"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get tool usage statistics for current user (GUI)."""
    analytics_service = AnalyticsService(db)
    
    params = UserStatsParams(
        start_date=start_date,
        end_date=end_date,
        tool_slug=tool_slug
    )
    
    return analytics_service.get_user_tool_usage(current_user.user_id, params)


@gui_router.get("/my/summary", response_model=Dict[str, Any])
async def get_my_execution_summary_gui(
    start_date: Optional[datetime] = Query(None, description="Filter summary after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter summary before this date"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get execution summary for current user (GUI)."""
    analytics_service = AnalyticsService(db)
    
    return analytics_service.get_user_execution_summary(current_user.user_id, start_date, end_date)


@gui_router.get("/users/{user_id}/tool-usage", response_model=List[UserToolUsageResponse])
async def get_user_tool_usage_gui(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="Filter usage after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter usage before this date"),
    tool_slug: Optional[str] = Query(None, description="Filter by specific tool"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get tool usage statistics for a specific user (GUI)."""
    analytics_service = AnalyticsService(db)
    
    params = UserStatsParams(
        start_date=start_date,
        end_date=end_date,
        tool_slug=tool_slug
    )
    
    return analytics_service.get_user_tool_usage(user_id, params)


@gui_router.get("/users/{user_id}/summary", response_model=Dict[str, Any])
async def get_user_execution_summary_gui(
    user_id: str,
    start_date: Optional[datetime] = Query(None, description="Filter summary after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter summary before this date"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get execution summary for a specific user (GUI)."""
    analytics_service = AnalyticsService(db)
    
    return analytics_service.get_user_execution_summary(user_id, start_date, end_date)


@gui_router.get("/tools/stats", response_model=List[ToolStatsResponse])
async def get_tool_statistics_gui(
    start_date: Optional[datetime] = Query(None, description="Filter stats after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter stats before this date"),
    min_executions: Optional[int] = Query(None, ge=0, description="Minimum number of executions"),
    sort_by: str = Query("total_executions", regex="^(total_executions|unique_users|success_rate|total_cost|last_used_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: UserResponse = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get tool usage statistics across all users (GUI)."""
    analytics_service = AnalyticsService(db)
    
    params = ToolStatsParams(
        start_date=start_date,
        end_date=end_date,
        min_executions=min_executions,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    return analytics_service.get_tool_statistics(params)