"""
异步工具路由器 - FastAPI 路由层

提供批量工具执行的 HTTP API 接口，负责：
- 路由定义和参数验证
- 依赖注入和认证
- HTTP 响应处理
- 错误处理和状态码映射
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
    """创建异步工具路由器
    
    Args:
        prefix: 路由前缀
        current_user_dep: 用户认证依赖
        tags: 路由标签
        
    Returns:
        APIRouter: 配置好的路由器实例
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
        """批量工具执行端点
        
        执行批量工具动作，支持：
        - 智能缓存（基于请求内容哈希）
        - 并发限制和超时控制
        - 完整的错误处理和日志记录
        - 追踪ID支持
        """
        try:
            # 创建服务实例并执行业务逻辑
            service = AsyncToolsService(db)
            result, headers = await service.execute_batch_actions(request, current_user.id)
            
            # 设置响应头
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
            # 设置追踪ID到响应头（如果可用）
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
        """健康检查端点"""
        service = AsyncToolsService(db)
        return service.get_health_status()
    
    @router.get("/tools/metrics")
    async def get_metrics(
        current_user: models.User = Depends(current_user_dep),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """性能指标端点（需要认证）"""
        service = AsyncToolsService(db)
        return service.get_metrics()
    
    @router.get("/tools/config")
    async def get_config(
        current_user: models.User = Depends(current_user_dep),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """配置信息端点（需要认证）"""
        service = AsyncToolsService(db)
        return service.get_config()
    
    return router


# 创建预配置的路由器实例
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

# 为了向后兼容，创建一个特殊的路由器（去掉内部的/tools前缀）
def make_legacy_batch_tools_router() -> APIRouter:
    """创建向后兼容的批量工具路由器"""
    router = APIRouter(prefix="/v1/tools", tags=["batch-tools"])
    
    @router.post("/get_observation", response_model=AgentResponse)
    async def get_observation(
        request: ActionRequest,
        response: Response,
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> AgentResponse:
        """批量工具执行端点（向后兼容）"""
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
        """健康检查端点（向后兼容）"""
        service = AsyncToolsService(db)
        return service.get_health_status()
    
    @router.get("/metrics")
    async def get_metrics(
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """性能指标端点（向后兼容）"""
        service = AsyncToolsService(db)
        return service.get_metrics()
    
    @router.get("/config")
    async def get_config(
        current_user: models.User = Depends(current_user_from_api_key),
        db: Session = Depends(get_db)
    ) -> Dict[str, Any]:
        """配置信息端点（向后兼容）"""
        service = AsyncToolsService(db)
        return service.get_config()
    
    return router

batch_tools_router = make_legacy_batch_tools_router()