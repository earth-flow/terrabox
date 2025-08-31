"""Analytics service for tool execution statistics and history."""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, and_, or_

from ...db.models import ToolExecution
from ..schemas import (
    ToolExecutionResponse,
    UserToolUsageResponse,
    ToolStatsResponse,
    ExecutionHistoryParams,
    UserStatsParams,
    ToolStatsParams,
    PaginatedResponse
)


class AnalyticsService:
    """Service for analytics and statistics related to tool executions."""

    def __init__(self, db: Session):
        self.db = db

    def get_execution_history(
        self,
        params: ExecutionHistoryParams
    ) -> PaginatedResponse:
        """Get paginated tool execution history with optional filters."""
        query = self.db.query(ToolExecution)

        # Apply filters
        if params.user_id:
            query = query.filter(ToolExecution.user_id_fk == params.user_id)
        
        if params.tool_slug:
            # Support partial matching for tool slugs
            query = query.filter(ToolExecution.tool_slug.like(f"%{params.tool_slug}%"))
        
        if params.connection_id:
            query = query.filter(ToolExecution.connection_id_fk == params.connection_id)
        
        if params.start_date:
            query = query.filter(ToolExecution.started_at >= params.start_date)
        
        if params.end_date:
            query = query.filter(ToolExecution.started_at <= params.end_date)
        
        if params.success_only is not None:
            if params.success_only:
                query = query.filter(ToolExecution.ok == True)
            else:
                query = query.filter(ToolExecution.ok == False)

        # Order by most recent first
        query = query.order_by(desc(ToolExecution.started_at))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (params.page - 1) * params.size
        executions = query.offset(offset).limit(params.size).all()

        # Convert to response models
        items = [ToolExecutionResponse.from_orm(execution) for execution in executions]

        # Calculate total pages
        pages = (total + params.size - 1) // params.size

        return PaginatedResponse(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=pages
        )

    def get_user_tool_usage(
        self,
        user_id: str,
        params: UserStatsParams
    ) -> List[UserToolUsageResponse]:
        """Get tool usage statistics for a specific user."""
        query = self.db.query(
            ToolExecution.tool_slug,
            func.count(ToolExecution.id).label('usage_count'),
            func.sum(func.case([(ToolExecution.ok == True, 1)], else_=0)).label('success_count'),
            func.sum(func.case([(ToolExecution.ok == False, 1)], else_=0)).label('failure_count'),
            func.sum(ToolExecution.cost_estimate).label('total_cost'),
            func.max(ToolExecution.started_at).label('last_used_at')
        ).filter(ToolExecution.user_id_fk == user_id)

        # Apply filters
        if params.start_date:
            query = query.filter(ToolExecution.started_at >= params.start_date)
        
        if params.end_date:
            query = query.filter(ToolExecution.started_at <= params.end_date)
        
        if params.tool_slug:
            query = query.filter(ToolExecution.tool_slug == params.tool_slug)

        # Group by tool_slug and order by usage count
        query = query.group_by(ToolExecution.tool_slug)
        query = query.order_by(desc('usage_count'))

        results = query.all()

        return [
            UserToolUsageResponse(
                tool_slug=result.tool_slug,
                usage_count=result.usage_count or 0,
                success_count=result.success_count or 0,
                failure_count=result.failure_count or 0,
                total_cost=float(result.total_cost) if result.total_cost else None,
                last_used_at=result.last_used_at
            )
            for result in results
        ]

    def get_tool_statistics(
        self,
        params: ToolStatsParams
    ) -> List[ToolStatsResponse]:
        """Get overall tool usage statistics across all users."""
        query = self.db.query(
            ToolExecution.tool_slug,
            func.count(ToolExecution.id).label('total_executions'),
            func.count(func.distinct(ToolExecution.user_id_fk)).label('unique_users'),
            func.avg(func.case([(ToolExecution.ok == True, 1.0)], else_=0.0)).label('success_rate'),
            func.avg(ToolExecution.cost_estimate).label('average_cost'),
            func.sum(ToolExecution.cost_estimate).label('total_cost'),
            func.max(ToolExecution.started_at).label('last_used_at')
        )

        # Apply filters
        if params.start_date:
            query = query.filter(ToolExecution.started_at >= params.start_date)
        
        if params.end_date:
            query = query.filter(ToolExecution.started_at <= params.end_date)

        # Group by tool_slug
        query = query.group_by(ToolExecution.tool_slug)

        # Apply minimum executions filter
        if params.min_executions is not None:
            query = query.having(func.count(ToolExecution.id) >= params.min_executions)

        # Apply sorting
        sort_column = {
            'total_executions': 'total_executions',
            'unique_users': 'unique_users',
            'success_rate': 'success_rate',
            'total_cost': 'total_cost',
            'last_used_at': 'last_used_at'
        }.get(params.sort_by, 'total_executions')

        if params.sort_order == 'asc':
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        results = query.all()

        return [
            ToolStatsResponse(
                tool_slug=result.tool_slug,
                total_executions=result.total_executions or 0,
                unique_users=result.unique_users or 0,
                success_rate=float(result.success_rate or 0),
                average_cost=float(result.average_cost) if result.average_cost else None,
                total_cost=float(result.total_cost) if result.total_cost else None,
                last_used_at=result.last_used_at
            )
            for result in results
        ]

    def get_execution_by_id(self, execution_id: int) -> Optional[ToolExecutionResponse]:
        """Get a specific tool execution by ID."""
        execution = self.db.query(ToolExecution).filter(
            ToolExecution.id == execution_id
        ).first()
        
        if execution:
            return ToolExecutionResponse.from_orm(execution)
        return None

    def get_user_execution_summary(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get summary statistics for a user's tool executions."""
        query = self.db.query(ToolExecution).filter(
            ToolExecution.user_id_fk == user_id
        )

        if start_date:
            query = query.filter(ToolExecution.started_at >= start_date)
        
        if end_date:
            query = query.filter(ToolExecution.started_at <= end_date)

        # Get summary statistics
        summary_query = query.with_entities(
            func.count(ToolExecution.id).label('total_executions'),
            func.sum(func.case([(ToolExecution.ok == True, 1)], else_=0)).label('successful_executions'),
            func.sum(func.case([(ToolExecution.ok == False, 1)], else_=0)).label('failed_executions'),
            func.sum(ToolExecution.cost_estimate).label('total_cost'),
            func.count(func.distinct(ToolExecution.tool_slug)).label('unique_tools_used'),
            func.max(ToolExecution.started_at).label('last_execution_at')
        ).first()

        total_executions = summary_query.total_executions or 0
        successful_executions = summary_query.successful_executions or 0
        failed_executions = summary_query.failed_executions or 0
        
        success_rate = (
            successful_executions / total_executions 
            if total_executions > 0 else 0
        )

        return {
            'user_id': user_id,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': success_rate,
            'total_cost': float(summary_query.total_cost) if summary_query.total_cost else 0.0,
            'unique_tools_used': summary_query.unique_tools_used or 0,
            'last_execution_at': summary_query.last_execution_at
        }