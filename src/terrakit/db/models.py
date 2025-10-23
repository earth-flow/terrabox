from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, JSON, Index,
    BigInteger, ARRAY, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSON as PG_JSON, TIMESTAMP as PG_TIMESTAMP
import enum
import uuid
import os

# Database compatibility layer
def get_uuid_type():
    """Return appropriate UUID type based on database backend."""
    db_url = os.getenv('TL_DB_URL', 'sqlite:///test.db')
    if db_url.startswith('sqlite'):
        return String(36)  # SQLite uses string for UUID
    else:
        return PG_UUID(as_uuid=True)  # PostgreSQL uses native UUID

def get_json_type():
    """Return appropriate JSON type based on database backend."""
    db_url = os.getenv('TL_DB_URL', 'sqlite:///test.db')
    if db_url.startswith('sqlite'):
        return Text  # SQLite stores JSON as text
    else:
        return PG_JSON  # PostgreSQL uses native JSON

def get_timestamp_type():
    """Return appropriate timestamp type based on database backend."""
    db_url = os.getenv('TL_DB_URL', 'sqlite:///test.db')
    if db_url.startswith('sqlite'):
        return DateTime  # SQLite uses DATETIME
    else:
        return PG_TIMESTAMP  # PostgreSQL uses TIMESTAMP  # PostgreSQL uses timestamp

def uuid_default():
    """Return UUID default value as string for SQLite compatibility."""
    return lambda: str(uuid.uuid4())

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(get_uuid_type(), primary_key=True, default=uuid_default())
    user_id = Column(String(64), unique=True, nullable=False)       # Align with API user_id
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_keys = relationship("ApiKey", back_populates="user", cascade="all,delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(get_uuid_type(), ForeignKey("users.id"), nullable=False)
    label = Column(String(64))
    public_id = Column(String(16), nullable=False)
    secret_hash = Column(String(128), nullable=False)    # HMAC(secret)
    prefix = Column(String(8), default="tlk")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    revoked_at = Column(DateTime)
    user = relationship("User", back_populates="api_keys")
    __table_args__ = (UniqueConstraint("public_id", name="uq_apikey_public"),)


# Legacy models removed - using new Connection and App models instead

class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(get_uuid_type(), ForeignKey("users.id"), nullable=False)
    tool_slug = Column(String(128), index=True, nullable=False)
    connection_id_fk = Column(get_uuid_type(), ForeignKey("connections.id"))
    # execution metadata
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    ok = Column(Boolean, default=True)
    error = Column(Text)
    trace_id = Column(String(64), index=True)
    input_size = Column(Integer)
    output_size = Column(Integer)
    cost_estimate = Column(Integer)
    meta = Column(get_json_type())

# Plan and UserPlan models removed as they were not used in the application

class OAuthProvider(Base):
    """OAuth provider configuration table"""
    __tablename__ = "oauth_providers"
    id = Column(Integer, primary_key=True)
    name = Column(String(32), unique=True, nullable=False)  # google, github
    display_name = Column(String(64), nullable=False)  # Google, GitHub
    client_id = Column(String(255), nullable=False)
    client_secret = Column(String(255), nullable=False)
    auth_url = Column(String(512), nullable=False)
    token_url = Column(String(512), nullable=False)
    user_info_url = Column(String(512), nullable=False)
    scopes = Column(String(512))  # Default requested permission scopes
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserOAuthAccount(Base):
    """User OAuth account association table"""
    __tablename__ = "user_oauth_accounts"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(get_uuid_type(), ForeignKey("users.id"), nullable=False)
    provider_name = Column(String(32), nullable=False)  # OAuth provider name (google, github, etc.)
    oauth_user_id = Column(String(255), nullable=False)  # OAuth provider's user ID
    email = Column(String(255))  # OAuth account email
    display_name = Column(String(128))  # OAuth account display name
    avatar_url = Column(String(512))  # Avatar URL
    access_token = Column(Text)  # Encrypted stored access token
    refresh_token = Column(Text)  # Encrypted stored refresh token
    token_expires_at = Column(DateTime)  # Token expiration time
    is_primary = Column(Boolean, default=False)  # Whether this is the primary login method
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    
    __table_args__ = (
        UniqueConstraint("provider_name", "oauth_user_id", name="uq_oauth_provider_user"),
        Index("ix_oauth_user_provider", "user_id_fk", "provider_name"),
    )


# =============================================================================
# New Connection System Models
# =============================================================================

class AuthMethod(enum.Enum):
    """Authentication methods for connections."""
    oauth2 = "oauth2"
    api_key = "api_key"
    service_account = "service_account"
    token = "token"
    none = "none"


class ConnectionStatus(enum.Enum):
    """Connection status states."""
    incomplete = "incomplete"
    pending = "pending"
    valid = "valid"
    expired = "expired"
    revoked = "revoked"
    error = "error"


class Toolkit(Base):
    """Toolkit configuration and metadata."""
    __tablename__ = "toolkits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False)  # e.g., "github", "slack"
    name = Column(String(128), nullable=False)  # Display name
    description = Column(Text)
    toolkit_type = Column(String(32), nullable=False)  # "mcp", "rest", "webhook", etc.
    oauth_config = Column(get_json_type())  # OAuth configuration (client_id, client_secret, etc.)
    is_active = Column(Boolean, default=True)
    created_at = Column(get_timestamp_type(), default=datetime.utcnow)
    updated_at = Column(get_timestamp_type(), default=datetime.utcnow)
    
    # Relationships
    connections = relationship("Connection", back_populates="toolkit", cascade="all,delete-orphan")


class Connection(Base):
    """User connections to external services."""
    __tablename__ = "connections"
    
    id = Column(get_uuid_type(), primary_key=True, default=uuid_default())
    user_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    toolkit_id = Column(BigInteger, ForeignKey("toolkits.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(SQLEnum(ConnectionStatus), nullable=False, default=ConnectionStatus.incomplete)
    priority = Column(Integer, nullable=False, default=100)
    labels = Column(JSON, nullable=False, default={})
    last_used_at = Column(get_timestamp_type())
    
    # Auth-specific fields
    auth_method = Column(SQLEnum(AuthMethod), nullable=False)
    credentials_enc = Column(Text)  # AES-GCM encrypted JSON
    scopes = Column(JSON)  # OAuth2 granted scopes
    expires_at = Column(get_timestamp_type())
    last_error = Column(Text)
    
    # MCP-specific fields
    mcp_transport = Column(Text, default="websocket")
    mcp_endpoint_url = Column(Text)
    mcp_protocol_version = Column(Text)
    
    # Timestamps
    created_at = Column(get_timestamp_type(), nullable=False, default=datetime.utcnow)
    updated_at = Column(get_timestamp_type(), nullable=False, default=datetime.utcnow)
    
    # Relationships
    toolkit = relationship("Toolkit", back_populates="connections")
    tool_overrides = relationship("ToolOverride", back_populates="connection", cascade="all,delete-orphan")
    oauth_states = relationship("OAuthState", back_populates="connection", cascade="all,delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("user_id", "toolkit_id", "name", name="uq_connection_user_toolkit_name"),
        Index(
            "idx_conn_pick", 
            "user_id", "toolkit_id", "priority",
            postgresql_where="enabled AND status='valid' AND (expires_at IS NULL OR expires_at > now())"
        ),
    )


class ToolOverride(Base):
    """Per-connection tool overrides."""
    __tablename__ = "tool_overrides"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(get_uuid_type(), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)
    tool_key = Column(Text, nullable=False)
    enabled = Column(Boolean)  # NULL = inherit default
    config = Column(JSON, nullable=False, default={})
    tool_version = Column(Text)  # Optional (from registry)
    resolved_digest = Column(Text)  # Optional (from registry)
    is_stale = Column(Boolean, nullable=False, default=False)  # Optional
    
    # Relationships
    connection = relationship("Connection", back_populates="tool_overrides")
    
    __table_args__ = (
        UniqueConstraint("connection_id", "tool_key", name="uq_tool_override_connection_tool"),
    )


class OAuthState(Base):
    """OAuth callback state (PKCE/replay protection)."""
    __tablename__ = "oauth_states"
    
    state = Column(Text, primary_key=True)
    user_id = Column(get_uuid_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    toolkit_id = Column(BigInteger, ForeignKey("toolkits.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(get_uuid_type(), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)
    code_verifier = Column(Text)
    redirect_uri = Column(Text)
    created_at = Column(get_timestamp_type(), default=datetime.utcnow)
    expires_at = Column(get_timestamp_type(), nullable=False)
    
    # Relationships
    connection = relationship("Connection", back_populates="oauth_states")
