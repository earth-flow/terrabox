"""
Async Tools Router - FastAPI Routing Layer

Provides HTTP API interfaces for batch tool execution, responsible for:
- Route definition and parameter validation
- Dependency injection and authentication
- HTTP response handling
- Error handling and status code mapping
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..core.services.async_tools_service import (
    AsyncToolsService,
    ActionRequest,
    AgentResponse
)
from ..db.session import get_db
from ..db import models
from .deps import current_user_from_api_key, current_user_from_jwt


def make_async_tools_router(prefix: str, current_user_dep, tags: list = None) -> APIRouter:
    """Create Async Tools Router
    
    Args:
        prefix: Route prefix
        current_user_dep: User authentication dependency
        tags: Route tags
        
    Returns:
        APIRouter: Configured router instance
    """
    if tags is None:
        tags = ["async-tools"]
    
    router = APIRouter(prefix=prefix, tags=tags)
    
    @router.post("/tools/get_observation", response_model=AgentResponse)
    async def get_observation(
        request: ActionRequest,
        response: Response,
        current_user: models.User = Depends(current_user_dep),
        db: Session = Depends(get_db)
    ) -> AgentResponse:
        """Batch Tool Execution Endpoint
        
        Executes batch tool actions, supporting:
        - Smart caching (based on request content hash)
        - Concurrency limiting and timeout control
        - Comprehensive error handling and logging
        - Trace ID support
        """
        try:
            # Create service instance and execute business logic
            service = AsyncToolsService(db)
            result, headers = await service.execute_batch_actions(request, current_user.id)
            
            # Set response headers
            for key, value in headers.items():
                response.headers[key] = value
            
            return result
            
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except TimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail=str(e)
            )
        except Exception as e:
            # Set trace ID to response headers (if available)
            if hasattr(request, 'trace_id') and request.trace_id:
                response.headers["X-Trace-ID"] = request.trace_id
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}"
            )
    
    @router.get("/tools/health")
    async def health_check(
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Health Check Endpoint"""
        service = AsyncToolsService(db)
        return service.get_health_status()
    
    @router.get("/tools/metrics")
    async def get_metrics(
        current_user: models.User = Depends(current_user_dep),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Performance Metrics Endpoint (Authenticated)"""
        service = AsyncToolsService(db)
        return service.get_metrics()
    
    @router.get("/tools/config")
    async def get_config(
        current_user: models.User = Depends(current_user_dep),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Configuration Info Endpoint (Authenticated)"""
        service = AsyncToolsService(db)
        return service.get_config()
    
    return router


# Create pre-configured router instances
sdk_router = make_async_tools_router(
    prefix="/v1/sdk",
    current_user_dep=current_user_from_api_key,
    tags=["async-tools-sdk"]
)

gui_router = make_async_tools_router(
    prefix="/v1/gui", 
    current_user_dep=current_user_from_jwt,
    tags=["async-tools-gui"]
)

# Create a special router for backward compatibility (removing internal /tools prefix)
def make_legacy_batch_tools_router() -> APIRouter:
    """Create Backward Compatible Batch Tools Router"""
    router = APIRouter(prefix="/v1/tools", tags=["batch-tools"])
    
    @router.post("/get_observation", response_model=AgentResponse)
    async def get_observation(
        request: ActionRequest,
        response: Response,
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> AgentResponse:
        """Batch Tool Execution Endpoint (Backward Compatible)"""
        try:
            service = AsyncToolsService(db)
            result, headers = await service.execute_batch_actions(request, current_user.id)
            
            for key, value in headers.items():
                response.headers[key] = value
            
            return result
            
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except TimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail=str(e)
            )
        except Exception as e:
            if hasattr(request, 'trace_id') and request.trace_id:
                response.headers["X-Trace-ID"] = request.trace_id
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}"
            )
    
    @router.get("/health")
    async def health_check(
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Health Check Endpoint (Backward Compatible)"""
        service = AsyncToolsService(db)
        return service.get_health_status()
    
    @router.get("/metrics")
    async def get_metrics(
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Performance Metrics Endpoint (Backward Compatible)"""
        service = AsyncToolsService(db)
        return service.get_metrics()
    
    @router.get("/config")
    async def get_config(
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """Configuration Info Endpoint (Backward Compatible)"""
        service = AsyncToolsService(db)
        return service.get_config()
    
    return router

batch_tools_router = make_legacy_batch_tools_router()