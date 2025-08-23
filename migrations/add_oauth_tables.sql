-- 添加OAuth提供商配置表
CREATE TABLE oauth_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(32) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    client_secret VARCHAR(255) NOT NULL,
    auth_url VARCHAR(512) NOT NULL,
    token_url VARCHAR(512) NOT NULL,
    user_info_url VARCHAR(512) NOT NULL,
    scopes VARCHAR(512),
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 添加用户OAuth账户关联表
CREATE TABLE user_oauth_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_fk INTEGER NOT NULL,
    provider_id_fk INTEGER NOT NULL,
    oauth_user_id VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    display_name VARCHAR(128),
    avatar_url VARCHAR(512),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at DATETIME,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_fk) REFERENCES users (id),
    FOREIGN KEY (provider_id_fk) REFERENCES oauth_providers (id),
    UNIQUE (provider_id_fk, oauth_user_id)
);

-- 创建索引
CREATE INDEX ix_oauth_user_provider ON user_oauth_accounts (user_id_fk, provider_id_fk);

-- 插入默认的OAuth提供商配置（需要在实际部署时配置真实的client_id和client_secret）
INSERT INTO oauth_providers (name, display_name, client_id, client_secret, auth_url, token_url, user_info_url, scopes) VALUES
('google', 'Google', '116921976899-s0ikr354ecjm77r8ma20bdprtrbgiged.apps.googleusercontent.com', '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', 
 'https://accounts.google.com/o/oauth2/v2/auth', 
 'https://oauth2.googleapis.com/token', 
 'https://www.googleapis.com/oauth2/v2/userinfo', 
 'openid email profile'),
('github', 'GitHub', 'Ov23liRzD7AXQH0y5fFo', 'b49440bcbd4c252f5f0c0a7d2f290b0c272dc5c5', 
 'https://github.com/login/oauth/authorize', 
 'https://github.com/login/oauth/access_token', 
 'https://api.github.com/user', 
 'user:email');