"""OAuth认证服务

提供Google和GitHub OAuth认证的核心功能，包括：
- OAuth认证URL生成
- 授权码交换访问令牌
- 用户信息获取
- OAuth账户管理
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
from .security import DataMasking
from .utils.config import settings


class OAuthService:
    """OAuth认证服务类"""
    
    # OAuth提供商配置
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
        """获取OAuth提供商配置"""
        return db.query(m.OAuthProvider).filter(
            m.OAuthProvider.name == provider_name,
            m.OAuthProvider.is_active == True
        ).first()
    
    @classmethod
    def generate_auth_url(cls, db: Session, provider_name: str, redirect_uri: str) -> tuple[str, str]:
        """生成OAuth认证URL
        
        Returns:
            tuple: (auth_url, state) - 认证URL和状态参数
        """
        provider = cls.get_provider(db, provider_name)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # 生成随机状态参数防止CSRF攻击
        state = secrets.token_urlsafe(32)
        
        # 构建认证URL参数
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
        """用授权码交换访问令牌"""
        import logging
        logger = logging.getLogger(__name__)
        
        provider = cls.get_provider(db, provider_name)
        if not provider:
            logger.error(f"不支持的OAuth提供商: {provider_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # 准备令牌交换请求
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
        
        logger.info(f"向{provider_name}发送令牌交换请求: {provider.token_url}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    provider.token_url,
                    data=token_data,
                    headers=headers
                )
                
                logger.info(f"{provider_name}令牌交换响应: status={response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"{provider_name}令牌交换失败: status={response.status_code}, response={error_text}")
                    
                    # 检查是否是授权码已使用的错误
                    if "invalid_grant" in error_text or "authorization code" in error_text.lower():
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="授权码无效或已被使用，这可能是由于重复请求导致的"
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Failed to exchange authorization code for token: {error_text}"
                        )
                
                token_response = response.json()
                logger.info(f"{provider_name}令牌交换成功")
                return token_response
                
            except httpx.RequestError as e:
                logger.error(f"{provider_name}令牌交换网络错误: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Network error during token exchange: {str(e)}"
                )
    
    @classmethod
    async def get_user_info(cls, db: Session, provider_name: str, access_token: str) -> OAuthUserInfo:
        """获取OAuth用户信息"""
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
            
            # 根据不同提供商解析用户信息
            if provider_name == "google":
                return OAuthUserInfo(
                    oauth_user_id=user_data["id"],
                    email=user_data["email"],
                    display_name=user_data.get("name", ""),
                    avatar_url=user_data.get("picture")
                )
            elif provider_name == "github":
                # GitHub可能需要额外请求获取邮箱
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
        """创建或更新OAuth账户关联"""
        provider = cls.get_provider(db, provider_name)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported OAuth provider: {provider_name}"
            )
        
        # 查找现有的OAuth账户
        oauth_account = db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.provider_id_fk == provider.id,
            m.UserOAuthAccount.oauth_user_id == oauth_user_info.oauth_user_id
        ).first()
        
        # 计算令牌过期时间
        expires_in = token_data.get("expires_in", 3600)  # 默认1小时
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        if oauth_account:
            # 更新现有账户
            oauth_account.user_id_fk = user_id
            oauth_account.email = oauth_user_info.email
            oauth_account.display_name = oauth_user_info.display_name
            oauth_account.avatar_url = oauth_user_info.avatar_url
            oauth_account.access_token = DataMasking.encrypt_token_simple(token_data["access_token"], settings.JWT_SECRET)
            if "refresh_token" in token_data:
                oauth_account.refresh_token = DataMasking.encrypt_token_simple(token_data["refresh_token"], settings.JWT_SECRET)
            oauth_account.token_expires_at = token_expires_at
            oauth_account.updated_at = datetime.utcnow()
        else:
            # 创建新的OAuth账户
            oauth_account = m.UserOAuthAccount(
                user_id_fk=user_id,
                provider_id_fk=provider.id,
                oauth_user_id=oauth_user_info.oauth_user_id,
                email=oauth_user_info.email,
                display_name=oauth_user_info.display_name,
                avatar_url=oauth_user_info.avatar_url,
                access_token=DataMasking.encrypt_token_simple(token_data["access_token"], settings.JWT_SECRET),
                refresh_token=DataMasking.encrypt_token_simple(token_data.get("refresh_token", ""), settings.JWT_SECRET),
                token_expires_at=token_expires_at,
                is_primary=False  # 默认不是主要登录方式
            )
            db.add(oauth_account)
        
        db.commit()
        db.refresh(oauth_account)
        return oauth_account
    
    @classmethod
    def find_user_by_oauth(cls, db: Session, provider_name: str, oauth_user_id: str) -> Optional[m.User]:
        """通过OAuth信息查找用户"""
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
        """获取用户的所有OAuth账户"""
        return db.query(m.UserOAuthAccount).filter(
            m.UserOAuthAccount.user_id_fk == user_id
        ).all()