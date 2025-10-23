"""OAuth authentication service

Provides core functionality for Google and GitHub OAuth authentication, including:
- OAuth authentication URL generation
- Authorization code exchange for access tokens
- User information retrieval
- OAuth account management
"""

import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode, parse_qs

import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..db import models as m
from .schemas import OAuthUserInfo
from .security import encrypt_credentials, decrypt_credentials
from .utils.config import settings


class OAuthService:
    """OAuth authentication service class"""
    
    @staticmethod
    def _encrypt_token(token: str) -> str:
        """Securely encrypt single token"""
        if not token:
            return ""
        return encrypt_credentials({"token": token})
    
    @staticmethod
    def _decrypt_token(encrypted_token: str) -> str:
        """Decrypt single token"""
        if not encrypted_token:
            return ""
        try:
            decrypted = decrypt_credentials(encrypted_token)
            return decrypted.get("token", "")
        except Exception:
            return ""
    
    # OAuth provider configuration
    PROVIDERS = {
        "google": {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
            "scopes": "openid email profile"
        },
        "github": {
            "auth_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "user_info_url": "https://api.github.com/user",
            "scopes": "user:email"
        }
    }
    
    @classmethod
    def get_provider(cls, db: Session, provider_name: str) -> Optional[m.OAuthProvider]:
        """Get OAuth provider configuration"""
        return db.query(m.OAuthProvider).filter(
            m.OAuthProvider.name == provider_name,
            m.OAuthProvider.is_active == True
        ).first()
    
    @classmethod
    def generate_auth_url(cls, db: Session, provider_name: str, redirect_uri: str) -> tuple[str, str]:
        """Generate OAuth authentication URL
        
        Returns:
            tuple: (auth_url, state) - Authentication URL and state parameter
        """
        provider = cls.get_provider(db, provider_name)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # Generate random state parameter to prevent CSRF attacks
        state = secrets.token_urlsafe(32)
        
        # Build authentication URL parameters
        params = {
            "client_id": provider.client_id,
            "redirect_uri": redirect_uri,
            "scope": provider.scopes,
            "response_type": "code",
            "state": state
        }
        
        auth_url = f"{provider.auth_url}?{urlencode(params)}"
        return auth_url, state
    
    @classmethod
    async def exchange_code_for_token(cls, db: Session, provider_name: str, 
                                    code: str, redirect_uri: str) -> Dict[str, Any]:
        """Use authorization code to exchange for access token"""
        import logging
        logger = logging.getLogger(__name__)
        
        provider = cls.get_provider(db, provider_name)
        if not provider:
            logger.error(f"Unsupported OAuth provider: {provider_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # Prepare token exchange request
        token_data = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        logger.info(f"Sending token exchange request to {provider_name}: {provider.token_url}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    provider.token_url,
                    data=token_data,
                    headers=headers
                )
                
                logger.info(f"{provider_name} token exchange response: status={response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"{provider_name} token exchange failed: status={response.status_code}, response={error_text}")
                    
                    # Check if error is related to invalid grant
                    if "invalid_grant" in error_text or "authorization code" in error_text.lower():
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Authorization code is invalid or already used, this may be due to repeated request"
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Failed to exchange authorization code for token: {error_text}"
                        )
                
                token_response = response.json()
                logger.info(f"{provider_name} token exchange successful")
                return token_response
                
            except httpx.RequestError as e:
                logger.error(f"{provider_name} token exchange network error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Network error during token exchange: {str(e)}"
                )
    
    @classmethod
    async def get_user_info(cls, db: Session, provider_name: str, access_token: str) -> OAuthUserInfo:
        """Get OAuth user information"""
        provider = cls.get_provider(db, provider_name)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                provider.user_info_url,
                headers=headers
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch user information"
                )
            
            user_data = response.json()
            
            # Parse user information according to different providers
            if provider_name == "google":
                return OAuthUserInfo(
                    oauth_user_id=user_data["id"],
                    email=user_data["email"],
                    display_name=user_data.get("name", ""),
                    avatar_url=user_data.get("picture")
                )
            elif provider_name == "github":
                # GitHub may need extra request to get email
                email = user_data.get("email")
                if not email:
                    email_response = await client.get(
                        "https://api.github.com/user/emails",
                        headers=headers
                    )
                    if email_response.status_code == 200:
                        emails = email_response.json()
                        primary_email = next((e for e in emails if e.get("primary")), None)
                        if primary_email:
                            email = primary_email["email"]
                
                return OAuthUserInfo(
                    oauth_user_id=str(user_data["id"]),
                    email=email or "",
                    display_name=user_data.get("name") or user_data.get("login", ""),
                    avatar_url=user_data.get("avatar_url")
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported provider: {provider_name}"
                )
    
    @classmethod
    def create_or_update_oauth_account(cls, db: Session, user_id: int, provider_name: str,
                                     oauth_user_info: OAuthUserInfo, token_data: Dict[str, Any]) -> m.UserOAuthAccount:
        """Create or update OAuth account association"""
        provider = cls.get_provider(db, provider_name)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # Look for existing OAuth account
        oauth_account = db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.provider_id_fk == provider.id,
            m.UserOAuthAccount.oauth_user_id == oauth_user_info.oauth_user_id
        ).first()
        
        # Compute token expiration time
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        if oauth_account:
            # Update existing account
            oauth_account.user_id_fk = user_id
            oauth_account.email = oauth_user_info.email
            oauth_account.display_name = oauth_user_info.display_name
            oauth_account.avatar_url = oauth_user_info.avatar_url
            oauth_account.access_token = cls._encrypt_token(token_data["access_token"])
            if "refresh_token" in token_data:
                oauth_account.refresh_token = cls._encrypt_token(token_data["refresh_token"])
            oauth_account.token_expires_at = token_expires_at
            oauth_account.updated_at = datetime.utcnow()
        else:
            # Create new OAuth account
            oauth_account = m.UserOAuthAccount(
                user_id_fk=user_id,
                provider_id_fk=provider.id,
                oauth_user_id=oauth_user_info.oauth_user_id,
                email=oauth_user_info.email,
                display_name=oauth_user_info.display_name,
                avatar_url=oauth_user_info.avatar_url,
                access_token=cls._encrypt_token(token_data["access_token"]),
                refresh_token=cls._encrypt_token(token_data.get("refresh_token", "")),
                token_expires_at=token_expires_at,
                is_primary=False  # Default is not primary login method
            )
            db.add(oauth_account)
        
        db.commit()
        db.refresh(oauth_account)
        return oauth_account
    
    @classmethod
    def find_user_by_oauth(cls, db: Session, provider_name: str, oauth_user_id: str) -> Optional[m.User]:
        """Find user by OAuth information"""
        provider = cls.get_provider(db, provider_name)
        if not provider:
            return None
        
        oauth_account = db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.provider_id_fk == provider.id,
            m.UserOAuthAccount.oauth_user_id == oauth_user_id
        ).first()
        
        if oauth_account:
            return db.query(m.User).filter(m.User.id == oauth_account.user_id_fk).first()
        
        return None
    
    @classmethod
    def get_user_oauth_accounts(cls, db: Session, user_id: int) -> list[m.UserOAuthAccount]:
        """Get user's all OAuth accounts"""
        return db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.user_id_fk == user_id
        ).all()