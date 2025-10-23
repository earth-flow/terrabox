# Google OAuth 配置指南

## 问题诊断

如果您遇到 `invalid_grant` 错误，通常是由于以下原因之一：

1. **Redirect URI 不匹配** - 最常见的原因
2. **Authorization code 已被使用**
3. **Authorization code 过期**

## 解决方案

### 1. 检查 Google Cloud Console 配置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 选择您的项目
3. 导航到 "APIs & Services" > "Credentials"
4. 找到您的 OAuth 2.0 客户端 ID
5. 点击编辑（铅笔图标）

### 2. 配置正确的 Redirect URI

在 "Authorized redirect URIs" 部分，确保添加以下 URI：

```
http://localhost:3000/auth/callback
```

**重要提示：**
- URI 必须完全匹配，包括协议（http/https）、域名、端口和路径
- 不要在末尾添加斜杠
- 确保端口号与前端应用运行的端口一致

### 3. 当前配置验证

根据测试结果，当前配置：
- ✅ Client ID: 已配置
- ✅ Client Secret: 已配置  
- ✅ Auth URL: 正确
- ✅ Token URL: 正确
- ✅ Redirect URI: 在请求中正确包含

### 4. 常见问题排查

#### 问题：`invalid_grant` 错误
**可能原因：**
1. Google Cloud Console 中的 redirect URI 配置不正确
2. 前端应用运行在不同的端口
3. Authorization code 被重复使用

**解决方法：**
1. 检查 Google Cloud Console 中的 redirect URI 配置
2. 确认前端应用运行在 `http://localhost:3000`
3. 清除浏览器缓存和 sessionStorage
4. 重新发起 OAuth 流程

#### 问题：前端运行在不同端口
如果前端运行在其他端口（如 3001），需要：
1. 在 Google Cloud Console 中添加新的 redirect URI：`http://localhost:3001/auth/callback`
2. 或者修改前端配置使其运行在 3000 端口

### 5. 测试步骤

1. 确保后端服务运行在正确端口
2. 确保前端应用运行在 `http://localhost:3000`
3. 访问前端应用的登录页面
4. 点击 Google 登录按钮
5. 完成 Google 授权流程
6. 检查是否成功回调到 `/auth/callback`

### 6. 调试信息

当前环境变量配置：
```bash
GOOGLE_OAUTH_CLIENT_ID=116921976899-s0ikr354ecjm77r8ma20bdprtrbgiged.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=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
```

生成的认证 URL 示例：
```
https://accounts.google.com/o/oauth2/v2/auth?client_id=116921976899-s0ikr354ecjm77r8ma20bdprtrbgiged.apps.googleusercontent.com&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback&scope=openid+email+profile&response_type=code&state=...
```

### 7. 下一步

如果问题仍然存在，请：
1. 检查 Google Cloud Console 中的 OAuth 配置
2. 确认 redirect URI 完全匹配
3. 检查前端应用的实际运行端口
4. 查看浏览器开发者工具中的网络请求