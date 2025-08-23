# Terralink Platform Architecture

## Project Structure

```
terralink_platform/
├── src/terralink_platform/
│   ├── core/                    # Core business logic
│   │   ├── __init__.py
│   │   ├── schemas.py          # API request/response models
│   │   └── services.py         # Business logic services
│   ├── db/                     # Database layer
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   └── session.py          # Database session management
│   ├── routers/                # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py             # Authentication endpoints
│   │   ├── deps.py             # Dependency injection
│   │   └── tools.py            # Tool management endpoints
│   ├── services/               # External service integrations
│   │   ├── __init__.py
│   │   └── auth_service.py     # Authentication service
│   ├── toolkits/               # Tool implementations
│   │   ├── __init__.py
│   │   ├── example.py
│   │   └── github.py
│   ├── config.py               # Application configuration
│   ├── data.py                 # Data access layer
│   ├── extensions.py           # Plugin system
│   ├── main.py                 # Application entry point
│   ├── models.py               # Core domain models (Pydantic)
│   ├── rate_limit.py           # Rate limiting
│   └── security.py             # Security utilities
└── tests/                      # Test suite
```

## Architecture Principles

### 1. Separation of Concerns

- **Core Layer** (`core/`): Contains business logic and API schemas
- **Database Layer** (`db/`): Handles data persistence and ORM models
- **API Layer** (`routers/`): HTTP request/response handling
- **Service Layer** (`services/`): External integrations and complex business logic
- **Domain Layer** (`models.py`): Core business entities and rules

### 2. API Versioning

The platform provides two distinct API interfaces:

#### SDK API (`/v1/sdk/*`)
- **Authentication**: API Key
- **Target Audience**: Programmatic access, SDKs
- **Features**: Full functionality with explicit context management

#### GUI API (`/v1/gui/*`)
- **Authentication**: JWT tokens
- **Target Audience**: Web applications, user interfaces
- **Features**: Simplified interface with automatic user context

#### Legacy API (`/v1/*`)
- **Authentication**: API Key
- **Purpose**: Backward compatibility
- **Status**: Maintained for existing integrations

### 3. Data Models

#### Core Domain Models (`models.py`)
- `User`: Platform users
- `Connection`: OAuth connection attempts
- `ConnectedAccount`: Third-party account connections
- `ToolSpec`: Tool specifications
- `ExecuteRequest/Response`: Tool execution contracts
- `Toolkit`: Tool groupings

#### API Schemas (`core/schemas.py`)
- `ToolSpecOut`: Tool specification API response
- `ToolkitOut`: Toolkit API response
- `ExecuteRequestIn/ResponseOut`: Tool execution API contracts
- `ConnectionStatusOut`: Connection status API response
- `ErrorResponse`: Standardized error responses

#### Database Models (`db/models.py`)
- SQLAlchemy ORM models for persistence
- Separate from domain models for flexibility

### 4. Business Logic (`core/services.py`)

#### ToolService
- `get_tools_with_status()`: Retrieve tools with availability calculation
- `get_tool_with_status()`: Get single tool with status
- `get_toolkits_with_status()`: Retrieve toolkits with tool statuses
- `execute_tool()`: Execute tools with proper authorization

### 5. Authentication & Authorization

#### API Key Authentication
- Used for SDK and legacy endpoints
- Stateless authentication
- Suitable for server-to-server communication

#### JWT Authentication
- Used for GUI endpoints
- Session-based authentication
- Suitable for web applications

#### Tool Authorization
- Tools can require connected accounts
- Automatic account selection for single connections
- Explicit account specification for multiple connections

### 6. Tool Execution Flow

1. **Request Validation**: Validate tool existence and user permissions
2. **Connection Check**: Verify required connections are available
3. **Account Selection**: Choose appropriate connected account
4. **Tool Execution**: Execute tool with proper context
5. **Response Formatting**: Return standardized response

### 7. Error Handling

- Standardized error responses across all endpoints
- Proper HTTP status codes
- Detailed error messages for debugging
- Trace IDs for request tracking

### 8. Extensibility

#### Plugin System
- Built-in toolkit loading
- Entry point plugin discovery
- Dynamic tool registration

#### Configuration
- Environment-based configuration
- Development vs. production settings
- Database connection management

## Development Guidelines

### Adding New Tools
1. Create tool implementation in `toolkits/`
2. Register tool in toolkit metadata
3. Add any required connection logic
4. Update API documentation

### Adding New Endpoints
1. Define request/response schemas in `core/schemas.py`
2. Implement business logic in `core/services.py`
3. Create route handlers in appropriate router
4. Add authentication and validation

### Database Changes
1. Update ORM models in `db/models.py`
2. Create Alembic migrations
3. Update corresponding domain models if needed
4. Test migration scripts

### Testing
- Unit tests for business logic
- Integration tests for API endpoints
- End-to-end tests for complete workflows
- Mock external dependencies

## Security Considerations

- API keys and JWT tokens are properly validated
- Connected account access is scoped to owning users
- Tool execution requires proper authorization
- Sensitive data is not logged or exposed
- Rate limiting prevents abuse
- Input validation prevents injection attacks