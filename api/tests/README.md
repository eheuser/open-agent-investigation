# Test Suite

Comprehensive test suite for the Open Agent Investigation platform.

**Quick Start:**
```shell
docker compose -f docker-compose.test.yml run --rm test-runner pytest tests/unit/ -v --tb=short
```

## Overview

The test suite uses a three-tier strategy:

1. **Unit Tests** (~800 tests) - Fast, isolated tests for individual functions
2. **Integration Tests** (~1000 tests) - Database and API endpoint tests
3. **End-to-End Tests** (planned) - Full workflow tests

**Current Status:** 1919 tests, 70.50% coverage (targeting 80%)

## Structure

```
tests/
├── conftest.py                  # Global fixtures and configuration
├── pytest.ini                   # Pytest configuration
├── requirements-test.txt        # Full test dependencies
├── factories.py                 # Data factories for test data generation
├── README.md                    # This file
│
├── unit/                        # Unit tests (~900 tests, no database)
│   ├── analysis/                # Analysis module tests
│   │   ├── test_execution_evidence.py  # Execution evidence analyzer (40 tests)
│   │   └── test_user_activity.py       # User activity analyzer (82 tests)
│   ├── auth/                    # Authentication module tests
│   │   ├── test_auth_module.py  # JWT token creation/verification
│   │   └── test_password_hashing.py  # Argon2 password hashing
│   ├── parsers/                 # Parser utility tests
│   │   └── test_utils.py        # Parser sanitization and encoding (15 tests)
│   ├── tools/                   # Tool tests
│   │   └── test_analysis_tools.py  # Analysis tools (5 tests)
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
│   ├── services/                # Service layer tests (14 files)
│   │   ├── test_chat_router.py  # Chat routing logic
│   │   ├── test_websocket_manager.py  # WebSocket connections
│   │   ├── test_chat_persistence.py  # Message persistence
│   │   ├── test_llm_auth_helper.py  # LLM authentication
│   │   ├── test_context_manager.py  # Context management
│   │   ├── test_query_expander.py  # Query expansion
│   │   ├── test_llm_context.py  # LLM context building (110 tests)
│   │   ├── test_embedding_batcher.py  # Embedding batcher service (35 tests)
│   │   ├── test_embedding_pool.py  # Embedding pool service (21 tests)
│   │   ├── test_embedding_queue.py  # Embedding queue service (12 tests)
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

**Current Coverage**: 70.50% (1919 tests)
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
- `app/services/rag/retriever.py` - 72% (hybrid BM25 + vector search - 47 missing statements in new methods)
- `app/services/chat_router.py` - 95%
- `app/services/handlers/rag_handler.py` - 91% (enhanced query expansion + hybrid BM25 search)
- `app/services/rag/filter_engine.py` - 90%
- `app/services/query_expander.py` - 87%
- `app/services/handlers/general_chat_handler.py` - 85%
- `app/services/report_generator.py` - 83%
- `app/routers/tags.py` - 100% (deprecated endpoints)
- `app/services/chat_broadcast.py` - 69%
- `app/services/policy_router.py` - 75%
- `app/services/rag/event_processor.py` - 73%
- `app/services/rag/retriever.py` - 71%
- `app/services/handlers/event_handler.py` - 71%
- `app/services/embedding_pool.py` - 68% (new comprehensive tests added)
- `app/services/embedding_batcher.py` - 54% (new comprehensive tests added)
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

### Recent RAG System Enhancements

**Query Expansion (Dec 2024)**:
- Changed from simple keyword lists to diverse search queries
- Now generates 5-7 varied approaches: full questions, keyword phrases, artifact-specific queries, attack techniques, and tool signatures
- Parser updated to handle newline-separated queries instead of comma-separated terms
- Tests: `api/tests/unit/services/handlers/test_rag_handler.py::TestExpandQueryWithLLM`

**Hybrid BM25 + Vector Search (Dec 2024)**:
- BM25 full-text search is now **mandatory** in RAG pipeline (previously optional)
- All retrieval queries use hybrid search with configurable weights (default: 30% BM25, 70% vector)
- New methods: `Retriever._hybrid_retrieve()`, `Retriever._bm25_search()`
- Fetches 3x desired results from each method, merges, normalizes scores, and returns top-k
- Tests: `api/tests/unit/services/rag/test_retriever.py` (existing tests cover vector search, new tests needed for hybrid methods)

**Reranker Context (Dec 2024)**:
- Reranker already receives user query for context-aware scoring
- Uses separate reranker model (if configured) for improved relevance
- Computes cosine similarity between query embedding and document embeddings
- Tests: `api/tests/unit/services/test_embedding_service.py` (reranker tests)

### Modules Needing Coverage (<70%)
- `app/routers/timeline.py` - 11% (352 statements) - Advanced filtering and notes
- `app/routers/chat.py` - 12% (269 statements) - WebSocket handlers
- `app/routers/agents.py` - 20% (84 statements) - Agent execution flows
- `app/routers/analysis.py` - 22% (193 statements) - Analysis modules API
- `app/routers/jobs.py` - 22% (89 statements) - Job management
- `app/routers/embeddings.py` - 31% (61 statements) - Embedding generation
- `app/routers/logs.py` - 35% (49 statements) - Log streaming
- `app/routers/audit.py` - 35% (31 statements) - Audit log filtering
- `app/routers/artifacts.py` - 36% (61 statements) - File upload/download
- `app/routers/llm_config.py` - 40% (132 statements) - LLM configuration
- `app/routers/reports.py` - 41% (133 statements) - Report generation
- `app/routers/playbooks.py` - 46% (142 statements) - Playbook management
- `app/routers/investigations.py` - 48% (44 statements) - Investigation CRUD
- `app/routers/investigation_choices.py` - 52% (40 statements) - Agent choices
- `app/routers/mcp.py` - 57% (42 statements) - MCP server management
- `app/analysis/execution_evidence.py` - 61% (226 statements) - Execution artifact analysis
- `app/analysis/user_activity.py` - 66% (222 statements) - User activity artifacts (ShellBags, RecentDocs, etc.)
- `app/routers/chat_messages.py` - 59% (144 statements) - Message CRUD
- `app/services/handlers/timeline_handler.py` - 60% (292 statements) - Timeline operations
- `app/services/chat_broadcast.py` - 69% (479 statements) - WebSocket broadcasting

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
| `unit` | Unit tests (no external dependencies) | ~800 | `@pytest.mark.unit` |
| `integration` | Integration tests (require database) | ~1000 | `@pytest.mark.integration` |

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
- **Unit tests**: ~35 seconds (~835 tests)
- **Integration tests**: ~96 seconds (~1002 tests)
- **E2E tests**: ~2 minutes (planned)
- **Full suite**: ~131 seconds (1837 tests total)

## Test Coverage for Recent Changes

### RAG Enhancements - Test Status

**Summary**: Recent RAG improvements added 165 new statements across 2 files. Current coverage:
- `rag_handler.py`: 91% (19/215 missing) - Query expansion working, minor edge cases untested
- `retriever.py`: 72% (47/165 missing) - New hybrid search methods need comprehensive tests
- **Overall Impact**: +76 tests added, coverage maintained at 71.32%

**Action Items**: Add ~10 unit tests for hybrid search methods to restore retriever coverage to 90%+

---

The following tests should be added to cover the recent RAG enhancements:

**Query Expansion Tests** (`api/tests/unit/services/handlers/test_rag_handler.py`):
- ✅ Existing: `test_expand_query_success` - Validates LLM call and newline-separated parsing
- ✅ Existing: `test_expand_query_limits_to_7_terms` - Ensures max 7 queries returned
- ✅ Existing: `test_expand_query_strips_whitespace` - Tests cleanup logic
- ✅ **UPDATED**: All tests now use newline-separated mock responses
- 🔲 **NEW NEEDED** (19 missing statements): 
  - Test regex cleanup of numbered prefixes (`1.`, `2)`, etc.) - line 286, 288, 290, 292
  - Test regex cleanup of bullet prefixes (`- `, `* `, `•`) 
  - Test diverse query types in prompt (questions, keywords, artifact-specific)
  - Test empty lines are filtered out

**Coverage**: RAG handler is at 91% (215 statements, 19 missing). Most missing lines are in error handling paths and edge cases.

**Hybrid Search Tests** (`api/tests/unit/services/rag/test_retriever.py`):
- ✅ Existing: `test_vector_search_success` - Tests pure vector search
- ✅ Existing: `test_retrieve_with_candidates` - Tests retrieval with text loading
- 🔲 **NEW NEEDED** (47 missing statements): 
  - `test_hybrid_retrieve_combines_bm25_and_vector` - Test score fusion (lines 130-185)
  - `test_hybrid_retrieve_normalizes_scores` - Test normalization to [0,1]
  - `test_hybrid_retrieve_respects_weights` - Test configurable BM25/vector weights
  - `test_bm25_search_success` - Test BM25 full-text search (lines 206-273)
  - `test_bm25_search_with_owner_types` - Test owner type filtering
  - `test_bm25_search_handles_special_chars` - Test query sanitization
  - `test_bm25_search_handles_errors` - Test exception handling
  - `test_retrieve_uses_hybrid_when_query_text_provided` - Test automatic hybrid mode (line 81)
  - `test_retrieve_falls_back_to_vector_only` - Test fallback when query_text=None

**Coverage Impact**: The new hybrid search methods (`_hybrid_retrieve` and `_bm25_search`) added 165 statements, but only 118 are covered, dropping retriever coverage from 95% to 72%. Adding the tests above will restore coverage to ~90%.

**Integration Tests** (`api/tests/integration/routers/test_embeddings.py`):
- 🔲 **NEW NEEDED**: Test RAG query with hybrid search enabled
- 🔲 **NEW NEEDED**: Test BM25 results include keyword matches
- 🔲 **NEW NEEDED**: Test vector results include semantic matches
- 🔲 **NEW NEEDED**: Test combined results outperform single-method retrieval

## Contributing

When adding features:

1. **Write tests first** (TDD approach)
2. **Maintain coverage** (aim for 80%+)
3. **Use appropriate markers** (`@pytest.mark.unit`, etc.)
4. **Follow naming conventions** (`test_*` for functions, `Test*` for classes)
5. **Document complex tests** (docstrings explaining what/why)
6. **Update this README** when adding new features or test coverage

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Async Testing](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Factory Boy](https://factoryboy.readthedocs.io/)

## Recent Test Additions

### User Activity Analysis Test Coverage (Mar 2026)

**Added 82 new tests** for the user activity analyzer:

**User Activity Analyzer Tests** (`test_user_activity.py` - 82 tests):
- Analyzer initialization and configuration (2 tests)
- Category metadata validation (4 tests)
- Activity description extraction for all 7 categories (10 tests)
- User context extraction from various sources (3 tests)
- Additional data extraction per category (4 tests)
- Entry creation and validation (3 tests)
- Analysis workflow with caching (3 tests)
- Error handling and edge cases (3 tests)
- Data model serialization (3 tests)

**Categories Tested**:
- ShellBags - Windows Explorer folder browsing history
- RecentDocs - Recently opened documents
- OpenSaveMRU - Open/Save dialog history
- LastVisitedMRU - Application file access locations
- TypedPaths - Manually typed paths in Explorer
- RunMRU - Run dialog command history
- WordWheelQuery - Windows Search queries

**Coverage Impact**:
- `user_activity.py`: 15% → 66% (+51%)
- **Overall**: Added 82 tests, improved overall coverage from 69.23% to 70.50%

### Execution Evidence Analysis Test Updates (Mar 2026)

**Updated tests** to match new execution evidence categories:
- Expanded from 4 to 8 categories (added ShimCache, AmCache, UserAssist, PCA, BAM/DAM)
- Updated all test assertions to reflect new category count
- Fixed payload field extraction tests to match actual parser output
- Updated additional data extraction tests for new field structures

**Coverage Impact**:
- `execution_evidence.py`: 59% → 61% (+2%)
- Tests now accurately reflect production parser behavior

### Parser Utils Encoding Tests (Mar 2026)

**Updated tests** for new `sanitize_for_jsonb()` behavior:
- Updated byte handling tests to reflect UTF-8 decode-first approach
- Added tests for valid UTF-8 bytes vs invalid bytes
- Added tests for null byte removal after decoding
- Tests now validate proper encoding safety for PostgreSQL JSONB

**Coverage Impact**:
- All parser utils tests passing with new encoding logic
- Validates critical JSONB compatibility fixes

### Embedding System Test Coverage (Feb 2026)

**Added 68 new tests** for the embedding batcher and pool services:

**Embedding Batcher Tests** (`test_embedding_batcher.py` - 35 tests):
- Queue initialization and event queueing (8 tests)
- Queue size tracking (3 tests)
- Batcher process lifecycle management (4 tests)
- Configuration constants validation (2 tests)
- Integration tests for queue operations (3 tests)
- Edge cases and error handling (6 tests)
- Process function behavior (2 tests)
- Concurrent access patterns (7 tests)

**Embedding Pool Tests** (`test_embedding_pool.py` - 21 tests):
- Event pooling without auto-flush (3 tests)
- Manual pool flushing (2 tests)
- Investigation-specific flushing (3 tests)
- Deterministic batching behavior (3 tests)
- Pool statistics tracking (2 tests)
- Configuration constants (1 test)
- Edge cases and error handling (7 tests)

**Embedding Queue Tests** (`test_embedding_queue.py` - 12 tests):
- Event queueing with adaptive batching (5 tests)
- Embedding status tracking (6 tests)
- Configuration constants (1 test)

**Coverage Impact**:
- `embedding_batcher.py`: 21% → 54% (+33%)
- `embedding_pool.py`: 54% → 68% (+14%)
- `embedding_queue.py`: Maintained at 100%
- **Overall**: Added 68 tests, improved embedding system coverage significantly

### Embedding Count Consistency (Feb 2026)

**Issue**: Uploading the same artifact bundle to multiple investigations resulted in different embedding counts (e.g., 7,220 vs 7,619 vs 7,410 events embedded, ~5% variance).

**Root Cause**: 
The **embedding pool architecture was fundamentally flawed**:
1. **Concurrent artifact parsing** → Events added to shared pool in non-deterministic order
2. **Size-based flushing (500 events)** → Jobs created at unpredictable boundaries depending on which artifacts completed first
3. **Race conditions** → Multiple workers adding events simultaneously caused non-deterministic batch composition
4. **Set-based deduplication** → Converting `set` to `list` had undefined order

Even with investigation-specific flushing, the order of concurrent artifact completion determined which events ended up in which batch.

**Fix**: 
**Redesigned the embedding pool for deterministic-only flushing**:
- **Disabled size-based flushing** (set threshold to 999999999)
- **Disabled timeout-based flushing** (set timeout to 999999 seconds)
- Pool only flushes when **all parsing jobs complete** for an investigation
- Events are **sorted before batching** for deterministic job boundaries
- Each flush creates jobs of exactly 1000 events (deterministic batch sizes)

**Result**: Embedding counts are now 100% deterministic - identical artifact bundles produce identical embedding counts across all investigations.

**Files Modified**:
- `api/app/services/embedding_pool.py` - Disabled automatic flushing, sort events before batching
- `api/app/services/embedding_batcher.py` - New queue-based batching service (runs as separate process)
- `api/worker/main.py` - Flush pool when parsing completes (deterministic trigger)
- `api/worker/parsers/dispatcher.py` - Queue events for batching instead of immediate job creation

**Tests Added**:
- `api/tests/unit/services/test_embedding_batcher.py` - 35 comprehensive tests
- `api/tests/unit/services/test_embedding_pool.py` - Enhanced with 21 tests (from 4 tests)
- `api/tests/unit/services/test_embedding_queue.py` - 12 tests for queue service

## Architecture Decision: Deterministic Embedding Pool

The embedding pool now uses **deterministic-only flushing** to guarantee consistent results:

**Key Design Principles**:
1. **No automatic flushing** - Size and timeout thresholds are effectively disabled
2. **Flush only on completion** - Pool flushes when all parsing jobs finish for an investigation
3. **Sorted batching** - Events are sorted by ID before creating jobs
4. **Fixed batch size** - Always 1000 events per job (deterministic boundaries)

**Why This Works**:
- ✅ **Deterministic**: Same artifacts → Same pool contents → Same sorted order → Same batches
- ✅ **Efficient**: Still creates large jobs (1000 events each)
- ✅ **Simple**: No complex timing logic or race conditions
- ✅ **Predictable**: Job count = ceiling(total_events / 1000)

**Example**:
- Investigation with 7,427 interesting events
- Pool accumulates all events during parsing
- When parsing completes: Sort → Batch → Create 8 jobs (7×1000 + 1×427)
- Same input always produces same 8 jobs with same event IDs in same order

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
