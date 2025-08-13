"""Application entry point for the Terralink platform service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .extensions import load_builtin_toolkits, load_entrypoint_plugins
from .routers import auth as auth_router
from .routers import tools as tools_router


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application.

    This function is separated so that the app can be created in
    tests without running side effects in the module scope.  It
    registers all built‑in tools and mounts the API routers.  A
    simple healthcheck endpoint is added at the root.
    """
    # Load plugin system
    load_builtin_toolkits()
    load_entrypoint_plugins()
    
    app = FastAPI(title="Terralink Platform", version="0.1.0")

    @app.get("/", summary="Health check")
    async def health():
        return JSONResponse({"status": "ok"})

    # Include routers
    app.include_router(auth_router.router)
    app.include_router(tools_router.router)
    return app


app = create_app()
