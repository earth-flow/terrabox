"""Core business logic services."""
import secrets
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from passlib.context import CryptContext
from datetime import datetime, timedelta
import secrets
import hashlib
import hmac
import base64
import uuid
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Header

from ..models import ToolSpec, Toolkit, ConnectedAccount, Connection, UserCreate, UserLogin, UserResponse
from ..db.models import User, ApiKey
from ..db import models as m
from ..db.session import get_db
from ..data import list_toolkits, get_tool, get_handler, list_tools
from .schemas import ToolSpecOut, ToolkitOut, ExecuteRequestIn, ExecuteResponseOut
from .utils.security import (
    hash_password, verify_password, verify_token, 
    generate_api_key, hash_api_key, generate_public_id
)

# HTTP Bearer token scheme
security = HTTPBearer()


class ToolService:
    """Service for tool-related operations."""
    
    @staticmethod
    def get_tools_with_status(db: Session, user_id: str) -> List[ToolSpecOut]:
        """Get all tools with their availability status for a user."""
        from ..data import list_toolkits, list_tools
        
        toolkits = list_toolkits()
        tools = []
        
        for toolkit in toolkits:
            # Get tools for this toolkit
            toolkit_tools = list_tools(toolkit.name)
            for tool in toolkit_tools:
                # Calculate tool status based on connection requirements
                status = "available"
                if tool.requires_connection:
                    # Check if user has connected accounts for this toolkit
                    # 修复：直接查询ConnectedAccount表，使用正确的字段名
                    from ..db.models import User, ConnectedAccount as DBConnectedAccount
                    user = db.query(User).filter(User.user_id == user_id).first()
                    if user:
                        connected_accounts = db.query(DBConnectedAccount).filter(
                            DBConnectedAccount.user_id_fk == user.id,
                            DBConnectedAccount.toolkit == toolkit.name  # 使用toolkit.name而不是slug
                        ).all()
                        
                        if not connected_accounts:
                            status = "unavailable"
                    else:
                        status = "unavailable"
                
                tool_out = ToolSpecOut(
                    slug=tool.slug,
                    name=tool.slug,  # Use slug as name since ToolSpec doesn't have name
                    description=tool.description,
                    requires_connection=tool.requires_connection,
                    status=status,
                    toolkit_slug=toolkit.name,  # Use name as slug since Toolkit doesn't have slug
                    metadata=tool.parameters
                )
                tools.append(tool_out)
        
        return tools
    
    @staticmethod
    def get_tool_with_status(db: Session, user_id: str, tool_slug: str) -> Optional[ToolSpecOut]:
        """Get a specific tool with its availability status for a user."""
        tool = get_tool(tool_slug)
        if not tool:
            return None
        
        # Find the toolkit that contains this tool
        toolkit_name = None
        for toolkit in list_toolkits():
            toolkit_tools = list_tools(toolkit.name)
            if any(t.slug == tool_slug for t in toolkit_tools):
                toolkit_name = toolkit.name
                break
        
        # Calculate tool status
        status = "available"
        if tool.requires_connection and toolkit_name:
            # 修复：直接查询ConnectedAccount表，使用正确的字段名
            from ..db.models import User, ConnectedAccount as DBConnectedAccount
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                connected_accounts = db.query(DBConnectedAccount).filter(
                    DBConnectedAccount.user_id_fk == user.id,
                    DBConnectedAccount.toolkit == toolkit_name
                ).all()
                
                if not connected_accounts:
                    status = "unavailable"
            else:
                status = "unavailable"
        
        return ToolSpecOut(
            slug=tool.slug,
            name=tool.slug,  # Use slug as name since ToolSpec doesn't have name
            description=tool.description,
            requires_connection=tool.requires_connection,
            status=status,
            toolkit_slug=toolkit_name,
            metadata=tool.parameters  # Use parameters as metadata
        )
    
    @staticmethod
    def get_toolkits_with_status(db: Session, user_id: str) -> List[ToolkitOut]:
        """Get all toolkits with their tools' availability status for a user."""
        from ..data import list_toolkits, list_tools
        
        toolkits = list_toolkits()
        toolkit_outs = []
        
        for toolkit in toolkits:
            tools = []
            # Get tools for this toolkit
            toolkit_tools = list_tools(toolkit.name)
            for tool in toolkit_tools:
                # Calculate tool status
                status = "available"
                if tool.requires_connection:
                    # 修复：直接查询ConnectedAccount表，使用正确的字段名
                    from ..db.models import User, ConnectedAccount as DBConnectedAccount
                    user = db.query(User).filter(User.user_id == user_id).first()
                    if user:
                        connected_accounts = db.query(DBConnectedAccount).filter(
                            DBConnectedAccount.user_id_fk == user.id,
                            DBConnectedAccount.toolkit == toolkit.name
                        ).all()
                        
                        if not connected_accounts:
                            status = "unavailable"
                    else:
                        status = "unavailable"
                
                tool_out = ToolSpecOut(
                    slug=tool.slug,
                    name=tool.slug,  # Use slug as name since ToolSpec doesn't have name
                    description=tool.description,
                    requires_connection=tool.requires_connection,
                    status=status,
                    toolkit_slug=toolkit.name,  # Use name as slug since Toolkit doesn't have slug
                    metadata=tool.parameters
                )
                tools.append(tool_out)
            
            toolkit_out = ToolkitOut(
                slug=toolkit.name,  # Use name as slug since Toolkit model doesn't have slug
                name=toolkit.name,
                description=toolkit.description,
                tools=tools,
                metadata={"version": toolkit.version}
            )
            toolkit_outs.append(toolkit_out)
        
        return toolkit_outs
    
    @staticmethod
    async def execute_tool(db: Session, user_id: str, tool_slug: str, request: ExecuteRequestIn) -> ExecuteResponseOut:
        """Execute a tool for a user."""
        try:
            # Get the tool
            tool = get_tool(tool_slug)
            if not tool:
                return ExecuteResponseOut(
                    success=False,
                    error=f"Tool '{tool_slug}' not found"
                )
            
            # Check if tool requires connection
            if tool.requires_connection:
                # Find the toolkit that contains this tool
                toolkit_slug = None
                for toolkit in list_toolkits():
                    if any(t.slug == tool_slug for t in toolkit.tools):
                        toolkit_slug = toolkit.slug
                        break
                
                if not toolkit_slug:
                    return ExecuteResponseOut(
                        success=False,
                        error="Toolkit not found for this tool"
                    )
                
                # Check if user has connected accounts
                # 修复：直接查询ConnectedAccount表，使用正确的字段名
                from ..db.models import User, ConnectedAccount as DBConnectedAccount
                user = db.query(User).filter(User.user_id == user_id).first()
                if not user:
                    return ExecuteResponseOut(
                        success=False,
                        error="User not found"
                    )
                
                # 找到对应的toolkit名称
                toolkit_name = None
                for tk in list_toolkits():
                    if tk.slug == toolkit_slug:
                        toolkit_name = tk.name
                        break
                
                if not toolkit_name:
                    return ExecuteResponseOut(
                        success=False,
                        error="Toolkit not found"
                    )
                
                connected_accounts = db.query(DBConnectedAccount).filter(
                    and_(
                        DBConnectedAccount.user_id_fk == user.id,
                        DBConnectedAccount.toolkit == toolkit_name,
                        DBConnectedAccount.status == "active"
                    )
                ).all()
                
                if not connected_accounts:
                    return ExecuteResponseOut(
                        success=False,
                        error="Tool requires connection but no connected account found"
                    )
                
                # Use the first connected account if not specified
                if not request.connected_account_id:
                    request.connected_account_id = connected_accounts[0].id
            
            # Get handler and execute the tool
            handler = get_handler(tool_slug)
            if handler is None:
                return ExecuteResponseOut(
                    success=False,
                    error="No handler registered for tool"
                )
            
            # Prepare context for handler
            context = {
                "user_id": user_id,
                "connected_account_id": request.connected_account_id
            }
            
            # Merge metadata into context if provided
            if request.metadata:
                context.update(request.metadata)
            
            # Get connected account object if needed
            connected_account = None
            if tool.requires_connection and request.connected_account_id:
                connected_account = db.query(DBConnectedAccount).filter_by(
                    id=int(request.connected_account_id)
                ).first()
            
            # Execute the tool (支持异步handler)
            import asyncio
            import inspect
            
            if inspect.iscoroutinefunction(handler):
                # 异步handler
                result_data = await handler(request.inputs or {}, context, connected_account)
            else:
                # 同步handler
                result_data = handler(request.inputs or {}, context, connected_account)
            
            return ExecuteResponseOut(
                success=True,
                outputs=result_data,
                execution_id=str(uuid.uuid4())
            )
            
        except Exception as e:
            return ExecuteResponseOut(
                success=False,
                error=str(e)
            )


class AuthService:
    """Service for authentication and user management operations."""
    
    @staticmethod
    def create_user(db: Session, user_create: UserCreate) -> User:
        """创建新用户"""
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.email == user_create.email).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # 创建新用户
        hashed_password = hash_password(user_create.password)
        db_user = User(
            user_id=str(uuid.uuid4()),  # 生成唯一的UUID作为user_id
            email=user_create.email,
            password_hash=hashed_password,
            is_active=True
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return db_user
    
    @staticmethod
    def authenticate_user(db: Session, user_login: UserLogin) -> Optional[User]:
        """验证用户凭据"""
        user = db.query(User).filter(User.email == user_login.email).first()
        
        if not user or not verify_password(user_login.password, user.password_hash):
            return None
        
        return user
    
    @staticmethod
    def get_current_user(db: Session, credentials: HTTPAuthorizationCredentials) -> User:
        """获取当前认证用户"""
        token = credentials.credentials
        payload = verify_token(token)
        
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # JWT token中的sub字段是user_id（字符串），不是数据库的id（整数）
        user = db.query(User).filter(User.user_id == user_id_str).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
    
    @staticmethod
    def create_user_api_key(db: Session, user_id: int, name: str) -> ApiKey:
        """为用户创建API密钥"""
        api_key = generate_api_key()
        hashed_key = hash_api_key(api_key)
        public_id = generate_public_id()
        
        db_api_key = ApiKey(
            user_id_fk=user_id,
            label=name,
            public_id=public_id,
            secret_hash=hashed_key,
            is_active=True
        )
        
        db.add(db_api_key)
        db.commit()
        db.refresh(db_api_key)
        
        # 返回原始API密钥（仅此一次）
        db_api_key.key = api_key
        return db_api_key
    
    @staticmethod
    def verify_api_key(db: Session, api_key: str) -> Optional[User]:
        """验证API密钥并返回关联用户"""
        try:
            hashed_key = hash_api_key(api_key)
            
            db_api_key = db.query(ApiKey).filter(
                ApiKey.secret_hash == hashed_key,
                ApiKey.is_active == True
            ).first()
            
            if not db_api_key:
                return None
            
            # 更新最后使用时间
            db_api_key.last_used_at = datetime.utcnow()
            db.commit()
            
            return db_api_key.user
        except Exception as e:
            print(f"Error in verify_api_key: {e}")
            db.rollback()
            return None
    
    @staticmethod
    def get_current_user_from_api_key(db: Session, api_key: str) -> User:
        """Get current user from API key header."""
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required"
            )
        
        user = AuthService.verify_api_key(db, api_key)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        return user
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """根据邮箱查询用户完整信息"""
        user = db.query(User).filter(User.email == email).first()
        return user
    
    @staticmethod
    def create_connection(db: Session, user: User, toolkit: str, user_id: str) -> m.AuthConnection:
        """创建OAuth连接的共同逻辑"""
        # 验证用户ID匹配
        if user.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")
        
        # 生成连接ID
        connection_id = str(uuid.uuid4())
        
        # 生成真正的OAuth重定向URL
        redirect_url = ""
        if toolkit == "github":
            try:
                from ..core.oauth_service import OAuthService
                # 使用工具包连接专用的回调URL，并在state中包含connection_id
                callback_uri = "http://localhost:3000/auth/connection/callback"
                auth_url, state = OAuthService.generate_auth_url(db, "github", callback_uri)
                # 在URL中添加connection_id参数，以便前端能够识别这是工具包连接
                separator = "&" if "?" in auth_url else "?"
                redirect_url = f"{auth_url}{separator}connection_id={connection_id}"
            except Exception as e:
                # 如果OAuth服务不可用，使用占位符URL
                redirect_url = f"https://auth.example.com/{uuid.uuid4()}"
        else:
            # 其他工具包使用占位符URL
            redirect_url = f"https://auth.example.com/{uuid.uuid4()}"
        
        # 创建连接记录
        db_conn = m.AuthConnection(
            connection_id=connection_id,
            user_id_fk=user.id,
            toolkit=toolkit,
            redirect_url=redirect_url,
            status="pending"
        )
        db.add(db_conn)
        db.commit()
        db.refresh(db_conn)
        
        return db_conn
    
    @staticmethod
    def get_connection_status(db: Session, user: User, connection_id: str) -> m.AuthConnection:
        """获取连接状态的共同逻辑"""
        # 查找连接记录
        db_conn = db.query(m.AuthConnection).filter_by(connection_id=connection_id).first()
        if db_conn is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        
        # 验证所有权
        if db_conn.user_id_fk != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this connection")
        
        # 模拟OAuth流程完成（首次轮询时自动授权）
        if db_conn.status == "pending":
            db_conn.status = "authorized"
            
            # 创建连接账户
            connected_account = m.ConnectedAccount(
                user_id_fk=user.id,
                toolkit=db_conn.toolkit,
                display_name=f"{db_conn.toolkit.title()} Account",
                token_enc=f"demo_token_{uuid.uuid4().hex[:16]}",
                status="active"
            )
            db.add(connected_account)
            
            # 更新连接记录
            db_conn.connected_account_id_fk = connected_account.id
            
            db.commit()
            db.refresh(connected_account)
        
        return db_conn
    
    @staticmethod
    def list_connected_accounts(db: Session, user: User, user_id: str, toolkit: Optional[str] = None) -> List[m.ConnectedAccount]:
        """列出连接账户的共同逻辑"""
        if user.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")
        
        query = db.query(m.ConnectedAccount).filter_by(user_id_fk=user.id)
        if toolkit:
            query = query.filter_by(toolkit=toolkit)
        
        return query.all()
    
    @staticmethod
    def revoke_connected_account(db: Session, user: User, connected_account_id: str) -> m.ConnectedAccount:
        """撤销连接账户的共同逻辑"""
        acc = db.query(m.ConnectedAccount).filter_by(id=int(connected_account_id)).first()
        if not acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected account not found")
        if acc.user_id_fk != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to revoke this account")
        
        # 删除账户
        db.delete(acc)
        db.commit()
        
        return acc