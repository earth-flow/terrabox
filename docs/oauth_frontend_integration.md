# OAuth前端集成指南

本文档说明如何在前端应用中集成Google和GitHub OAuth登录功能。

## API端点概览

### 1. 获取可用的OAuth提供商
```http
GET /v1/oauth/providers
```

响应示例：
```json
[
  {
    "id": 1,
    "name": "google",
    "display_name": "Google",
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "scopes": "openid email profile",
    "is_active": true
  },
  {
    "id": 2,
    "name": "github",
    "display_name": "GitHub",
    "auth_url": "https://github.com/login/oauth/authorize",
    "scopes": "user:email",
    "is_active": true
  }
]
```

### 2. 发起OAuth认证
```http
POST /v1/oauth/auth
Content-Type: application/json

{
  "provider": "google",
  "redirect_uri": "http://localhost:3000/auth/callback"
}
```

响应示例：
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...",
  "state": "random_state_string"
}
```

### 3. 处理OAuth回调
```http
POST /v1/oauth/callback
Content-Type: application/json

{
  "provider": "google",
  "code": "authorization_code_from_oauth_provider",
  "state": "state_from_step_2"
}
```

响应示例：
```json
{
  "access_token": "jwt_token",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "user_id": "user_123",
    "email": "user@example.com",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

## 前端实现示例

### React实现

```typescript
// types/auth.ts
export interface OAuthProvider {
  id: number;
  name: string;
  display_name: string;
  auth_url: string;
  scopes?: string;
  is_active: boolean;
}

export interface OAuthAuthResponse {
  auth_url: string;
  state: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: number;
    user_id: string;
    email: string;
    is_active: boolean;
    created_at: string;
  };
}
```

```typescript
// services/authService.ts
const API_BASE_URL = 'http://localhost:8000';

export class AuthService {
  // 获取可用的OAuth提供商
  static async getOAuthProviders(): Promise<OAuthProvider[]> {
    const response = await fetch(`${API_BASE_URL}/v1/oauth/providers`);
    if (!response.ok) {
      throw new Error('Failed to fetch OAuth providers');
    }
    return response.json();
  }

  // 发起OAuth认证
  static async initiateOAuth(provider: string, redirectUri?: string): Promise<OAuthAuthResponse> {
    const response = await fetch(`${API_BASE_URL}/v1/oauth/auth`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        provider,
        redirect_uri: redirectUri || `${window.location.origin}/auth/callback`,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to initiate OAuth');
    }
    return response.json();
  }

  // 处理OAuth回调
  static async handleOAuthCallback(
    provider: string,
    code: string,
    state: string
  ): Promise<TokenResponse> {
    const response = await fetch(`${API_BASE_URL}/v1/oauth/callback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        provider,
        code,
        state,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'OAuth callback failed');
    }
    return response.json();
  }
}
```

```tsx
// components/OAuthLoginButton.tsx
import React from 'react';
import { AuthService } from '../services/authService';

interface OAuthLoginButtonProps {
  provider: string;
  displayName: string;
  onSuccess?: (token: TokenResponse) => void;
  onError?: (error: string) => void;
}

export const OAuthLoginButton: React.FC<OAuthLoginButtonProps> = ({
  provider,
  displayName,
  onSuccess,
  onError,
}) => {
  const handleLogin = async () => {
    try {
      // 发起OAuth认证
      const authResponse = await AuthService.initiateOAuth(provider);
      
      // 保存state到sessionStorage用于验证
      sessionStorage.setItem('oauth_state', authResponse.state);
      sessionStorage.setItem('oauth_provider', provider);
      
      // 重定向到OAuth提供商
      window.location.href = authResponse.auth_url;
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'OAuth login failed');
    }
  };

  return (
    <button
      onClick={handleLogin}
      className="oauth-login-button"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '12px 24px',
        border: '1px solid #ddd',
        borderRadius: '6px',
        background: 'white',
        cursor: 'pointer',
        fontSize: '14px',
      }}
    >
      {provider === 'google' && (
        <svg width="18" height="18" viewBox="0 0 24 24">
          {/* Google图标SVG */}
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
      )}
      {provider === 'github' && (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="#333">
          {/* GitHub图标SVG */}
          <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
        </svg>
      )}
      使用 {displayName} 登录
    </button>
  );
};
```

```tsx
// pages/AuthCallback.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AuthService } from '../services/authService';

export const AuthCallback: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        const code = searchParams.get('code');
        const state = searchParams.get('state');
        const provider = sessionStorage.getItem('oauth_provider');
        const savedState = sessionStorage.getItem('oauth_state');

        if (!code || !state || !provider) {
          throw new Error('Missing required parameters');
        }

        if (state !== savedState) {
          throw new Error('Invalid state parameter');
        }

        // 处理OAuth回调
        const tokenResponse = await AuthService.handleOAuthCallback(provider, code, state);
        
        // 保存token到localStorage
        localStorage.setItem('access_token', tokenResponse.access_token);
        localStorage.setItem('user', JSON.stringify(tokenResponse.user));
        
        // 清理sessionStorage
        sessionStorage.removeItem('oauth_state');
        sessionStorage.removeItem('oauth_provider');
        
        // 重定向到主页
        navigate('/', { replace: true });
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Authentication failed');
      } finally {
        setLoading(false);
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div>正在处理登录...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div style={{ color: 'red' }}>登录失败: {error}</div>
        <button onClick={() => navigate('/login')}>返回登录页</button>
      </div>
    );
  }

  return null;
};
```

```tsx
// pages/LoginPage.tsx
import React, { useEffect, useState } from 'react';
import { OAuthLoginButton } from '../components/OAuthLoginButton';
import { AuthService } from '../services/authService';
import type { OAuthProvider } from '../types/auth';

export const LoginPage: React.FC = () => {
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadProviders = async () => {
      try {
        const oauthProviders = await AuthService.getOAuthProviders();
        setProviders(oauthProviders);
      } catch (error) {
        console.error('Failed to load OAuth providers:', error);
      } finally {
        setLoading(false);
      }
    };

    loadProviders();
  }, []);

  if (loading) {
    return <div>加载中...</div>;
  }

  return (
    <div style={{ maxWidth: '400px', margin: '100px auto', padding: '20px' }}>
      <h2>登录到 Terralink</h2>
      
      {/* 传统邮箱密码登录表单 */}
      <form style={{ marginBottom: '30px' }}>
        <div style={{ marginBottom: '15px' }}>
          <input
            type="email"
            placeholder="邮箱地址"
            style={{ width: '100%', padding: '12px', border: '1px solid #ddd', borderRadius: '6px' }}
          />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <input
            type="password"
            placeholder="密码"
            style={{ width: '100%', padding: '12px', border: '1px solid #ddd', borderRadius: '6px' }}
          />
        </div>
        <button
          type="submit"
          style={{
            width: '100%',
            padding: '12px',
            background: '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          登录
        </button>
      </form>

      {/* OAuth登录选项 */}
      {providers.length > 0 && (
        <>
          <div style={{ textAlign: 'center', margin: '20px 0', color: '#666' }}>
            或者使用以下方式登录
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {providers.map((provider) => (
              <OAuthLoginButton
                key={provider.id}
                provider={provider.name}
                displayName={provider.display_name}
                onError={(error) => {
                  alert(`登录失败: ${error}`);
                }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
};
```

## 路由配置

确保在你的路由配置中添加OAuth回调路由：

```tsx
// App.tsx 或路由配置文件
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { AuthCallback } from './pages/AuthCallback';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        {/* 其他路由 */}
      </Routes>
    </BrowserRouter>
  );
}
```

## 注意事项

1. **重定向URI配置**: 确保在OAuth应用配置中设置正确的重定向URI（如 `http://localhost:3000/auth/callback`）

2. **状态验证**: 使用state参数防止CSRF攻击，确保回调时验证state参数

3. **错误处理**: 实现适当的错误处理，包括网络错误、认证失败等情况

4. **Token管理**: 安全地存储和管理JWT token，考虑使用httpOnly cookies而不是localStorage

5. **环境配置**: 在后端正确配置OAuth应用的客户端ID和密钥

6. **HTTPS**: 生产环境中必须使用HTTPS

## 部署前检查清单

- [ ] 配置Google OAuth应用并获取客户端ID和密钥
- [ ] 配置GitHub OAuth应用并获取客户端ID和密钥
- [ ] 设置环境变量 `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- [ ] 设置环境变量 `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`
- [ ] 运行数据库迁移脚本添加OAuth相关表
- [ ] 在OAuth应用中配置正确的重定向URI
- [ ] 测试完整的OAuth流程
- [ ] 确保生产环境使用HTTPS