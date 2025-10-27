"""Routes for connection management."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets

from ..db.session import get_db
from ..db import models as m
from .deps import current_user_from_api_key, current_user_from_jwt
from ..core.schemas import (
    ConnectionCreateRequest, ConnectionOAuth2StartRequest, ConnectionOAuth2StartResponse,
    ConnectionResponse, ConnectionUpdateRequest, ConnectionTestResponse, 
    ConnectionRefreshResponse, ToolkitResponse, ToolDefinitionResponse,
    EffectiveToolsResponse, ToolOverrideRequest, ToolOverrideResponse, MCPManifestResponse
)
from ..core.services import ConnectionService, ToolOverrideService
from ..core.tool_registry import get_tool_registry
from .factory import RouterConfig, SDK_CONFIG, GUI_CONFIG


# =============================================================================
# SDK Router (API Key Authentication)
# =============================================================================
# Common Router (OAuth Callback)
# =============================================================================


# =============================================================================
# Common Router (OAuth Callback)
# =============================================================================

common_router = APIRouter(prefix="/v1", tags=["connections-common"])


@common_router.get("/auth/callback")
def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Handle OAuth2 callback."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error} - {error_description}"
        )
    
    try:
        # Validate state parameter
        oauth_state = ConnectionService.validate_oauth_state(db, state)
        if not oauth_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state"
            )
        
        # Get connection and app details
        connection = db.query(m.Connection).filter(
            m.Connection.id == oauth_state.connection_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        toolkit = db.query(m.Toolkit).filter(m.Toolkit.id == oauth_state.toolkit_id).first()
        if not toolkit or not toolkit.oauth_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Toolkit OAuth configuration not found"
            )
        
        oauth_config = toolkit.oauth_config
        
        # Exchange authorization code for tokens
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': oauth_state.redirect_uri or oauth_config.get('redirect_uri'),
            'client_id': oauth_config.get('client_id'),
            'client_secret': oauth_config.get('client_secret')
        }
        
        # Add PKCE code verifier if present
        if oauth_state.code_verifier:
            token_data['code_verifier'] = oauth_state.code_verifier
        
        # TODO: Make actual HTTP request to OAuth provider's token endpoint
        # For now, we'll simulate a successful token exchange
        credentials = {
            'access_token': f'access_token_{secrets.token_urlsafe(32)}',
            'refresh_token': f'refresh_token_{secrets.token_urlsafe(32)}',
            'token_type': 'Bearer',
            'expires_at': datetime.utcnow() + timedelta(hours=1),
            'scope': ' '.join(connection.scopes or [])
        }
        
        # Complete OAuth flow
        updated_connection = ConnectionService.complete_oauth_flow(
            db=db,
            state=state,
            authorization_code=code,
            credentials=credentials
        )
        
        # Return success response
        return {
            "message": "OAuth callback processed successfully",
            "connection_id": str(updated_connection.id),
            "status": updated_connection.status.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up OAuth state on error
        try:
            oauth_state = db.query(m.OAuthState).filter(
                m.OAuthState.state == state
            ).first()
            if oauth_state:
                db.delete(oauth_state)
                db.commit()
        except Exception:
            # Ignore cleanup errors
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback processing failed: {str(e)}"
        )



# Small deduplication: Unified toolkit validity validation

def _get_active_toolkit_or_404(db: Session, toolkit_key: str) -> m.Toolkit:
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    return toolkit


# =============================================================================
# Router Factory Implementation
# =============================================================================

def make_connections_router(config: RouterConfig) -> APIRouter:
    """Create a connections router with the specified configuration.
    
    Args:
        config: Router configuration (prefix, auth dependency, etc.)
        
    Returns:
        Configured APIRouter with all connections endpoints
    """
    router = APIRouter(
        prefix=config.prefix,
        tags=[f"connections-{config.prefix.split('/')[-1]}"]
    )
    
    @router.get("/toolkits/{toolkit_key}/tools", response_model=List[ToolDefinitionResponse])
    def get_toolkit_tools(
        toolkit_key: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get tool definitions for an app from ToolRegistry."""
        # Verify toolkit exists and user has access
        _get_active_toolkit_or_404(db, toolkit_key)
        
        # Get tools from registry
        registry = get_tool_registry()
        tool_defs = registry.list_tools(toolkit_key)
        
        return [
            ToolDefinitionResponse(
                tool_key=tool.tool_key,
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                default_enabled=tool.default_enabled,
                default_config=tool.default_config,
                required_scopes=tool.required_scopes,
                version=tool.version,
                digest=tool.digest
            )
            for tool in tool_defs
        ]

    @router.post("/toolkits/{toolkit_key}/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
    def create_connection(
        toolkit_key: str,
        request: ConnectionCreateRequest,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Create a new connection."""
        # Verify toolkit exists
        _get_active_toolkit_or_404(db, toolkit_key)
        
        # Create connection
        connection = ConnectionService.create_connection(
            db=db,
            user_id=current_user.user_id,
            app_key=toolkit_key,
            name=request.name,
            auth_method=request.auth_method,
            credentials=request.credentials,
            scopes=request.scopes,
            labels=request.labels
        )
        
        return ConnectionResponse.from_orm(connection)

    @router.post("/toolkits/{toolkit_key}/connections/oauth2-start", response_model=ConnectionOAuth2StartResponse)
    def start_oauth2_flow(
        toolkit_key: str,
        request: ConnectionOAuth2StartRequest,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Start OAuth2 flow for a connection."""
        try:
            # First create an OAuth2 connection
            _get_active_toolkit_or_404(db, toolkit_key)
            connection = ConnectionService.create_connection(
                db=db,
                user_id=current_user.user_id,
                app_key=toolkit_key,
                name=request.name,
                auth_method=m.AuthMethod.oauth2,
                labels=request.labels,
                scopes=request.scopes,
                redirect_uri=request.redirect_uri
            )
            
            # Start OAuth2 flow
            oauth_data = ConnectionService.start_oauth2_flow(
                db=db,
                user_id=current_user.user_id,
                connection_id=connection.id,
                redirect_uri=request.redirect_uri,
                scopes=request.scopes
            )
            
            return ConnectionOAuth2StartResponse(
                connection_id=connection.id,
                auth_url=oauth_data['auth_url'],
                state=oauth_data['state']
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start OAuth2 flow: {str(e)}"
            )

    @router.get("/toolkits/{toolkit_key}/connections", response_model=List[ConnectionResponse])
    def get_toolkit_connections(
        toolkit_key: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get all connections for an app."""
        # Verify toolkit exists
        _get_active_toolkit_or_404(db, toolkit_key)
        
        connections = ConnectionService.get_user_connections(
            db=db,
            user_id=current_user.user_id,
            app_key=toolkit_key
        )
        
        return [ConnectionResponse.from_orm(conn) for conn in connections]

    @router.get("/connections/{connection_id}", response_model=ConnectionResponse)
    def get_connection(
        connection_id: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get a specific connection."""
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        return ConnectionResponse.from_orm(connection)

    @router.patch("/connections/{connection_id}", response_model=ConnectionResponse)
    def update_connection(
        connection_id: str,
        request: ConnectionUpdateRequest,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Update a connection."""
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Update connection
        updated_connection = ConnectionService.update_connection(
            db=db,
            connection_id=connection_id,
            update_data=request
        )
        
        return ConnectionResponse.from_orm(updated_connection)

    @router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse)
    def test_connection(
        connection_id: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Test a connection."""
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Test connection
        test_result = ConnectionService.test_connection(db=db, connection_id=connection_id)
        
        return ConnectionTestResponse(**test_result)

    @router.post("/connections/{connection_id}/refresh", response_model=ConnectionRefreshResponse)
    def refresh_connection(
        connection_id: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Refresh a connection's credentials."""
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Refresh connection
        refresh_result = ConnectionService.refresh_connection(db=db, connection_id=connection_id)
        
        return ConnectionRefreshResponse(**refresh_result)

    @router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_connection(
        connection_id: str,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Delete a connection."""
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        db.delete(connection)
        db.commit()

    @router.get("/connections/{connection_id}/tools", response_model=EffectiveToolsResponse)
    def get_connection_tools(
        connection_id: str,
        include_disabled: bool = Query(False, description="Include disabled tools"),
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get effective tools for a connection."""
        # Verify connection ownership
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        result = ToolOverrideService.get_effective_tools(
            db=db,
            connection_id=connection_id,
            include_disabled=include_disabled
        )
        
        return EffectiveToolsResponse(**result)

    @router.patch("/connections/{connection_id}/tools/{tool_key}", response_model=ToolOverrideResponse)
    def upsert_tool_override(
        connection_id: str,
        tool_key: str,
        request: ToolOverrideRequest,
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Create or update a tool override for a connection."""
        # Verify connection ownership
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Upsert tool override
        override = ToolOverrideService.upsert_tool_override(
            db=db,
            connection_id=connection_id,
            tool_key=tool_key,
            override_data=request
        )
        
        return ToolOverrideResponse.from_orm(override)

    @router.get("/connections/{connection_id}/manifest", response_model=MCPManifestResponse)
    def get_mcp_manifest(
        connection_id: str,
        include_secrets: bool = Query(False, description="Include secrets in manifest"),
        current_user: m.User = Depends(config.current_user_dep),
        db: Session = Depends(get_db)
    ):
        """Get MCP manifest for a connection."""
        # Verify connection ownership
        connection = db.query(m.Connection).filter(
            m.Connection.id == connection_id,
            m.Connection.user_id == current_user.user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Generate manifest
        manifest_data = ConnectionService.generate_mcp_manifest(
            db=db,
            connection_id=connection_id,
            include_secrets=include_secrets
        )
        
        return MCPManifestResponse(**manifest_data)
    
    return router


# =============================================================================
# Create SDK and GUI routers using factory
# =============================================================================

# Create SDK router (API Key authentication)
sdk_router = make_connections_router(SDK_CONFIG)

# Create GUI router (JWT authentication)  
gui_router = make_connections_router(GUI_CONFIG)


@gui_router.get("/toolkits/{toolkit_key}/stats")
def get_toolkit_connection_stats(
    toolkit_key: str,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get connection statistics for a toolkit."""
    # Verify toolkit exists
    toolkit = db.query(m.Toolkit).filter(
        m.Toolkit.key == toolkit_key, 
        m.Toolkit.is_active == True
    ).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
    # Count total connections
    total_connections = db.query(m.Connection).filter(
        m.Connection.toolkit_id == toolkit.id
    ).count()
    
    # Count valid and enabled connections
    valid_connections = db.query(m.Connection).filter(
        m.Connection.toolkit_id == toolkit.id,
        m.Connection.status == m.ConnectionStatus.valid,
        m.Connection.enabled == True
    ).count()
    
    # Count unique users with valid connections
    unique_users = db.query(m.Connection.user_id).filter(
        m.Connection.toolkit_id == toolkit.id,
        m.Connection.status == m.ConnectionStatus.valid,
        m.Connection.enabled == True
    ).distinct().count()
    
    return {
        "toolkit_key": toolkit_key,
        "toolkit_name": toolkit.name,
        "total_connections": total_connections,
        "valid_connections": valid_connections,
        "unique_users": unique_users
    }


__all__ = ["sdk_router", "gui_router", "common_router"]


# Small deduplication: Unified toolkit validity validation

def _get_active_toolkit_or_404(db: Session, toolkit_key: str) -> m.Toolkit:
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    return toolkit