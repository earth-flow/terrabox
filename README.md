# Terralink Platform

Terralink Platform是一个基于FastAPI的后端服务，为Terralink SDK提供API支持。该平台提供用户认证、工具管理、API密钥管理等核心功能。

## 功能特性

### 🔐 认证系统
- **用户注册与登录**：支持邮箱密码注册，密码使用Argon2哈希加密
- **JWT认证**：为GUI应用提供Bearer Token认证
- **API Key认证**：为SDK提供API Key认证
- **密码策略**：强制密码最小长度和字符集要求
- **速率限制**：防止暴力破解和滥用

### 🔑 API Key管理
- **创建API Key**：支持自定义标签和前缀
- **列表查看**：查看用户所有API Key（已脱敏）
- **撤销功能**：安全删除不需要的API Key
- **数量限制**：每用户最多5个API Key

### 🛠️ 工具系统
- **插件架构**：支持动态加载工具插件
- **内置工具包**：预装常用工具
- **扩展点支持**：通过entry points加载第三方工具

## 快速开始

### 环境要求
- Python 3.9+
- SQLite（开发环境）或PostgreSQL（生产环境）

### 安装依赖

```bash
# 克隆项目
cd terralink_platform

# 安装依赖
pip install -e .

# 开发环境额外依赖
pip install -e ".[dev]"
```

### 环境配置

创建 `.env` 文件：

```env
# 数据库配置
TL_DB_URL=sqlite:///./terralink_platform.db

# JWT配置
TL_JWT_SECRET=your_jwt_secret_key_here

# API Key加密配置
TL_APIKEY_KDF_SECRET=your_apikey_secret_here

# 环境设置
TL_ENV=dev
```

**⚠️ 生产环境请务必更改默认密钥！**

### 启动服务

```bash
# 开发模式（自动重载）
uvicorn src.terralink_platform.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn src.terralink_platform.main:app --host 0.0.0.0 --port 8000
```

### 初始化数据库

```bash
# 运行初始化脚本
python scripts/init_db.py
```

## API文档

启动服务后，访问以下地址查看API文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 主要API端点

#### 认证相关
- `POST /v1/register` - 用户注册
- `POST /v1/login` - 用户登录（返回JWT）

#### API Key管理
- `POST /v1/api-keys` - 创建API Key
- `GET /v1/api-keys` - 列出API Keys
- `DELETE /v1/api-keys/{key_id}` - 撤销API Key

#### 工具相关
- `GET /v1/tools` - 获取可用工具列表
- `POST /v1/tools/{tool_name}/use` - 使用指定工具

## 开发指南

### 项目结构

```
terralink_platform/
├── src/terralink_platform/
│   ├── main.py              # 应用入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型
│   ├── security.py          # 安全工具
│   ├── rate_limit.py        # 速率限制
│   ├── db/                  # 数据库相关
│   │   ├── models.py        # SQLAlchemy模型
│   │   └── session.py       # 数据库会话
│   ├── routers/             # API路由
│   │   ├── auth.py          # 认证路由
│   │   ├── tools.py         # 工具路由
│   │   └── deps.py          # 依赖注入
│   ├── services/            # 业务逻辑
│   └── toolkits/            # 工具包
├── tests/                   # 测试文件
├── scripts/                 # 脚本工具
└── examples/                # 使用示例
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_auth.py

# 运行安全功能测试
python test_security_features.py
```

### 添加新工具

1. 在 `src/terralink_platform/toolkits/` 下创建新的工具模块
2. 实现工具接口
3. 在 `extensions.py` 中注册工具

### 数据库迁移

```bash
# 生成迁移文件
alembic revision --autogenerate -m "描述变更"

# 应用迁移
alembic upgrade head
```

## 安全考虑

- 🔒 密码使用Argon2哈希，安全性高
- 🔑 API Key使用HMAC-SHA256加密存储
- 🚦 内置速率限制防止滥用
- 📝 敏感信息在日志中自动脱敏
- 🛡️ JWT Token有过期时间限制

## 部署

### Docker部署

```dockerfile
# Dockerfile示例
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "src.terralink_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 生产环境配置

1. 使用PostgreSQL数据库
2. 配置Redis用于缓存和会话
3. 设置反向代理（Nginx）
4. 启用HTTPS
5. 配置日志收集

## 故障排除

### 常见问题

**Q: 数据库连接失败**
A: 检查 `TL_DB_URL` 环境变量配置是否正确

**Q: JWT认证失败**
A: 确认 `TL_JWT_SECRET` 已设置且与客户端一致

**Q: API Key无法使用**
A: 检查API Key格式和权限，确认未过期

### 日志查看

```bash
# 查看应用日志
tail -f logs/terralink_platform.log

# 查看错误日志
grep ERROR logs/terralink_platform.log
```

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交变更
4. 创建Pull Request

## 许可证

本项目采用MIT许可证。详见LICENSE文件。

## 联系方式

- 邮箱：xiongzhitong@gmail.com

---

**版本**: 0.1.0  
**更新**: 2025年8月16日