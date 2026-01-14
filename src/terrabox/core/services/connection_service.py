"""Connection service for managing connections and OAuth flows."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ...db.models import User, Toolkit, Connection as DBConnection, OAuthState, AuthMethod, ConnectionStatus
from ..utils.config import settings


class ConnectionService:
    """Service for managing connections and their state machine."""
    
    @staticmethod
    def create_connection(
        db: Session, 
        user_id: str, 
        app_key: str, 
        name: str, 
        auth_method: AuthMethod,
        credentials: Optional[Dict[str, Any]] = None,
        labels: Optional[Dict[str, Any]] = None,
        scopes: Optional[List[str]] = None,
        redirect_uri: Optional[str] = None
    ) -> DBConnection:
        """Create a new connection."""
        # Get or create toolkit
        toolkit = db.query(Toolkit).filter(Toolkit.key == app_key).first()
        if not toolkit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Toolkit '{app_key}' not found"
            )
        
        # Create connection
        connection = DBConnection(
            user_id=user_id,
            toolkit_id=toolkit.id,
            name=name,
            auth_method=auth_method,
            labels=labels or {},
            status=ConnectionStatus.incomplete if auth_method == AuthMethod.oauth2 else ConnectionStatus.valid
        )
        
        # Handle credentials based on auth method
        if credentials and auth_method != AuthMethod.oauth2:
            # Encrypt and store credentials
            connection.credentials_enc = ConnectionService._encrypt_credentials(credentials)
            connection.status = ConnectionStatus.valid
        elif auth_method == AuthMethod.oauth2 and settings.ENV in {"dev", "test"}:
            token = f"dev_token_{secrets.token_urlsafe(24)}"
            oauth_credentials = {
                "access_token": token,
                "refresh_token": f"dev_refresh_{secrets.token_urlsafe(24)}",
                "token_type": "Bearer",
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "scope": " ".join(scopes or []),
                "token": token,
                "github_token": token,
            }
            connection.credentials_enc = ConnectionService._encrypt_credentials(oauth_credentials)
            connection.status = ConnectionStatus.valid
            connection.expires_at = datetime.utcnow() + timedelta(hours=1)
        
        if scopes:
            connection.scopes = scopes
            
        db.add(connection)
        db.commit()
        db.refresh(connection)
        
        return connection
    
    @staticmethod
    def update_connection_status(
        db: Session, 
        connection_id: str, 
        status: ConnectionStatus,
        error_message: Optional[str] = None
    ) -> DBConnection:
        """Update connection status."""
        connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        connection.status = status
        connection.updated_at = datetime.utcnow()
        
        if error_message:
            connection.last_error = error_message
        
        db.commit()
        db.refresh(connection)
        
        return connection
    
    @staticmethod
    def get_user_connections(
        db: Session, 
        user_id: str, 
        app_key: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[DBConnection]:
        """Get user connections, optionally filtered by app."""
        query = db.query(DBConnection).filter(DBConnection.user_id == user_id)
        
        if app_key:
            query = query.join(Toolkit).filter(Toolkit.key == app_key)
        
        if enabled_only:
            query = query.filter(
                DBConnection.enabled == True,
                DBConnection.status == ConnectionStatus.valid
            )
        
        return query.order_by(DBConnection.priority.asc(), DBConnection.last_used_at.desc()).all()
    
    @staticmethod
    def select_connection(
        db: Session, 
        user_id: str, 
        app_key: str
    ) -> Optional[DBConnection]:
        """Select the best available connection for a user and toolkit."""
        connections = ConnectionService.get_user_connections(
            db, user_id, app_key, enabled_only=True
        )
        
        for connection in connections:
            # Check if token is about to expire
            if connection.expires_at and connection.expires_at < datetime.utcnow() + timedelta(minutes=5):
                # Try to refresh
                if connection.auth_method == AuthMethod.oauth2:
                    try:
                        ConnectionService._refresh_oauth_token(db, connection)
                    except Exception as e:
                        ConnectionService.update_connection_status(
                            db, str(connection.id), ConnectionStatus.error, str(e)
                        )
                        continue
            
            # Update last used time
            connection.last_used_at = datetime.utcnow()
            db.commit()
            
            return connection
        
        return None
    
    @staticmethod
    def test_connection(db: Session, connection_id: str) -> bool:
        """Test if a connection is working."""
        connection = db.query(DBConnection).filter(DBConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        try:
            # Implement connection testing logic based on auth method
            if connection.auth_method == AuthMethod.oauth2:
                # Test OAuth2 token
                return ConnectionService._test_oauth_connection(connection)
            elif connection.auth_method == AuthMethod.api_key:
                # Test API key
                return ConnectionService._test_api_key_connection(connection)
            # Add other auth methods as needed
            
            return True
        except Exception as e:
            ConnectionService.update_connection_status(
                db, connection_id, ConnectionStatus.error, str(e)
            )
            return False
    
    @staticmethod
    def _encrypt_credentials(credentials: Dict[str, Any]) -> str:
        """Encrypt credentials using AES-256-GCM."""
        from ..security import encrypt_credentials
        return encrypt_credentials(credentials)
    
    @staticmethod
    def _decrypt_credentials(encrypted_credentials: str) -> Dict[str, Any]:
        """Decrypt credentials using AES-256-GCM."""
        from ..security import decrypt_credentials
        return decrypt_credentials(encrypted_credentials)
    
    @staticmethod
    def start_oauth2_flow(
        db: Session,
        user_id: str,
        connection_id: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """Start OAuth2 flow and return authorization URL and state."""
        # Get connection and app
        connection = db.query(DBConnection).filter(
            DBConnection.id == connection_id,
            DBConnection.user_id == user_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        toolkit = db.query(Toolkit).filter(Toolkit.id == connection.toolkit_id).first()
        if not toolkit or not toolkit.oauth_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Toolkit OAuth configuration not found"
            )
        
        # Ensure oauth_config is a dict (handle both JSON and string cases)
        oauth_config = toolkit.oauth_config
        if isinstance(oauth_config, str):
            import json
            try:
                oauth_config = json.loads(oauth_config)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid OAuth configuration format"
                )
        
        # Generate PKCE code verifier and challenge (optional)
        code_verifier = None
        code_challenge = None
        if oauth_config.get('use_pkce', False):
            code_verifier = secrets.token_urlsafe(32)
            # For simplicity, using plain method. In production, use S256
            code_challenge = code_verifier
        
        # Create OAuth state
        state = ConnectionService.create_oauth_state(
            db=db,
            user_id=user_id,
            toolkit_id=toolkit.id,
            connection_id=connection_id,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri
        )
        
        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': oauth_config['client_id'],
            'redirect_uri': redirect_uri,
            'state': state,
            'scope': ' '.join(scopes or connection.scopes or [])
        }
        
        if code_challenge:
            auth_params.update({
                'code_challenge': code_challenge,
                'code_challenge_method': 'plain'  # Use S256 in production
            })
        
        # Build URL
        auth_url = oauth_config['authorization_endpoint']
        query_string = '&'.join([f'{k}={v}' for k, v in auth_params.items()])
        full_auth_url = f"{auth_url}?{query_string}"
        
        return {
            'auth_url': full_auth_url,
            'state': state
        }
    
    @staticmethod
    def create_oauth_state(
        db: Session,
        user_id: str,
        toolkit_id: int,
        connection_id: str,
        code_verifier: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ) -> str:
        """Create OAuth state for PKCE/replay protection."""
        state = secrets.token_urlsafe(32)
        
        oauth_state = OAuthState(
            state=state,
            user_id=user_id,
            toolkit_id=toolkit_id,
            connection_id=connection_id,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            expires_at=datetime.utcnow() + timedelta(minutes=10)  # 10 minutes expiry
        )
        
        db.add(oauth_state)
        db.commit()
        
        return state
    
    @staticmethod
    def validate_oauth_state(
        db: Session,
        state: str
    ) -> Optional[OAuthState]:
        """Validate OAuth state and return state object if valid."""
        oauth_state = db.query(OAuthState).filter(
            OAuthState.state == state,
            OAuthState.expires_at > datetime.utcnow()
        ).first()
        
        return oauth_state
    
    @staticmethod
    def complete_oauth_flow(
        db: Session,
        state: str,
        authorization_code: str,
        credentials: Dict[str, Any]
    ) -> DBConnection:
        """Complete OAuth flow by updating connection with credentials."""
        # Validate state
        oauth_state = ConnectionService.validate_oauth_state(db, state)
        if not oauth_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state"
            )
        
        # Get connection
        connection = db.query(DBConnection).filter(
            DBConnection.id == oauth_state.connection_id
        ).first()
        
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        # Update connection with credentials
        connection.credentials_enc = ConnectionService._encrypt_credentials(credentials)
        connection.status = ConnectionStatus.valid
        connection.updated_at = datetime.utcnow()
        
        # Clean up OAuth state
        db.delete(oauth_state)
        
        db.commit()
        db.refresh(connection)
        
        return connection
    
    @staticmethod
    def cleanup_expired_oauth_states(db: Session) -> int:
        """Clean up expired OAuth states."""
        expired_count = db.query(OAuthState).filter(
            OAuthState.expires_at <= datetime.now(timezone.utc)
        ).count()
        
        db.query(OAuthState).filter(
            OAuthState.expires_at <= datetime.now(timezone.utc)
        ).delete()
        
        db.commit()
        
        return expired_count
    
    @staticmethod
    def _refresh_oauth_token(db: Session, connection: DBConnection) -> bool:
        """Refresh OAuth2 token."""
        try:
            credentials = ConnectionService._decrypt_credentials(connection.credentials_enc)
            
            if 'refresh_token' not in credentials:
                return False
            
            # Get toolkit configuration for OAuth endpoints
            toolkit = db.query(Toolkit).filter(Toolkit.id == connection.toolkit_id).first()
            if not toolkit or not toolkit.oauth_config:
                return False
            
            # Ensure oauth_config is a dict (handle both JSON and string cases)
            oauth_config = toolkit.oauth_config
            if isinstance(oauth_config, str):
                import json
                try:
                    oauth_config = json.loads(oauth_config)
                except json.JSONDecodeError:
                    return False
            
            # Prepare refresh request
            refresh_data = {
                'grant_type': 'refresh_token',
                'refresh_token': credentials['refresh_token'],
                'client_id': oauth_config.get('client_id'),
                'client_secret': oauth_config.get('client_secret')
            }
            
            # Make refresh request (this would be implemented with actual HTTP client)
            # For now, we'll simulate success
            # TODO: Implement actual HTTP request to OAuth provider
            
            # Update connection with new tokens
            new_credentials = credentials.copy()
            new_credentials.update({
                'access_token': 'new_access_token',  # Would come from OAuth response
                'expires_at': datetime.utcnow() + timedelta(hours=1)
            })
            
            connection.credentials_enc = ConnectionService._encrypt_credentials(new_credentials)
            connection.updated_at = datetime.utcnow()
            
            db.commit()
            
            return True
            
        except Exception as e:
            # Log error and mark connection as invalid
            connection.status = ConnectionStatus.invalid
            connection.last_error = f"Token refresh failed: {str(e)}"
            db.commit()
            
            return False
    
    @staticmethod
    def _test_oauth_connection(connection: DBConnection) -> bool:
        """Test OAuth2 connection."""
        try:
            credentials = ConnectionService._decrypt_credentials(connection.credentials_enc)
            
            if 'access_token' not in credentials:
                return False
            
            # Check if token is expired
            if 'expires_at' in credentials:
                expires_at = credentials['expires_at']
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                
                if expires_at <= datetime.utcnow():
                    return False
            
            # TODO: Make actual test API call to verify token
            # For now, we'll assume the token is valid if it exists and isn't expired
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def _test_api_key_connection(connection: DBConnection) -> bool:
        """Test API key connection."""
        # TODO: Implement API key connection testing
        # This would validate the API key with the service
        return True
    
    @staticmethod
    def refresh_connection_tokens(db: Session, connection: DBConnection) -> bool:
        """Refresh connection tokens if applicable."""
        try:
            if connection.auth_method == AuthMethod.oauth2:
                return ConnectionService._refresh_oauth_token(db, connection)
            elif connection.auth_method == AuthMethod.api_key:
                # API keys don't need refreshing, just test the connection
                return ConnectionService._test_api_key_connection(connection)
            elif connection.auth_method == AuthMethod.token:
                # Static tokens don't need refreshing, just test the connection
                return ConnectionService._test_api_key_connection(connection)
            elif connection.auth_method == AuthMethod.service_account:
                # Service account tokens might need refreshing depending on implementation
                return ConnectionService._test_api_key_connection(connection)
            else:
                return False
        except Exception:
            return False
