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
from typing import Optional, Dict, Any, List
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
    
    # OAuth provider configuration from environment variables
    @classmethod
    def get_provider_config(cls, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get OAuth provider configuration from environment variables"""
        provider_configs = {
            "google": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scopes": "openid email profile",
                "display_name": "Google"
            },
            "github": {
                "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
                "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
                "auth_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "user_info_url": "https://api.github.com/user",
                "scopes": "user:email",
                "display_name": "GitHub"
            },
            "microsoft": {
                "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
                "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
                "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "user_info_url": "https://graph.microsoft.com/v1.0/me",
                "scopes": "openid email profile",
                "display_name": "Microsoft"
            },
            "discord": {
                "client_id": settings.DISCORD_OAUTH_CLIENT_ID,
                "client_secret": settings.DISCORD_OAUTH_CLIENT_SECRET,
                "auth_url": "https://discord.com/api/oauth2/authorize",
                "token_url": "https://discord.com/api/oauth2/token",
                "user_info_url": "https://discord.com/api/users/@me",
                "scopes": "identify email",
                "display_name": "Discord"
            },
            "linkedin": {
                "client_id": settings.LINKEDIN_OAUTH_CLIENT_ID,
                "client_secret": settings.LINKEDIN_OAUTH_CLIENT_SECRET,
                "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
                "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
                "user_info_url": "https://api.linkedin.com/v2/people/~",
                "scopes": "r_liteprofile r_emailaddress",
                "display_name": "LinkedIn"
            }
        }
        
        config = provider_configs.get(provider_name)
        if not config:
            return None
            
        # Check if required credentials are configured
        if not config["client_id"] or not config["client_secret"]:
            return None
            
        return config
    
    @classmethod
    def get_available_providers(cls) -> List[Dict[str, str]]:
        """Get list of available OAuth providers with valid configuration"""
        providers = []
        provider_display_names = {
            "google": "Google",
            "github": "GitHub", 
            "microsoft": "Microsoft",
            "discord": "Discord",
            "linkedin": "LinkedIn"
        }
        
        for provider_name in ["google", "github", "microsoft", "discord", "linkedin"]:
            config = cls.get_provider_config(provider_name)
            if config:
                providers.append({
                    "name": provider_name,
                    "display_name": provider_display_names.get(provider_name, provider_name.title()),
                    "auth_url": config["auth_url"],
                    "scopes": config["scopes"],
                    "is_active": True
                })
        return providers
    
    @classmethod
    def generate_auth_url(cls, provider_name: str, redirect_uri: str = None) -> tuple[str, str]:
        """Generate OAuth authentication URL
        
        Args:
            provider_name: OAuth provider name
            redirect_uri: Redirect URI (optional, uses environment variable if not provided)
        
        Returns:
            tuple: (auth_url, state) - Authentication URL and state parameter
        """
        provider_config = cls.get_provider_config(provider_name)
        if not provider_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth provider '{provider_name}' is not configured. Please check that {provider_name.upper()}_OAUTH_CLIENT_ID and {provider_name.upper()}_OAUTH_CLIENT_SECRET environment variables are set."
            )
        
        # Use provided redirect_uri or default from environment
        if not redirect_uri:
            redirect_uri = settings.OAUTH_REDIRECT_URI
        
        # Generate random state parameter to prevent CSRF attacks
        state = secrets.token_urlsafe(32)
        
        # Build authentication URL parameters
        params = {
            "client_id": provider_config["client_id"],
            "redirect_uri": redirect_uri,
            "scope": provider_config["scopes"],
            "response_type": "code",
            "state": state
        }
        
        auth_url = f"{provider_config['auth_url']}?{urlencode(params)}"
        return auth_url, state
    
    @classmethod
    async def exchange_code_for_token(cls, provider_name: str, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Use authorization code to exchange for access token"""
        import logging
        logger = logging.getLogger(__name__)
        
        provider_config = cls.get_provider_config(provider_name)
        if not provider_config:
            logger.error(f"OAuth provider {provider_name} is not configured or missing credentials")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth provider '{provider_name}' is not configured. Please check that {provider_name.upper()}_OAUTH_CLIENT_ID and {provider_name.upper()}_OAUTH_CLIENT_SECRET environment variables are set."
            )
        
        # Prepare token exchange request
        token_data = {
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        logger.info(f"Sending token exchange request to {provider_name}: {provider_config['token_url']}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    provider_config["token_url"],
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
    async def get_user_info(cls, provider_name: str, access_token: str) -> OAuthUserInfo:
        """Get OAuth user information"""
        provider_config = cls.get_provider_config(provider_name)
        if not provider_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported or unconfigured OAuth provider: {provider_name}"
            )
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                provider_config["user_info_url"],
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
            elif provider_name == "microsoft":
                return OAuthUserInfo(
                    oauth_user_id=user_data["id"],
                    email=user_data.get("mail") or user_data.get("userPrincipalName", ""),
                    display_name=user_data.get("displayName", ""),
                    avatar_url=None  # Microsoft Graph API requires separate request for photo
                )
            elif provider_name == "discord":
                return OAuthUserInfo(
                    oauth_user_id=user_data["id"],
                    email=user_data.get("email", ""),
                    display_name=user_data.get("username", ""),
                    avatar_url=f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png" if user_data.get("avatar") else None
                )
            elif provider_name == "linkedin":
                # LinkedIn v2 API requires separate requests for email
                email = ""
                try:
                    email_response = await client.get(
                        "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))",
                        headers=headers
                    )
                    if email_response.status_code == 200:
                        email_data = email_response.json()
                        if email_data.get("elements"):
                            email = email_data["elements"][0]["handle~"]["emailAddress"]
                except:
                    pass
                
                return OAuthUserInfo(
                    oauth_user_id=user_data["id"],
                    email=email,
                    display_name=f"{user_data.get('firstName', {}).get('localized', {}).get('en_US', '')} {user_data.get('lastName', {}).get('localized', {}).get('en_US', '')}".strip(),
                    avatar_url=user_data.get("profilePicture", {}).get("displayImage~", {}).get("elements", [{}])[0].get("identifiers", [{}])[0].get("identifier")
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
        provider_config = cls.get_provider_config(provider_name)
        if not provider_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}. Please check {provider_name.upper()}_CLIENT_ID and {provider_name.upper()}_CLIENT_SECRET environment variables."
            )
        
        # Look for existing OAuth account
        oauth_account = db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.provider_name == provider_name,
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
                provider_name=provider_name,
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
        provider_config = cls.get_provider_config(provider_name)
        if not provider_config:
            return None
        
        oauth_account = db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.provider_name == provider_name,
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