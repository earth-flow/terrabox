"""Tool service for tool-related operations."""
import uuid
import asyncio
import inspect
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..tool_registry import ToolSpec
from ...data import list_toolkits, get_tool, get_handler, list_tools
from ..schemas import ToolSpecOut, ToolkitOut, ExecuteRequestIn, ExecuteResponseOut
from ..tool_registry import get_tool_registry, ToolDefinition
class ToolService:
    """Service for tool-related operations."""
    
    @staticmethod
    def get_tools_with_status(db: Session, user_id: str) -> List[ToolSpecOut]:
        """Get all tools with their availability status for a user."""
        from ...data import list_toolkits, list_tools
        from .connection_service import ConnectionService
        
        toolkits = list_toolkits()
        tools = []
        
        for toolkit in toolkits:
            # Get tools for this toolkit
            toolkit_tools = list_tools(toolkit.name)
            for tool in toolkit_tools:
                # Calculate tool status based on connection requirements
                status = "available"
                if tool.requires_connection:
                    # Check if user has valid connections for this toolkit
                    connection = ConnectionService.select_connection(db, user_id, toolkit.name)
                    if not connection:
                        status = "unavailable"
                
                tool_out = ToolSpecOut(
                    slug=tool.slug,
                    name=tool.name,
                    description=tool.description,
                    requires_connection=tool.requires_connection,
                    status=status,
                    toolkit_slug=toolkit.name,  # Use name as slug since Toolkit doesn't have slug
                    parameters=tool.parameters,
                    metadata=tool.metadata if hasattr(tool, 'metadata') else None
                )
                tools.append(tool_out)
        
        return tools
    
    @staticmethod
    def get_tool_with_status(db: Session, user_id: str, tool_slug: str) -> Optional[ToolSpecOut]:
        """Get a specific tool with its availability status for a user."""
        from .connection_service import ConnectionService
        
        tool = get_tool(tool_slug)
        if not tool:
            return None
        
        # Find the toolkit that contains this tool
        toolkit_name = None
        for toolkit in list_toolkits():
            toolkit_tools = list_tools(toolkit.name)
            if any(t.slug == tool_slug for t in toolkit_tools):
                toolkit_name = toolkit.name
                break
        
        # Calculate tool status
        status = "available"
        if tool.requires_connection and toolkit_name:
            # Check if user has valid connections for this toolkit
            connection = ConnectionService.select_connection(db, user_id, toolkit_name)
            if not connection:
                status = "unavailable"
        
        return ToolSpecOut(
            slug=tool.slug,
            name=tool.name,
            description=tool.description,
            requires_connection=tool.requires_connection,
            status=status,
            toolkit_slug=toolkit_name or "",
            parameters=tool.parameters,
            metadata=tool.metadata if hasattr(tool, 'metadata') else None
        )
    
    @staticmethod
    def get_toolkits_with_status(db: Session, user_id: str) -> List[ToolkitOut]:
        """Get all toolkits with their availability status for a user."""
        from .connection_service import ConnectionService
        
        toolkits = list_toolkits()
        toolkit_outs = []
        
        for toolkit in toolkits:
            # Check if user has valid connections for this toolkit
            connection = ConnectionService.select_connection(db, user_id, toolkit.name)
            status = "connected" if connection else "available"
            
            # Get tools count for this toolkit
            toolkit_tools = list_tools(toolkit.name)
            tools_count = len(toolkit_tools)
            
            # Count tools that require connection
            connection_required_count = sum(1 for tool in toolkit_tools if tool.requires_connection)
            
            # Convert tools to ToolSpecOut objects
            tool_specs = []
            for tool in toolkit_tools:
                tool_spec = ToolSpecOut(
                    slug=tool.slug,
                    name=tool.name,
                    description=tool.description,
                    requires_connection=tool.requires_connection,
                    status="available",
                    toolkit_slug=toolkit.name,
                    parameters=tool.parameters if hasattr(tool, 'parameters') else None,
                    metadata=tool.metadata if hasattr(tool, 'metadata') else None
                )
                tool_specs.append(tool_spec)
            
            toolkit_out = ToolkitOut(
                slug=toolkit.name,  # Use name as slug since Toolkit doesn't have slug
                name=toolkit.name,
                description=toolkit.description,
                tools=tool_specs,
                metadata={
                    "tools_count": tools_count,
                    "connection_required_count": connection_required_count,
                    "status": status
                }
            )
            toolkit_outs.append(toolkit_out)
        
        return toolkit_outs
    
    @staticmethod
    async def execute_tool(db: Session, user_id: str, tool_slug: str, request: ExecuteRequestIn) -> ExecuteResponseOut:
        """Execute a tool with the given inputs."""
        from .connection_service import ConnectionService
        from .tool_override_service import ToolOverrideService
        
        try:
            # Get tool definition
            tool = get_tool(tool_slug)
            if not tool:
                return ExecuteResponseOut(
                    success=False,
                    error="Tool not found"
                )
            
            # Find the toolkit that contains this tool
            app_key = None
            for toolkit in list_toolkits():
                toolkit_tools = list_tools(toolkit.name)
                if any(t.slug == tool_slug for t in toolkit_tools):
                    app_key = toolkit.name
                    break
            
            # Check if tool requires connection
            connection = None
            if tool.requires_connection and app_key:
                connection = ConnectionService.select_connection(db, user_id, app_key)
                if not connection:
                    return ExecuteResponseOut(
                        success=False,
                        error="No valid connection found for this tool"
                    )
            
            # For tools that don't require connection, try to find any connection for the toolkit
            # to check tool override settings
            if not connection and app_key:
                connection = ConnectionService.select_connection(db, user_id, app_key)
            
            # Check if tool is enabled (if any connection exists for the toolkit)
            if connection:
                # Get effective tools to check if this tool is enabled
                effective_tools_data = ToolOverrideService.get_effective_tools(
                    db=db,
                    connection_id=str(connection.id),
                    include_disabled=False  # Only get enabled tools
                )
                
                # Check if the tool is in the enabled tools list
                enabled_tool_keys = {tool['tool_key'] for tool in effective_tools_data['tools']}
                if tool_slug not in enabled_tool_keys:
                    return ExecuteResponseOut(
                        success=False,
                        error="Tool is disabled for this connection"
                    )
            
            # Get tool handler
            handler = get_handler(tool_slug)
            if not handler:
                return ExecuteResponseOut(
                    success=False,
                    error="No handler registered for tool"
                )
            
            # Prepare context for handler
            context = {
                "user_id": user_id,
                "connection_id": str(connection.id) if connection else None
            }
            
            # Merge metadata into context if provided
            if request.metadata:
                context.update(request.metadata)
            
            # Execute the tool (支持异步handler)
            # Check handler signature to determine if it accepts connection parameter
            sig = inspect.signature(handler)
            accepts_connection = len(sig.parameters) >= 3
            
            if inspect.iscoroutinefunction(handler):
                # 异步handler
                if accepts_connection:
                    result_data = await handler(request.inputs or {}, context, connection)
                else:
                    result_data = await handler(request.inputs or {}, context)
            else:
                # 同步handler
                if accepts_connection:
                    result_data = handler(request.inputs or {}, context, connection)
                else:
                    result_data = handler(request.inputs or {}, context)
            
            # Record tool execution
            execution_id = str(uuid.uuid4())
            ToolService._log_tool_execution(
                db, user_id, tool_slug, connection, execution_id, 
                request.inputs, result_data, True, None, app_key
            )
            
            return ExecuteResponseOut(
                success=True,
                outputs=result_data,
                execution_id=execution_id
            )
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Tool execution failed: {e}")
            
            # Log failed execution
            ToolService._log_tool_execution(
                db, user_id, tool_slug, None, str(uuid.uuid4()),
                request.inputs, None, False, str(e), None
            )
            
            return ExecuteResponseOut(
                success=False,
                error=str(e)
            )
    
    @staticmethod
    def _log_tool_execution(
        db: Session, user_id: str, tool_slug: str, connection, 
        execution_id: str, inputs, outputs, success: bool, 
        error: Optional[str] = None, app_key: Optional[str] = None
    ):
        """Log tool execution for analytics."""
        try:
            import json
            from ...db.models import ToolExecution
            
            # Serialize meta data to JSON string for SQLite compatibility
            meta_data = {"app_key": app_key} if app_key else None
            meta_json = json.dumps(meta_data) if meta_data else None
            
            tool_execution = ToolExecution(
                user_id_fk=user_id,
                tool_slug=tool_slug,
                connection_id_fk=connection.id if connection else None,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                ok=success,
                error=error,
                trace_id=execution_id,
                input_size=len(str(inputs or {})),
                output_size=len(str(outputs)) if outputs else 0,
                meta=meta_json
            )
            db.add(tool_execution)
            db.commit()
        except Exception as log_error:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to log tool execution: {log_error}")