"""Router factory infrastructure for eliminating SDK/GUI duplication.

This module provides a factory pattern to create routers with different
authentication dependencies and URL prefixes, eliminating code duplication
between SDK (API key auth) and GUI (JWT auth) routes.
"""

from typing import Callable, Any, Optional, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db import models as m
from .deps import current_user_from_api_key, current_user_from_jwt


class RouterConfig:
    """Configuration for router factory."""
    
    def __init__(
        self,
        prefix: str,
        tags: List[str],
        current_user_dep: Callable[..., m.User],
        include_db: bool = True
    ):
        """Initialize router configuration.
        
        Args:
            prefix: URL prefix for the router (e.g., "/v1/sdk", "/v1/gui")
            tags: OpenAPI tags for the router
            current_user_dep: Dependency function for current user authentication
            include_db: Whether to include database session dependency
        """
        self.prefix = prefix
        self.tags = tags
        self.current_user_dep = current_user_dep
        self.include_db = include_db


# Predefined configurations for common use cases
SDK_CONFIG = RouterConfig(
    prefix="/v1/sdk",
    tags=[],  # Will be set per module
    current_user_dep=current_user_from_api_key,
    include_db=True
)

GUI_CONFIG = RouterConfig(
    prefix="/v1/gui", 
    tags=[],  # Will be set per module
    current_user_dep=current_user_from_jwt,
    include_db=True
)


def create_router_factory(module_name: str):
    """Create a router factory function for a specific module.
    
    Args:
        module_name: Name of the module (e.g., "tools", "connections", "auth")
        
    Returns:
        Factory function that creates routers with the given configuration
    """
    
    def router_factory(config: RouterConfig) -> APIRouter:
        """Create a router with the given configuration.
        
        Args:
            config: Router configuration
            
        Returns:
            Configured APIRouter instance
        """
        # Update tags to include module name
        tags = config.tags + [f"{module_name}-{config.prefix.split('/')[-1]}"]
        
        return APIRouter(
            prefix=config.prefix,
            tags=tags
        )
    
    return router_factory


def get_common_dependencies(config: RouterConfig):
    """Get common dependencies for routes.
    
    Args:
        config: Router configuration
        
    Returns:
        Dictionary of common dependencies
    """
    deps = {}
    
    if config.include_db:
        deps["db"] = Depends(get_db)
    
    deps["current_user"] = Depends(config.current_user_dep)
    
    return deps


def create_route_decorator(config: RouterConfig):
    """Create a route decorator that automatically includes common dependencies.
    
    Args:
        config: Router configuration
        
    Returns:
        Decorator function for routes
    """
    common_deps = get_common_dependencies(config)
    
    def route_decorator(func: Callable) -> Callable:
        """Decorator that adds common dependencies to route function."""
        # Get function signature and add common dependencies
        import inspect
        sig = inspect.signature(func)
        
        # Create new parameters with common dependencies
        new_params = []
        for name, param in sig.parameters.items():
            new_params.append(param)
        
        # Add common dependencies if not already present
        for dep_name, dep_value in common_deps.items():
            if dep_name not in sig.parameters:
                new_params.append(
                    inspect.Parameter(
                        dep_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=dep_value,
                        annotation=m.User if dep_name == "current_user" else Session
                    )
                )
        
        # Create new signature
        new_sig = sig.replace(parameters=new_params)
        func.__signature__ = new_sig
        
        return func
    
    return route_decorator