# Test Suite

Comprehensive test suite for the Open Agent Investigation platform.

**Quick Start:**
```shell
docker compose -f docker-compose.test.yml run --rm test-runner pytest tests/unit/ -v --tb=short
```

## Overview

The test suite uses a three-tier strategy:

1. **Unit Tests** (~770 tests) - Fast, isolated tests for individual functions
2. **Integration Tests** (~956 tests) - Database and API endpoint tests
3. **End-to-End Tests** (planned) - Full workflow tests

**Current Status:** 1726 tests, 71.96% coverage (targeting 80%)

## Structure

```
tests/
├── conftest.py                  # Global fixtures and configuration
├── pytest.ini                   # Pytest configuration
├── requirements-test.txt        # Full test dependencies
├── factories.py                 # Data factories for test data generation
├── README.md                    # This file
│
├── unit/                        # Unit tests (~783 tests, no database)
│   ├── auth/                    # Authentication module tests
│   │   ├── test_auth_module.py  # JWT token creation/verification
│   │   └── test_password_hashing.py  # Argon2 password hashing
│   ├── core/
│   │   ├── test_config.py       # Settings and environment variables
│   │   ├── test_security.py     # Security utilities
│   │   └── test_deps.py         # Dependency injection
│   ├── models/                  # SQLAlchemy model tests (15 files)
│   │   ├── test_user.py         # User model
│   │   ├── test_investigation.py  # Investigation model
│   │   ├── test_artifact.py     # Artifact model
│   │   ├── test_chat_history.py # ChatMessage model
│   │   ├── test_tool_execution.py  # ToolExecution model
│   │   ├── test_llm_config.py   # LLMProviderConfig model
│   │   ├── test_mcp_server.py   # MCPServer model
│   │   ├── test_embedding.py    # Embedding model (45 tests)
│   │   ├── test_filter_config.py # FilterConfig model (40 tests)
│   │   ├── test_investigation_choice.py # InvestigationChoice model (65 tests)
│   │   ├── test_investigation_note.py # InvestigationNote model (50 tests)
│   │   ├── test_job_agent.py    # AgentJob model (65 tests)
│   │   ├── test_job_parsing.py  # ParsingJob model (60 tests)
│   │   ├── test_report.py       # Report model (70 tests)
│   │   └── test_tool_result.py  # ToolResult model (50 tests)
│   ├── schemas/                 # Pydantic schema validation tests (9 files)
│   │   ├── test_investigation.py  # Investigation schemas
│   │   ├── test_user_schema.py  # User schemas
│   │   ├── test_artifact_schema.py  # Artifact schemas
│   │   ├── test_llm_config_schema.py  # LLM config schemas
│   │   ├── test_mcp_server_schema.py  # MCP server schemas
│   │   ├── test_chat_message_schema.py # Chat message schemas (130 tests)
│   │   ├── test_event_schema.py # Event schemas (70 tests)
│   │   ├── test_job_schema.py   # Job schemas (70 tests)
│   │   └── test_timeline_schema.py # Timeline schemas (120 tests)
│   ├── crud/                    # CRUD operation tests (mocked, 10 files)
│   │   ├── test_user.py         # User CRUD operations
│   │   ├── test_artifact.py     # Artifact CRUD (45 tests)
│   │   ├── test_chat_history.py # Chat history CRUD (175 tests)
│   │   ├── test_investigation.py # Investigation CRUD (43 tests)
│   │   ├── test_investigation_choice.py # Investigation choice CRUD (50 tests)
│   │   ├── test_job.py          # Job CRUD (100 tests)
│   │   ├── test_llm_config.py   # LLM config CRUD (45 tests)
│   │   ├── test_mcp_server.py   # MCP server CRUD (50 tests)
│   │   ├── test_report.py       # Report CRUD (37 tests)
│   │   └── test_tool_execution.py # Tool execution CRUD (55 tests)
│   ├── routers/                 # Router unit tests (1 file)
│   │   └── test_events.py       # Events router (53 tests)
│   ├── services/                # Service layer tests (11 files)
│   │   ├── test_chat_router.py  # Chat routing logic
│   │   ├── test_websocket_manager.py  # WebSocket connections
│   │   ├── test_chat_persistence.py  # Message persistence
│   │   ├── test_llm_auth_helper.py  # LLM authentication
│   │   ├── test_context_manager.py  # Context management
│   │   ├── test_query_expander.py  # Query expansion
│   │   ├── test_llm_context.py  # LLM context building (110 tests)
│   │   ├── handlers/
│   │   │   └── test_general_chat_handler.py  # General chat handler
│   │   └── rag/
│   │       ├── test_embedding.py  # Embedding service
│   │       └── test_filter_engine.py  # Event filtering
│   ├── utils/                   # Utility function tests
│   │   └── test_content_sanitizer.py  # Content sanitization
│   └── core/                    # Core module tests
│       └── test_database.py     # Database configuration (15 tests)
│
├── integration/                 # Integration tests (~200 tests, with database)
│   └── routers/
│       ├── test_auth.py         # Authentication endpoints (19 tests)
│       ├── test_investigations.py  # Investigation CRUD (21 tests)
│       ├── test_artifacts.py    # Artifact upload/download (12 tests)
│       ├── test_jobs.py         # Job status and management (13 tests)
│       ├── test_llm_config.py   # LLM configuration (19 tests)
│       ├── test_chat_messages.py  # Chat messages CRUD (24 tests)
│       ├── test_mcp.py          # MCP servers (19 tests)
│       ├── test_investigation_choices.py  # Agent choices (8 tests)
│       ├── test_embeddings.py   # Embedding generation (4 tests)
│       ├── test_audit.py        # Audit logs (9 tests)
│       ├── test_agents.py       # Agent execution (13 tests)
│       └── test_reports.py      # Report generation (8 tests)
│
├── e2e/                         # End-to-end tests (planned)
│   └── (future workflow tests)
│
└── mock_services/               # Mock external services
    ├── mock_llm.py              # Mock LLM API server
    └── Dockerfile.mock-llm      # Docker image for mock LLM
```

## Running Tests

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 15 (via Docker)

### Quick Start

**On Linux/macOS:**
```bash
# Run all tests
./run-tests.sh all

# Run only unit tests
./run-tests.sh unit

# Run only integration tests
./run-tests.sh integration

# Run only e2e tests
./run-tests.sh e2e
```

**On Windows (PowerShell):**
```powershell
# Run all tests
.\run-tests.ps1 all

# Run only unit tests
.\run-tests.ps1 unit

# Run only integration tests
.\run-tests.ps1 integration

# Run only e2e tests
.\run-tests.ps1 e2e
```

### Manual Execution

**Without Docker:**
```bash
cd api

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements-test.txt

# Set environment variables
export TEST_DATABASE_URL="postgresql+asyncpg://postgres:testpass@localhost:5432/open_agent_inv_test"
export JWT_SECRET="test-secret-key"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/core/test_security.py -v

# Run tests by marker
pytest tests/ -v -m unit
pytest tests/ -v -m integration
```

**With Docker:**
```bash
# Build and run test container
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# Run specific test type
docker compose -f docker-compose.test.yml run --rm test-runner \
    pytest tests/ -v -m unit

# Cleanup
docker compose -f docker-compose.test.yml down -v
```

## Coverage

**Current Coverage**: 71.93% (1745 tests)
**Target**: 80% line coverage

The test suite aims for:
- **80%+ line coverage** for API code
- **70%+ line coverage** for worker code
- **100% coverage** for critical security functions

### High Coverage Modules (>70%)
- `app/models/*` - 95-100% (all models fully tested)
- `app/schemas/*` - 90-100% (comprehensive validation tests)
- `app/crud/*` - 99-100% (all CRUD operations tested)
- `app/core/*` - 67-100% (core functionality tested)
- `app/services/context_manager.py` - 97%
- `app/services/rag/embedding_service.py` - 95%
- `app/services/rag/retriever.py` - 95%
- `app/services/chat_router.py` - 95%
- `app/services/handlers/rag_handler.py` - 92%
- `app/services/rag/filter_engine.py` - 90%
- `app/services/query_expander.py` - 87%
- `app/services/handlers/general_chat_handler.py` - 85%
- `app/services/report_generator.py` - 83%
- `app/routers/tags.py` - 100% (deprecated endpoints)
- `app/services/chat_broadcast.py` - 77%
- `app/services/policy_router.py` - 75%
- `app/services/rag/event_processor.py` - 75%
- `app/services/handlers/event_handler.py` - 71%
- `app/auth.py` - 100%
- `app/deps.py` - 100%
- `app/utils/content_sanitizer.py` - 100%
- `app/services/chat_persistence.py` - 100%
- `app/services/llm_auth_helper.py` - 100%
- `app/services/llm_context.py` - 100%
- `app/services/websocket_manager.py` - 100%
- `app/services/rag/embedding.py` - 100%

### Recently Improved Coverage
- `app/routers/events.py` - **10% → 92%** (+82%) - Added 53 unit tests for JSONB queries, filtering, and paste functionality

### Modules Needing Coverage (<50%)
- `app/routers/events.py` - **92%** (223 statements) ✅ - Complex JSONB queries and paste functionality
- `app/routers/chat.py` - 13% (266 statements) - WebSocket handlers
- `app/routers/timeline.py` - 13% (266 statements) - Advanced filtering and notes
- `app/routers/agents.py` - 20% (84 statements) - Agent execution flows
- `app/routers/jobs.py` - 22% (89 statements) - Job management
- `app/routers/embeddings.py` - 30% (46 statements) - Embedding generation
- `app/routers/artifacts.py` - 34% (65 statements) - File upload/download
- `app/routers/audit.py` - 35% (31 statements) - Audit log filtering
- `app/routers/reports.py` - 43% (127 statements) - Report generation
- `app/routers/llm_config.py` - 44% (54 statements) - LLM configuration
- `app/routers/mcp.py` - 45% (42 statements) - MCP server management
- `app/services/llm_service.py` - 50% (273 statements) - HTTP integration
- `app/routers/chat_messages.py` - 58% (142 statements) - Message CRUD
- `app/services/handlers/timeline_handler.py` - 61% (279 statements) - Timeline operations

View coverage report:
```bash
# Generate HTML coverage report
pytest tests/ --cov=app --cov-report=html

# Open in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Test Markers

Tests are organized using pytest markers:

| Marker | Description | Count | Example |
|--------|-------------|-------|---------|
| `unit` | Unit tests (no external dependencies) | ~770 | `@pytest.mark.unit` |
| `integration` | Integration tests (require database) | ~956 | `@pytest.mark.integration` |

| `e2e` | End-to-end tests (full stack) | 0 | `@pytest.mark.e2e` |
| `slow` | Tests that take > 1 second | 0 | `@pytest.mark.slow` |

Run tests by marker:
```bash
pytest tests/ -v -m unit           # Only unit tests
pytest tests/ -v -m integration    # Only integration tests
pytest tests/ -v -m "not slow"     # Exclude slow tests
```

## Factories

Data factories are provided for generating test data:

```python
from tests.factories import (
    UserFactory,
    AdminUserFactory,
    InvestigationFactory,
    SecurityEventFactory,
    TimelineEntryFactory,
)

# Create test user
user = UserFactory.build(username="testuser")

# Create investigation with events
investigation = InvestigationFactory.build(owner_user_id=user.user_id)
event = SecurityEventFactory.build(investigation_id=investigation.investigation_id)

# Create timeline entry
entry = TimelineEntryFactory.build(
    investigation_id=investigation.investigation_id,
    event_id=event.event_id
)
```

## Fixtures

Common fixtures available in `conftest.py`:

### Database Fixtures
- `test_engine` - Test database engine (session-scoped)
- `db_session` - Database session with transaction rollback (function-scoped)
- `override_get_db` - Override FastAPI dependency

### Client Fixtures
- `client` - Synchronous TestClient for FastAPI
- `async_client` - Async HTTP client for WebSocket tests

### Authentication Fixtures
- `test_user` - Regular user account
- `admin_user` - Admin user account
- `test_token` - JWT token for test user
- `admin_token` - JWT token for admin user
- `auth_headers` - Authorization headers with test token
- `admin_headers` - Authorization headers with admin token

### Investigation Fixtures
- `test_investigation` - Sample investigation

### Mock Service Fixtures
- `mock_llm_client` - Mock LLM client with deterministic responses
- `mock_intent_classifier` - Pre-configured LLM for intent classification
- `mock_embedding_service` - Deterministic embedding generation
- `deterministic_uuid` - Sequential UUID generator

## Test Principles

1. **Avoid Over-Mocking** - Integration tests use real database sessions, not mocks
2. **Function-Scoped Fixtures** - Each test gets a fresh database to avoid state leakage
3. **Test Isolation** - No shared state between tests
4. **Real Workflows** - Integration tests exercise actual code paths
5. **Docker Testing** - Always use Docker containers for consistency
6. **Coverage Quality** - Focus on meaningful tests that verify business logic

## Writing Tests

### Unit Test Example

```python
import pytest

@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing utilities."""
    
    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        from app.auth import hash_password
        
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password
```

### Integration Test Example

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
class TestLogin:
    """Test login endpoint."""
    
    async def test_login_success(
        self,
        async_client: AsyncClient,
        test_user
    ):
        """Test successful login."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
```

### E2E Test Example

```python
import pytest
from httpx import AsyncClient

@pytest.mark.e2e
@pytest.mark.slow
class TestFullWorkflow:
    """Test complete investigation workflow."""
    
    async def test_create_investigation_and_analyze(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """Test creating investigation, uploading artifact, and running analysis."""
        # Create investigation
        response = await async_client.post(
            "/api/v1/investigations/",
            headers=auth_headers,
            json={"title": "E2E Test Investigation"}
        )
        assert response.status_code == 201
        inv_id = response.json()["investigation_id"]
        
        # Upload artifact
        # ... (artifact upload logic)
        
        # Run agent analysis
        # ... (agent execution logic)
        
        # Verify timeline populated
        # ... (timeline verification)
```

## Debugging Tests

### Enable SQL Logging

```python
# In conftest.py, set echo=True
engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=True,  # Log all SQL queries
)
```

### Run Single Test with Verbose Output

```bash
pytest tests/unit/core/test_security.py::TestPasswordHashing::test_hash_password_returns_string -vv
```

### Drop into Debugger on Failure

```bash
pytest tests/ --pdb
```

### Print Statements

```python
def test_something():
    result = my_function()
    print(f"Result: {result}")  # Will show in pytest output with -s
    assert result == expected
```

Run with `-s` to see print output:
```bash
pytest tests/ -v -s
```

## Continuous Integration

Tests run automatically on:
- Every push to `main` or `develop` branches
- Every pull request

GitHub Actions workflow (`.github/workflows/tests.yml`):
1. **Unit Tests** - Run without database
2. **Integration Tests** - Run with PostgreSQL service
3. **Docker Tests** - Full stack in Docker
4. **Code Quality** - Linting, formatting, type checking

## Performance

Test execution times (approximate):
- **Unit tests**: ~20 seconds (~770 tests)
- **Integration tests**: ~60 seconds (~956 tests)
- **E2E tests**: ~2 minutes (planned)
- **Full suite**: ~82 seconds (1726 tests total)

## Contributing

When adding features:

1. **Write tests first** (TDD approach)
2. **Maintain coverage** (aim for 80%+)
3. **Use appropriate markers** (`@pytest.mark.unit`, etc.)
4. **Follow naming conventions** (`test_*` for functions, `Test*` for classes)
5. **Document complex tests** (docstrings explaining what/why)

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Async Testing](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Factory Boy](https://factoryboy.readthedocs.io/)

## Troubleshooting

### Database Connection Errors

**Issue**: `connection refused` errors

**Solution**:
```bash
# Ensure PostgreSQL is running
docker compose -f docker-compose.test.yml up test-db

# Check connection
psql -h localhost -p 5433 -U postgres -d open_agent_inv_test
```

### Import Errors

**Issue**: `ModuleNotFoundError`

**Solution**:
```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/api:$PYTHONPATH

# Or install in editable mode
pip install -e .
```

### Fixture Not Found

**Issue**: `fixture 'test_user' not found`

**Solution**: Ensure `conftest.py` is in the correct location and imported properly.

### Tests Hanging

**Issue**: Tests hang indefinitely

**Solution**: Use `pytest-timeout`:
```bash
pytest tests/ --timeout=30  # Kill tests after 30 seconds
```

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../../README.md).
