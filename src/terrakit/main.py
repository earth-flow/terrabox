"""Application entry point for the Terralink platform service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from .core.utils.config import settings
from .db.session import engine
from .db.models import Base
from .extensions import load_builtin_toolkits, load_entrypoint_plugins
from .routers import auth as auth_router
from .routers import tools as tools_router
from .routers import connections as connections_router
from .routers import analytics as analytics_router
from .core.background_tasks import start_background_tasks, stop_background_tasks
from .core.services.async_tool_server import batch_tools_router

def init_db():
    """Initialize database tables.
    
    In development, creates tables automatically.
    In production, use Alembic migrations.
    """
    if settings.ENV == "dev":
        Base.metadata.create_all(bind=engine)  # Use Alembic in production


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    await start_background_tasks()
    yield
    # Shutdown
    await stop_background_tasks()


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application.

    This function is separated so that the app can be created in
    tests without running side effects in the module scope.  It
    registers all built‑in tools and mounts the API routers.  A
    simple healthcheck endpoint is added at the root.
    """
    # Initialize database
    init_db()
    
    # Load plugin system
    load_builtin_toolkits()
    load_entrypoint_plugins()
    
    app = FastAPI(
        title="Terralink Platform", 
        version="0.1.0",
        lifespan=lifespan
    )

    @app.get("/", summary="Health check")
    async def health():
        return JSONResponse({"status": "ok"})

    # Include routers
    # Auth routers
    app.include_router(auth_router.common_router)  # Common routes (register, login)
    app.include_router(auth_router.sdk_router)     # SDK routes (API key auth)
    app.include_router(auth_router.gui_router)     # GUI routes (JWT auth)
    
    # Tools routers
    app.include_router(tools_router.sdk_router)    # SDK tools
    app.include_router(tools_router.gui_router)    # GUI tools
    
    # Connection routers
    app.include_router(connections_router.common_router)  # OAuth callbacks
    app.include_router(connections_router.sdk_router)     # SDK connections
    app.include_router(connections_router.gui_router)     # GUI connections
    
    # Analytics routers
    app.include_router(analytics_router.sdk_router)       # SDK analytics
    app.include_router(analytics_router.gui_router)       # GUI analytics
    
    # Batch tools router (new async batch processing)
    app.include_router(batch_tools_router)                # Batch tools execution
    
    return app


app = create_app()
