# Terrakit Platform

Terrakit Platform是一个基于FastAPI的后端服务，为Terrakit SDK提供API支持。该平台提供用户认证、工具管理、API密钥管理等核心功能。

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

## 安装指南

### 系统要求

- **Python**: 3.9 或更高版本
- **操作系统**: Linux, macOS, Windows
- **数据库**: SQLite（开发环境）或 PostgreSQL（生产环境）
- **内存**: 最少 512MB RAM
- **磁盘空间**: 最少 100MB 可用空间

### 第一步：获取源码

```bash
# 方式1：从Git仓库克隆（推荐）
git clone <repository-url>
cd terrakit_platform

# 方式2：下载源码包
# 下载并解压源码包到本地目录
```

### 第二步：创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 第三步：安装依赖

```bash
# 安装基础依赖
pip install -e .

# 开发环境安装（包含测试工具）
pip install -e ".[dev]"

# 验证安装
python -c "import terrakit; print('安装成功！')"
```

### 第四步：环境配置

1. **复制配置模板**：
```bash
cp .env.example .env  # 如果存在模板文件
# 或手动创建 .env 文件
```

2. **编辑配置文件** `.env`：
```env
# ===================
# 数据库配置
# ===================
# 开发环境使用SQLite
TL_DB_URL=sqlite:///./terrakit_platform.db
# 生产环境使用PostgreSQL
# TL_DB_URL=postgresql://username:password@localhost:5432/terrakit_db

# ===================
# 安全配置
# ===================
# JWT密钥（生产环境必须更改）
TL_JWT_SECRET=your_super_secret_jwt_key_change_in_production
# API Key加密密钥（生产环境必须更改）
TL_APIKEY_KDF_SECRET=your_super_secret_apikey_kdf_change_in_production

# ===================
# 应用配置
# ===================
# 环境设置：dev, staging, production
TL_ENV=dev

# ===================
# OAuth配置（可选）
# ===================
# GitHub OAuth
GITHUB_OAUTH_CLIENT_ID=your_github_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_github_client_secret

# Google OAuth
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret
```

**🔒 安全提示**：
- 生产环境必须更改所有默认密钥
- 不要将 `.env` 文件提交到版本控制系统
- 使用强密码和随机密钥

### 第五步：初始化数据库

```bash
# 初始化数据库表结构和测试数据
python scripts/init_db.py

# 验证数据库
python -c "from terrakit.db.session import engine; print('数据库连接成功！')"
```

### 第六步：启动服务

```bash
# 开发模式（推荐，支持热重载）
uvicorn src.terrakit.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn src.terrakit.main:app --host 0.0.0.0 --port 8000 --workers 4

# 后台运行
nohup uvicorn src.terrakit.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

### 第七步：验证安装

1. **检查服务状态**：
```bash
# 访问健康检查端点
curl http://localhost:8000/
# 预期返回: {"status":"ok"}
```

2. **访问API文档**：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

3. **测试用户注册**：
```bash
curl -X POST "http://localhost:8000/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPassword123!"
  }'
```

## 使用指南

### 基本使用流程

1. **用户注册和登录**
2. **创建API Key**
3. **使用工具和服务**
4. **管理连接和配置**

### 用户认证

#### 注册新用户
```bash
curl -X POST "http://localhost:8000/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

#### 用户登录
```bash
curl -X POST "http://localhost:8000/v1/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

### API Key管理

#### 创建API Key
```bash
# 使用JWT Token
curl -X POST "http://localhost:8000/v1/api-keys" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "My API Key",
    "prefix": "myapp"
  }'
```

#### 使用API Key调用接口
```bash
curl -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"
```

### 工具使用

#### 获取可用工具列表
```bash
curl -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"
```

#### 使用特定工具
```bash
curl -X POST "http://localhost:8000/v1/tools/github/use" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "action": "list_repos",
      "owner": "username"
    }
  }'
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

### 连接管理

#### 创建连接
```bash
curl -X POST "http://localhost:8000/v1/connections" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My GitHub Connection",
    "type": "github",
    "config": {
      "token": "github_personal_access_token"
    }
  }'
```

#### 列出连接
```bash
curl -X GET "http://localhost:8000/v1/connections" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Python SDK 使用

#### 安装Python客户端
```bash
pip install terrakit-client  # 如果有独立客户端包
# 或直接使用requests
pip install requests
```

#### Python代码示例
```python
import requests
import json

class TerrakitClient:
    def __init__(self, base_url="http://localhost:8000", api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})
    
    def register(self, email, password):
        """注册新用户"""
        response = self.session.post(
            f"{self.base_url}/v1/register",
            json={"email": email, "password": password}
        )
        return response.json()
    
    def login(self, email, password):
        """用户登录"""
        response = self.session.post(
            f"{self.base_url}/v1/login",
            json={"email": email, "password": password}
        )
        return response.json()
    
    def create_api_key(self, jwt_token, label, prefix=None):
        """创建API Key"""
        headers = {"Authorization": f"Bearer {jwt_token}"}
        data = {"label": label}
        if prefix:
            data["prefix"] = prefix
        
        response = self.session.post(
            f"{self.base_url}/v1/gui/api-keys",
            json=data,
            headers=headers
        )
        return response.json()
    
    def list_tools(self):
        """获取工具列表"""
        response = self.session.get(f"{self.base_url}/v1/sdk/tools")
        return response.json()
    
    def execute_tool(self, tool_slug, inputs, metadata=None):
        """执行工具"""
        response = self.session.post(
            f"{self.base_url}/v1/sdk/tools/{tool_slug}/execute",
            json={"inputs": inputs, "metadata": metadata or {}}
        )
        return response.json()
    
    def list_toolkit_connections(self, toolkit):
        """获取指定工具包的连接列表"""
        response = self.session.get(
            f"{self.base_url}/v1/sdk/toolkits/{toolkit}/connections"
        )
        return response.json()
    
    def create_connection(self, toolkit, name, auth_method="oauth2"):
        """创建新连接"""
        data = {
            "name": name,
            "auth_method": auth_method,
            "credentials": {},
            "scopes": []
        }
        response = self.session.post(
            f"{self.base_url}/v1/sdk/toolkits/{toolkit}/connections",
            json=data
        )
        return response.json()
    
    def get_connection_status(self, connection_id):
        """获取连接状态"""
        response = self.session.get(
            f"{self.base_url}/v1/sdk/connections/{connection_id}"
        )
        return response.json()

# 使用示例
client = TerrakitClient()

# 注册用户
result = client.register("user@example.com", "SecurePassword123!")
print("注册结果:", result)

# 登录获取JWT
login_result = client.login("user@example.com", "SecurePassword123!")
jwt_token = login_result["access_token"]

# 创建API Key
api_key_result = client.create_api_key(jwt_token, "My Python Client")
api_key = api_key_result["key"]

# 使用API Key创建新客户端
api_client = TerrakitClient(api_key=api_key)

# 获取工具列表
tools = api_client.list_tools()
print("可用工具:", tools)

# 执行GitHub工具
github_result = api_client.execute_tool(
    "github-list-repos", 
    {"owner": "octocat"},
    {"connection_id": 1}  # 如果需要特定连接
)
print("GitHub仓库:", github_result)

# 获取GitHub工具包的连接列表
github_connections = api_client.list_toolkit_connections("github")
print("GitHub连接:", github_connections)

# 创建新的GitHub连接
new_connection = api_client.create_connection(
    "github", 
    "My GitHub Connection"
)
print("新连接:", new_connection)

# 检查连接状态
if "id" in new_connection:
    status = api_client.get_connection_status(new_connection["id"])
    print("连接状态:", status)
```

## 开发指南

### 项目结构

```
terrakit_platform/
├── src/terrakit/
│   ├── main.py              # FastAPI应用入口
│   ├── data.py              # 工具注册和管理
│   ├── extensions.py        # 扩展加载器
│   ├── core/                # 核心业务逻辑
│   │   ├── schemas.py       # Pydantic数据模型
│   │   ├── services/        # 业务服务层
│   │   └── utils/config.py  # 配置管理
│   ├── db/                  # 数据库层
│   │   ├── models.py        # SQLAlchemy模型
│   │   └── session.py       # 数据库会话
│   ├── routers/             # API路由
│   │   ├── auth.py          # 认证相关API
│   │   ├── api_keys.py      # API Key管理
│   │   ├── tools.py         # 工具相关API
│   │   └── connections.py   # 连接管理API
│   └── toolkits/            # 工具包
│       └── github.py        # GitHub工具包
├── tests/                   # 测试文件
├── scripts/                 # 脚本文件
└── docs/                    # 文档
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

1. 在 `src/terrakit/toolkits/` 下创建新的工具模块
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
CMD ["uvicorn", "src.terrakit.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 生产环境配置

1. 使用PostgreSQL数据库
2. 配置Redis用于缓存和会话
3. 设置反向代理（Nginx）
4. 启用HTTPS
5. 配置日志收集

## 故障排除

### 安装问题

#### 1. Python版本不兼容
```bash
# 检查Python版本
python --version
# 应该是3.9或更高版本

# 如果版本过低，安装新版本
# Ubuntu/Debian:
sudo apt update && sudo apt install python3.9
# macOS (使用Homebrew):
brew install python@3.9
# Windows: 从官网下载安装
```

#### 2. 依赖安装失败
```bash
# 升级pip
pip install --upgrade pip

# 清理缓存重新安装
pip cache purge
pip install -e . --no-cache-dir

# 如果遇到编译错误，安装构建工具
# Ubuntu/Debian:
sudo apt install build-essential python3-dev
# CentOS/RHEL:
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

#### 3. 虚拟环境问题
```bash
# 删除旧的虚拟环境
rm -rf venv

# 重新创建
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows

# 重新安装依赖
pip install -e .
```

### 运行时问题

#### 1. 数据库连接失败
```bash
# 检查数据库文件权限（SQLite）
ls -la terrakit_platform.db
chmod 664 terrakit_platform.db  # 如果权限不足

# 测试数据库连接
python -c "
from terrakit.db.session import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('数据库连接成功！')
"

# PostgreSQL连接测试
psql -h localhost -U username -d terrakit_db -c "SELECT 1;"
```

#### 2. 端口被占用
```bash
# 检查端口占用
netstat -tlnp | grep :8000
# 或
lsof -i :8000

# 杀死占用进程
kill -9 <PID>

# 使用其他端口启动
uvicorn src.terrakit.main:app --port 8001
```

#### 3. JWT Token问题
```bash
# 检查JWT配置
python -c "
from terrakit.core.utils.config import get_settings
settings = get_settings()
print('JWT Secret长度:', len(settings.jwt_secret))
print('JWT Secret:', settings.jwt_secret[:10] + '...')
"

# 重新生成JWT密钥
python -c "import secrets; print('新JWT密钥:', secrets.token_urlsafe(32))"
```

#### 4. API Key认证失败
```bash
# 验证API Key格式
curl -v -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"

# 检查API Key是否存在
python -c "
from terrakit.db.session import SessionLocal
from terrakit.db.models import APIKey
with SessionLocal() as db:
    keys = db.query(APIKey).all()
    for key in keys:
        print(f'API Key: {key.prefix}_{key.key_hash[:8]}..., 状态: {key.is_active}')
"
```

### 性能问题

#### 1. 响应缓慢
```bash
# 检查系统资源
top
htop  # 如果已安装

# 检查数据库性能
# SQLite: 使用EXPLAIN QUERY PLAN
# PostgreSQL: 使用EXPLAIN ANALYZE

# 启用调试模式查看详细日志
export TL_ENV=dev
uvicorn src.terrakit.main:app --reload --log-level debug
```

#### 2. 内存使用过高
```bash
# 监控内存使用
ps aux | grep uvicorn

# 减少worker数量
uvicorn src.terrakit.main:app --workers 1

# 使用内存分析工具
pip install memory-profiler
python -m memory_profiler your_script.py
```

### 日志和调试

#### 查看应用日志
```bash
# 实时查看日志
tail -f server.log

# 查看错误日志
grep -i error server.log
grep -i exception server.log

# 按时间查看日志
tail -n 100 server.log | grep "$(date '+%Y-%m-%d')"
```

#### 启用详细日志
```bash
# 在.env文件中添加
echo "TL_LOG_LEVEL=DEBUG" >> .env

# 或临时启用
export TL_LOG_LEVEL=DEBUG
uvicorn src.terrakit.main:app --reload
```

#### 数据库调试
```bash
# SQLite调试
sqlite3 terrakit_platform.db
.tables
.schema users
SELECT * FROM users LIMIT 5;
.quit

# PostgreSQL调试
psql -h localhost -U username -d terrakit_db
\dt
\d users
SELECT * FROM users LIMIT 5;
\q
```

### 获取帮助

如果以上方法都无法解决问题，请：

1. **收集信息**：
   - Python版本：`python --version`
   - 操作系统：`uname -a` (Linux/macOS) 或 `systeminfo` (Windows)
   - 错误日志：完整的错误堆栈信息
   - 配置文件：`.env`文件内容（隐藏敏感信息）

2. **检查文档**：
   - API文档：http://localhost:8000/docs
   - 项目文档：`docs/`目录

3. **社区支持**：
   - 提交Issue到项目仓库
   - 包含详细的错误信息和复现步骤

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