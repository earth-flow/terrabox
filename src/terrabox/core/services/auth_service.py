"""Authentication service for user management and API key operations."""
import uuid
import re
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from ..schemas import UserCreate, UserLogin
from ...db.models import User, ApiKey
from ..utils.auth import (
    hash_password, verify_password, verify_token, 
    generate_api_key, hash_api_key, generate_public_id
)


logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication and user management operations."""
    
    @staticmethod
    def create_user(db: Session, user_create: UserCreate) -> User:
        """Create new user"""
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == user_create.email).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = hash_password(user_create.password)
        db_user = User(
            user_id=str(uuid.uuid4()),  # Generate unique UUID as user_id
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
        """Verify user credentials"""
        user = db.query(User).filter(User.email == user_login.email).first()
        
        if not user or not verify_password(user_login.password, user.password_hash):
            return None
        
        return user
    
    @staticmethod
    def get_current_user(db: Session, credentials: HTTPAuthorizationCredentials) -> User:
        """Get current authenticated user"""
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
        
        # The sub field in JWT token is user_id (string), not database id (integer)
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
        """Create API key for user"""
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
        
        # Return original API key (only this once)
        db_api_key.key = api_key
        return db_api_key
    
    @staticmethod
    def verify_api_key(db: Session, api_key: str) -> Optional[User]:
        """Verify API key and return associated user"""
        try:
            hashed_key = hash_api_key(api_key)
            
            db_api_key = db.query(ApiKey).filter(
                ApiKey.secret_hash == hashed_key,
                ApiKey.is_active == True
            ).first()
            
            # Must have valid API Key and associated user must be active
            if not db_api_key or not getattr(db_api_key, "user", None) or not db_api_key.user.is_active:
                return None
            
            # Update last used time
            db_api_key.last_used_at = datetime.utcnow()
            db.commit()
            
            return db_api_key.user
        except Exception as e:
            logger.error(f"Error in verify_api_key: {e}")
            db.rollback()
            return None
    
    @staticmethod
    def get_current_user_from_api_key(db: Session, api_key: str) -> User:
        """Get current user from API key header."""
        if not api_key or not api_key.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required"
            )
        # Normalize and validate API Key format to avoid accidental loose matching or empty string bypass
        normalized_key = api_key.strip()
        if not re.match(r"^tlk_(live|test)_[A-Za-z0-9_\-]{16,}$", normalized_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key format"
            )
        
        user = AuthService.verify_api_key(db, normalized_key)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        return user
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Query user complete information by email"""
        user = db.query(User).filter(User.email == email).first()
        return user