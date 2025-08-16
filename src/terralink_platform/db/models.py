from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, JSON, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, nullable=False)       # 与 API 的 user_id 对齐
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_keys = relationship("ApiKey", back_populates="user", cascade="all,delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(Integer, ForeignKey("users.id"), nullable=False)
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

class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(Integer, ForeignKey("users.id"), nullable=False)
    toolkit = Column(String(64), nullable=False)
    display_name = Column(String(128))
    scopes = Column(JSON)
    token_enc = Column(Text)                                  # 加密存储
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")

class AuthConnection(Base):
    __tablename__ = "auth_connections"
    id = Column(Integer, primary_key=True)
    connection_id = Column(String(64), unique=True, nullable=False)
    user_id_fk = Column(Integer, ForeignKey("users.id"), nullable=False)
    toolkit = Column(String(64), nullable=False)
    status = Column(String(16), default="pending")
    redirect_url = Column(Text)
    connected_account_id_fk = Column(Integer, ForeignKey("connected_accounts.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(Integer, ForeignKey("users.id"), nullable=False)
    tool_slug = Column(String(128), index=True, nullable=False)
    connected_account_id_fk = Column(Integer, ForeignKey("connected_accounts.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    ok = Column(Boolean, default=True)
    error = Column(Text)
    trace_id = Column(String(64), index=True)
    input_size = Column(Integer)
    output_size = Column(Integer)
    cost_estimate = Column(Integer)
    meta = Column(JSON)

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    features = Column(JSON)

class UserPlan(Base):
    __tablename__ = "user_plans"
    id = Column(Integer, primary_key=True)
    user_id_fk = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id_fk = Column(Integer, ForeignKey("plans.id"), nullable=False)
    active = Column(Boolean, default=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    __table_args__ = (Index("ix_user_plans_user_active", "user_id_fk", "active"),)