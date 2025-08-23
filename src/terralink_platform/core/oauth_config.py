"""OAuth配置管理

管理OAuth提供商的配置信息，包括客户端ID、密钥等敏感信息。
实际生产环境中，这些配置应该通过环境变量或安全的配置管理系统提供。
"""

import os
from typing import Dict, Any

class OAuthConfig:
    """OAuth配置类"""
    
    @classmethod
    def get_provider_config(cls, provider_name: str) -> Dict[str, Any]:
        """获取OAuth提供商配置
        
        Args:
            provider_name: 提供商名称 (google, github)
            
        Returns:
            包含客户端ID、密钥等配置的字典
        """
        if provider_name == "google":
            return {
                "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
                "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
                "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scopes": "openid email profile"
            }
        elif provider_name == "github":
            return {
                "client_id": os.getenv("GITHUB_OAUTH_CLIENT_ID", ""),
                "client_secret": os.getenv("GITHUB_OAUTH_CLIENT_SECRET", ""),
                "auth_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "user_info_url": "https://api.github.com/user",
                "scopes": "user:email"
            }
        else:
            raise ValueError(f"Unsupported OAuth provider: {provider_name}")
    
    @classmethod
    def is_provider_configured(cls, provider_name: str) -> bool:
        """检查OAuth提供商是否已配置
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            True if configured, False otherwise
        """
        config = cls.get_provider_config(provider_name)
        return bool(config.get("client_id")) and bool(config.get("client_secret"))
    
    @classmethod
    def get_configured_providers(cls) -> list[str]:
        """获取已配置的OAuth提供商列表
        
        Returns:
            已配置的提供商名称列表
        """
        providers = ["google", "github"]
        return [p for p in providers if cls.is_provider_configured(p)]

# 环境变量配置说明
"""
要启用OAuth功能，请设置以下环境变量：

Google OAuth:
- GOOGLE_OAUTH_CLIENT_ID: Google OAuth应用的客户端ID
- GOOGLE_OAUTH_CLIENT_SECRET: Google OAuth应用的客户端密钥

GitHub OAuth:
- GITHUB_OAUTH_CLIENT_ID: GitHub OAuth应用的客户端ID  
- GITHUB_OAUTH_CLIENT_SECRET: GitHub OAuth应用的客户端密钥

获取这些配置的步骤：

1. Google OAuth:
   - 访问 https://console.developers.google.com/
   - 创建新项目或选择现有项目
   - 启用 Google+ API
   - 创建OAuth 2.0客户端ID
   - 设置授权重定向URI: http://localhost:3000/auth/callback

2. GitHub OAuth:
   - 访问 https://github.com/settings/applications/new
   - 创建新的OAuth应用
   - 设置Authorization callback URL: http://localhost:3000/auth/callback
   - 获取Client ID和Client Secret
"""