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


# =============================================================================
# SDK Router (API Key Authentication)
# =============================================================================

sdk_router = APIRouter(prefix="/v1/sdk", tags=["connections-sdk"])


@sdk_router.get("/toolkits/{toolkit_key}/tools", response_model=List[ToolDefinitionResponse])
def get_toolkit_tools_sdk(
    toolkit_key: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get tool definitions for an app from ToolRegistry (SDK version)."""
    # Verify toolkit exists and user has access
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
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


@sdk_router.post("/toolkits/{toolkit_key}/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection_sdk(
    toolkit_key: str,
    request: ConnectionCreateRequest,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Create a new connection (SDK version)."""
    # Verify toolkit exists
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
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


@sdk_router.post("/toolkits/{toolkit_key}/connections/oauth2-start", response_model=ConnectionOAuth2StartResponse)
def start_oauth2_flow_sdk(
    toolkit_key: str,
    request: ConnectionOAuth2StartRequest,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Start OAuth2 flow for a connection (SDK version)."""
    try:
        # First create an OAuth2 connection
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


@sdk_router.get("/toolkits/{toolkit_key}/connections", response_model=List[ConnectionResponse])
def get_toolkit_connections_sdk(
    toolkit_key: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get all connections for an app (SDK version)."""
    # Verify toolkit exists
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
    connections = ConnectionService.get_user_connections(
        db=db,
        user_id=current_user.user_id,
        app_key=toolkit_key
    )
    
    return [ConnectionResponse.from_orm(conn) for conn in connections]


@sdk_router.get("/connections/{connection_id}", response_model=ConnectionResponse)
def get_connection_sdk(
    connection_id: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get a specific connection (SDK version)."""
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


@sdk_router.patch("/connections/{connection_id}", response_model=ConnectionResponse)
def update_connection_sdk(
    connection_id: str,
    request: ConnectionUpdateRequest,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Update a connection (SDK version)."""
    connection = db.query(m.Connection).filter(
        m.Connection.id == connection_id,
        m.Connection.user_id == current_user.user_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found"
        )
    
    # Update connection fields
    if request.name is not None:
        connection.name = request.name
    if request.enabled is not None:
        connection.enabled = request.enabled
    if request.priority is not None:
        connection.priority = request.priority
    if request.labels is not None:
        connection.labels = request.labels
    
    connection.updated_at = datetime.utcnow()
    
    # Handle credential rotation
    if request.rotate_credentials:
        # TODO: Implement credential rotation
        pass
    
    db.commit()
    db.refresh(connection)
    
    return ConnectionResponse.from_orm(connection)


@sdk_router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse)
def test_connection_sdk(
    connection_id: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Test a connection (SDK version)."""
    connection = db.query(m.Connection).filter(
        m.Connection.id == connection_id,
        m.Connection.user_id == current_user.user_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found"
        )
    
    success = ConnectionService.test_connection(db, connection_id)
    
    return ConnectionTestResponse(
        success=success,
        message="Connection test successful" if success else "Connection test failed",
        tested_at=datetime.utcnow()
    )


@sdk_router.post("/connections/{connection_id}/refresh", response_model=ConnectionRefreshResponse)
def refresh_connection_sdk(
    connection_id: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Refresh a connection (SDK version)."""
    connection = db.query(m.Connection).filter(
        m.Connection.id == connection_id,
        m.Connection.user_id == current_user.user_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found"
        )
    
    try:
        # Refresh connection tokens
        success = ConnectionService.refresh_connection_tokens(db, connection)
        
        return ConnectionRefreshResponse(
            success=success,
            message="Token refresh successful" if success else "Token refresh failed",
            refreshed_at=datetime.utcnow()
        )
        
    except Exception as e:
        return ConnectionRefreshResponse(
            success=False,
            message=f"Token refresh failed: {str(e)}",
            refreshed_at=datetime.utcnow()
        )


@sdk_router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection_sdk(
    connection_id: str,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Delete a connection (SDK version)."""
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


@sdk_router.get("/connections/{connection_id}/tools", response_model=EffectiveToolsResponse)
def get_connection_tools_sdk(
    connection_id: str,
    include_disabled: bool = Query(False, description="Include disabled tools"),
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get effective tools for a connection (SDK version)."""
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


@sdk_router.patch("/connections/{connection_id}/tools/{tool_key}", response_model=ToolOverrideResponse)
def upsert_tool_override_sdk(
    connection_id: str,
    tool_key: str,
    request: ToolOverrideRequest,
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Create or update tool override (SDK version)."""
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
    
    override = ToolOverrideService.upsert_tool_override(
        db=db,
        connection_id=connection_id,
        tool_key=tool_key,
        enabled=request.enabled,
        config=request.config
    )
    
    return ToolOverrideResponse.from_orm(override)


@sdk_router.get("/connections/{connection_id}/manifest", response_model=MCPManifestResponse)
def get_mcp_manifest_sdk(
    connection_id: str,
    include_secrets: bool = Query(False, description="Include secrets in manifest"),
    current_user: m.User = Depends(current_user_from_api_key),
    db: Session = Depends(get_db)
):
    """Get MCP manifest for a connection (SDK version)."""
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
    
    # Verify connection is valid and MCP-enabled
    if not connection.enabled or connection.status.value != "valid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection is not valid or enabled"
        )
    
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.id == connection.toolkit_id).first()
    if not toolkit or "mcp" not in toolkit.toolkit_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Toolkit does not support MCP"
        )
    
    # Get effective tools
    tools_result = ToolOverrideService.get_effective_tools(
        db=db,
        connection_id=connection_id,
        include_disabled=False
    )
    
    # Build manifest
    tools = [
        {
            "tool_key": tool["tool_key"],
            "enabled": tool["enabled"],
            "config": tool["config"]
        }
        for tool in tools_result["tools"]
    ]
    
    headers = {}
    if not include_secrets:
        headers["Authorization"] = "Bearer ***masked***"
    else:
        # TODO: Decrypt and include actual credentials
        headers["Authorization"] = "Bearer ***masked***"
    
    return MCPManifestResponse(
        endpoint_url=connection.mcp_endpoint_url or "",
        transport=connection.mcp_transport or "websocket",
        protocol_version=connection.mcp_protocol_version or "2024-11-05",
        headers=headers,
        tools=tools
    )


# =============================================================================
# GUI Router (JWT Authentication)
# =============================================================================

gui_router = APIRouter(prefix="/v1/gui", tags=["connections-gui"])

# GUI endpoints mirror SDK endpoints but use JWT authentication
# For brevity, implementing key endpoints only

@gui_router.get("/toolkits/{toolkit_key}/connections", response_model=List[ConnectionResponse])
def get_toolkit_connections_gui(
    toolkit_key: str,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get all connections for an app (GUI version)."""
    # Verify toolkit exists
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
    connections = ConnectionService.get_user_connections(
        db=db,
        user_id=current_user.user_id,
        app_key=toolkit_key
    )
    
    return [ConnectionResponse.from_orm(conn) for conn in connections]


@gui_router.post("/toolkits/{toolkit_key}/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection_gui(
    toolkit_key: str,
    request: ConnectionCreateRequest,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Create a new connection (GUI version)."""
    # Verify toolkit exists
    toolkit = db.query(m.Toolkit).filter(m.Toolkit.key == toolkit_key, m.Toolkit.is_active == True).first()
    if not toolkit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toolkit not found"
        )
    
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


@gui_router.get("/connections/{connection_id}/tools", response_model=EffectiveToolsResponse)
def get_connection_tools_gui(
    connection_id: str,
    include_disabled: bool = Query(False, description="Include disabled tools"),
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Get effective tools for a connection (GUI version)."""
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


@gui_router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection_gui(
    connection_id: str,
    current_user: m.User = Depends(current_user_from_jwt),
    db: Session = Depends(get_db)
):
    """Delete a connection (GUI version)."""
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