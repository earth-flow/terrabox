# Terrabox Platform

Terrabox Platform is a FastAPI-based backend service that provides API support for the Terrabox SDK. The platform offers core features such as user authentication, tool management, and API key management.

## Features

### 🔐 Authentication System
- **User Registration & Login**: Supports email/password registration with Argon2 hashing.
- **JWT Authentication**: Provides Bearer Token authentication for GUI applications.
- **API Key Authentication**: Provides API Key authentication for the SDK.
- **Password Policy**: Enforces minimum length and character set requirements.
- **Rate Limiting**: Prevents brute force attacks and abuse.

### 🔑 API Key Management
- **Create API Key**: Supports custom labels and prefixes.
- **List Keys**: View all user API Keys (masked).
- **Revoke Key**: Securely delete unused API Keys.
- **Limit**: Maximum of 5 API Keys per user.

### 🛠️ Tool System
- **Plugin Architecture**: Supports dynamic loading of tool plugins.
- **Built-in Toolkits**: Pre-installed common tools.
- **Extension Support**: Load third-party tools via entry points.

## Installation Guide

### System Requirements

- **Python**: 3.9 or higher
- **Operating System**: Linux, macOS, Windows
- **Database**: SQLite (Development) or PostgreSQL (Production)
- **Memory**: Minimum 512MB RAM
- **Disk Space**: Minimum 100MB free space

### Step 1: Get Source Code

```bash
# Method 1: Clone from Git repository (Recommended)
git clone <repository-url>
cd terrabox_platform

# Method 2: Download Source Archive
# Download and extract the source archive to a local directory
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install base dependencies
pip install -e .

# Install development dependencies (includes testing tools)
pip install -e ".[dev]"

# Verify installation
python -c "import terrabox; print('Installation successful!')"
```

### Step 4: Environment Configuration

1. **Copy Configuration Template**:
```bash
cp .env.example .env  # If the template file exists
# Or manually create .env file
```

2. **Edit Configuration File** `.env`:
```env
# ===================
# Database Configuration
# ===================
# Use SQLite for development
TL_DB_URL=sqlite:///./terrabox_platform.db
# Use PostgreSQL for production
# TL_DB_URL=postgresql://username:password@localhost:5432/terrabox_db

# ===================
# Security Configuration
# ===================
# JWT Secret (Must change in production)
TL_JWT_SECRET=your_super_secret_jwt_key_change_in_production
# API Key KDF Secret (Must change in production)
TL_APIKEY_KDF_SECRET=your_super_secret_apikey_kdf_change_in_production

# ===================
# Application Configuration
# ===================
# Environment setting: dev, staging, production
TL_ENV=dev

# ===================
# OAuth Configuration (Optional)
# ===================
# GitHub OAuth
GITHUB_OAUTH_CLIENT_ID=your_github_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_github_client_secret

# Google OAuth
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret
```

**🔒 Security Notice**:
- Must change all default secrets in production environment.
- Do not commit `.env` file to version control system.
- Use strong passwords and random keys.

### Step 5: Initialize Database

```bash
# Initialize database schema and test data
python scripts/init_db.py

# Verify database
python -c "from terrabox.db.session import engine; print('Database connection successful!')"
```

### Step 6: Start Service

```bash
# Development mode (Recommended, supports hot reload)
uvicorn terrabox.main:app --app-dir src --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn terrabox.main:app --app-dir src --host 0.0.0.0 --port 8000 --workers 4

# Background run
nohup uvicorn terrabox.main:app --app-dir src --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

### Step 7: Verify Installation

1. **Check Service Status**:
```bash
# Access health check endpoint
curl http://localhost:8000/
# Expected return: {"status":"ok"}
```

2. **Access API Documentation**:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

3. **Test User Registration**:
```bash
curl -X POST "http://localhost:8000/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test_'\"$(date +%s)\"'@example.com",
    "password": "TestPassword123!"
  }'
```

## User Guide

### Basic Usage Flow

1. **User Registration and Login**
2. **Create API Key**
3. **Use Tools and Services**
4. **Manage Connections and Configurations**

### User Authentication

#### Register New User
```bash
curl -X POST "http://localhost:8000/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

#### User Login
```bash
curl -X POST "http://localhost:8000/v1/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

### API Key Management

#### Create API Key
```bash
# Use JWT Token
curl -X POST "http://localhost:8000/v1/api-keys" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "My API Key",
    "prefix": "myapp"
  }'
```

#### Use API Key to Call Interface
```bash
curl -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Tool Usage

#### Get Available Tools List
```bash
curl -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"
```

#### Use Specific Tool
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

## API Documentation

After starting the service, access the following addresses to view API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Main API Endpoints

#### Authentication Related
- `POST /v1/register` - User Registration
- `POST /v1/login` - User Login (Returns JWT)

#### API Key Management
- `POST /v1/api-keys` - Create API Key
- `GET /v1/api-keys` - List API Keys
- `DELETE /v1/api-keys/{key_id}` - Revoke API Key

#### Tool Related
- `GET /v1/tools` - Get Available Tools List
- `POST /v1/tools/{tool_name}/use` - Use Specified Tool

### Connection Management

#### Create Connection
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

#### List Connections
```bash
curl -X GET "http://localhost:8000/v1/connections" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Python SDK Usage

#### Install Python Client
```bash
pip install terrabox-client  # If there is a standalone client package
# Or use requests directly
pip install requests
```

#### Python Code Example
```python
import requests
import json

class TerraboxClient:
    def __init__(self, base_url="http://localhost:8000", api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})
    
    def register(self, email, password):
        """Register new user"""
        response = self.session.post(
            f"{self.base_url}/v1/register",
            json={"email": email, "password": password}
        )
        return response.json()
    
    def login(self, email, password):
        """User login"""
        response = self.session.post(
            f"{self.base_url}/v1/login",
            json={"email": email, "password": password}
        )
        return response.json()
    
    def create_api_key(self, jwt_token, label, prefix=None):
        """Create API Key"""
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
        """Get tool list"""
        response = self.session.get(f"{self.base_url}/v1/sdk/tools")
        return response.json()
    
    def execute_tool(self, tool_slug, inputs, metadata=None):
        """Execute tool"""
        response = self.session.post(
            f"{self.base_url}/v1/sdk/tools/{tool_slug}/execute",
            json={"inputs": inputs, "metadata": metadata or {}}
        )
        return response.json()
    
    def list_toolkit_connections(self, toolkit):
        """Get connection list for specified toolkit"""
        response = self.session.get(
            f"{self.base_url}/v1/sdk/toolkits/{toolkit}/connections"
        )
        return response.json()
    
    def create_connection(self, toolkit, name, auth_method="oauth2"):
        """Create new connection"""
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
        """Get connection status"""
        response = self.session.get(
            f"{self.base_url}/v1/sdk/connections/{connection_id}"
        )
        return response.json()

# Usage Example
client = TerraboxClient()

# Register User
result = client.register("user@example.com", "SecurePassword123!")
print("Registration Result:", result)

# Login to get JWT
login_result = client.login("user@example.com", "SecurePassword123!")
jwt_token = login_result["access_token"]

# Create API Key
api_key_result = client.create_api_key(jwt_token, "My Python Client")
api_key = api_key_result["key"]

# Create new client using API Key
api_client = TerraboxClient(api_key=api_key)

# Get Tool List
tools = api_client.list_tools()
print("Available Tools:", tools)

# Execute GitHub Tool
github_result = api_client.execute_tool(
    "github-list-repos", 
    {"owner": "octocat"},
    {"connection_id": 1}  # If specific connection is needed
)
print("GitHub Repos:", github_result)

# Get Connection List for GitHub Toolkit
github_connections = api_client.list_toolkit_connections("github")
print("GitHub Connections:", github_connections)

# Create New GitHub Connection
new_connection = api_client.create_connection(
    "github", 
    "My GitHub Connection"
)
print("New Connection:", new_connection)

# Check Connection Status
if "id" in new_connection:
    status = api_client.get_connection_status(new_connection["id"])
    print("Connection Status:", status)
```

## Development Guide

### Adding New Tools

1. Create new tool module under `src/terrabox/toolkits/`
2. Implement tool interface
3. Register tool in `extensions.py`

### Database Migration

```bash
# Generate migration file
alembic revision --autogenerate -m "Describe changes"

# Apply migration
alembic upgrade head
```

## Security Considerations

- 🔒 Passwords use Argon2 hashing for high security.
- 🔑 API Keys are stored using HMAC-SHA256 encryption.
- 🚦 Built-in rate limiting prevents abuse.
- 📝 Sensitive information is automatically masked in logs.
- 🛡️ JWT Tokens have expiration time limits.

## Deployment

### Docker Deployment

```dockerfile
# Dockerfile Example
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "terrabox.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Environment Configuration

1. Use PostgreSQL database.
2. Configure Redis for caching and sessions.
3. Set up reverse proxy (Nginx).
4. Enable HTTPS.
5. Configure log collection.

## Troubleshooting

### Installation Issues

#### 1. Python Version Incompatible
```bash
# Check Python version
python --version
# Should be 3.9 or higher

# If version is too low, install new version
# Ubuntu/Debian:
sudo apt update && sudo apt install python3.9
# macOS (using Homebrew):
brew install python@3.9
# Windows: Download from official website
```

#### 2. Dependency Installation Failed
```bash
# Upgrade pip
pip install --upgrade pip

# Clear cache and reinstall
pip cache purge
pip install -e . --no-cache-dir

# If compilation errors occur, install build tools
# Ubuntu/Debian:
sudo apt install build-essential python3-dev
# CentOS/RHEL:
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel
```

#### 3. Virtual Environment Issues
```bash
# Delete old virtual environment
rm -rf venv

# Recreate
python -m venv venv
source venv/bin/activate  # Linux/macOS
# Or
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -e .
```

### Runtime Issues

#### 1. Database Connection Failed
```bash
# Check database file permissions (SQLite)
ls -la terrabox_platform.db
chmod 664 terrabox_platform.db  # If permissions are insufficient

# Test database connection
python -c "
from terrabox.db.session import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('Database connection successful!')
"

# PostgreSQL connection test
psql -h localhost -U username -d terrabox_db -c "SELECT 1;"
```

#### 2. Port Occupied
```bash
# Check port usage
netstat -tlnp | grep :8000
# Or
lsof -i :8000

# Kill occupying process
kill -9 <PID>

# Start with another port
uvicorn terrabox.main:app --app-dir src --port 8001
```

#### 3. JWT Token Issues
```bash
# Check JWT configuration
python -c "
from terrabox.core.utils.config import get_settings
settings = get_settings()
print('JWT Secret Length:', len(settings.jwt_secret))
print('JWT Secret:', settings.jwt_secret[:10] + '...')
"

# Regenerate JWT Secret
python -c "import secrets; print('New JWT Secret:', secrets.token_urlsafe(32))"
```

#### 4. API Key Authentication Failed
```bash
# Verify API Key format
curl -v -X GET "http://localhost:8000/v1/tools" \
  -H "X-API-Key: YOUR_API_KEY"

# Check if API Key exists
python -c "
from terrabox.db.session import SessionLocal
from terrabox.db.models import APIKey
with SessionLocal() as db:
    keys = db.query(APIKey).all()
    for key in keys:
        print(f'API Key: {key.prefix}_{key.key_hash[:8]}..., Status: {key.is_active}')
"
```

### Performance Issues

#### 1. Slow Response
```bash
# Check system resources
top
htop  # If installed

# Check database performance
# SQLite: Use EXPLAIN QUERY PLAN
# PostgreSQL: Use EXPLAIN ANALYZE

# Enable debug mode to view detailed logs
export TL_ENV=dev
uvicorn terrabox.main:app --app-dir src --reload --log-level debug
```

#### 2. High Memory Usage
```bash
# Monitor memory usage
ps aux | grep uvicorn

# Reduce worker count
uvicorn terrabox.main:app --app-dir src --workers 1

# Use memory profiler tool
pip install memory-profiler
python -m memory_profiler your_script.py
```

### Logs and Debugging

#### View Application Logs
```bash
# View logs in real-time
tail -f server.log

# View error logs
grep -i error server.log
grep -i exception server.log

# View logs by time
tail -n 100 server.log | grep "$(date '+%Y-%m-%d')"
```

#### Enable Detailed Logs
```bash
# Add to .env file
echo "TL_LOG_LEVEL=DEBUG" >> .env

# Or enable temporarily
export TL_LOG_LEVEL=DEBUG
uvicorn terrabox.main:app --app-dir src --reload
```

#### Database Debugging
```bash
# SQLite debugging
sqlite3 terrabox_platform.db
.tables
.schema users
SELECT * FROM users LIMIT 5;
.quit

# PostgreSQL debugging
psql -h localhost -U username -d terrabox_db
\dt
\d users
SELECT * FROM users LIMIT 5;
\q
```

### Get Help

If the above methods cannot solve the problem, please:

1. **Collect Information**:
   - Python Version: `python --version`
   - Operating System: `uname -a` (Linux/macOS) or `systeminfo` (Windows)
   - Error Logs: Complete error stack trace
   - Configuration File: `.env` file content (hide sensitive information)

2. **Check Documentation**:
   - API Documentation: http://localhost:8000/docs
   - Project Documentation: `docs/` directory

3. **Community Support**:
   - Submit Issue to project repository
   - Include detailed error information and reproduction steps

## Contribution Guide

1. Fork the project
2. Create feature branch
3. Submit changes
4. Create Pull Request

## License

This project is licensed under the MIT License. See LICENSE file for details.
