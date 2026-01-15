# API Component

FastAPI backend providing REST endpoints, WebSocket support, and intelligent query routing for the micro-forensics workbench.

For comprehensive documentation, see [docs/index.md](../docs/index.md).

## Quick Links

- [Architecture Overview](../docs/architecture.md)

## Overview

The API service handles:
- **RESTful API** endpoints for investigations, artifacts, events, and timeline data
- **WebSocket** connections for real-time agent reasoning and progress updates
- **Intelligent Query Routing** - LLM-based classification to 4 specialized handlers with manual mode override
- **RAG-Powered Search** - Hybrid BM25 + vector similarity search with LLM-driven query expansion and re-ranking
- **Advanced Tools** - SQL execution, JQ transformation, diagram generation (GraphViz/Mermaid)
- **Dynamic Turn Budget** - Agents can request additional investigation turns (up to 30 total)
- **Report Generation** - Automated PDF/Markdown reports with database persistence
- **Field Dictionary** - LLM-generated JSONB field descriptions for efficient querying
- **Context Summarization** - LLM-powered chat history compaction for long investigations
- **Authentication** using JWT tokens with role-based access control
- **Job queue** management for parsing and agent tasks
- **Chat persistence** for conversation history in OpenAI message format
- **Timeline management** for evidence chronology with event deduplication

### Technology Stack

- **FastAPI** 0.110 - Modern Python web framework
- **SQLAlchemy 2.0** - Async ORM with PostgreSQL support
- **Pydantic 2.7** - Data validation and serialization
- **PyJWT** - JSON Web Token authentication
- **Argon2** - Password hashing
- **Uvicorn** - ASGI server
- **aiohttp** - Async HTTP client for LLM calls

---

## Intelligent Query Routing

The API uses **LLM-based intent classification** or **manual mode selection** to route user queries to one of four specialized handlers:

### Routing Architecture

```
User Query → Manual Mode or LLM Classification → Handler Selection
                              ↓
    ┌───────────────────────┼────────────────────────────────┐
    │                       │                               │
 Agent Handler         Timeline Handler                General Chat
(Complex Analysis)     (Timeline CRUD)                (Metadata Q&A)
    │                       │                               │
11+ Forensic Tools     5 Timeline Tools                  No Tools
Multi-turn agent       Multi-turn LLM                Single LLM call
Job queue (async)      Synchronous                   Synchronous
    │                       │                               │
    └───────────────────────┴────────────────────────────────┘
                              ↓
                    Augmented Chat Handler
                         (RAG Search)
                              │
              Query Expansion + Vector Search
              Multi-query retrieval + Re-ranking
                        Synchronous
                              ↓
                    WebSocket Response + DB Persistence
```

### 1. **Agent Handler** (`services/handlers/policy_handler.py`)

**Full agentic investigation with 16+ forensic tools**

- **Triggers**: Event searches, complex analysis, multi-step investigations
- **Tools**: 16+ forensic tools including:
  - **Data Query**: search_events, query_jsonb, aggregate, hybrid_search (BM25 + vector)
  - **Advanced**: execute_sql, apply_jq for complex data manipulation
  - **Analysis**: register_timeline_entry, complete_investigation
  - **Visualization**: render_diagram (GraphViz/Mermaid)
  - **Control**: request_additional_turns (dynamic turn budget)
- **Execution**: Creates agent job, worker processes asynchronously with two-phase approach
- **Response**: Job queued message, worker streams updates via WebSocket
- **Features**:
  - **Hybrid Search**: Combines BM25 full-text search with vector similarity
  - **Dynamic Turns**: Agent can request 3-15 additional turns with justification (hard ceiling: 30)
  - **Field Dictionary**: Auto-generated JSONB field descriptions for efficient querying
  - **Memory Summarization**: LLM-powered chat history compaction preserves event IDs
- **Cost**: High (multiple LLM calls with tool execution)
- **Examples**:
  - "Find remote logons in the event data"
  - "Analyze suspicious PowerShell activity using semantic search"
  - "What files were modified by user jsmith? Create a timeline diagram."
  - "Run SQL query to find all events where TargetUserName contains 'admin'"

### 2. **Timeline Handler** (`services/handlers/timeline_handler.py`)

**LLM with timeline-specific tools for CRUD operations**

- **Triggers**: Timeline queries, add/update/delete timeline entries, statistics
- **Tools**: 5 timeline tools (query, add, update, delete, stats)
- **Execution**: Multi-turn LLM loop (up to 10 iterations)
- **Retry Logic**: Automatic retry on failures (up to 3 attempts per tool)
- **Transaction Safety**: Savepoint isolation to prevent transaction pollution
- **Response**: Immediate answer with micro-summary footer
- **Cost**: Medium (tool execution with LLM reasoning)
- **Examples**:
  - "Show me timeline entries from March 20-24"
  - "Add a timeline entry for this suspicious login"
  - "Timeline statistics"

**Timeline Tools**:
1. `query_timeline_entries` - Search/filter timeline entries
2. `add_timeline_entry` - Create new timeline entry
3. `update_timeline_entry` - Update existing entry
4. `delete_timeline_entry` - Delete entry by ID
5. `get_timeline_stats` - Get timeline statistics

### 3. **General Chat Handler** (`services/handlers/general_chat_handler.py`)

**Fast context-based Q&A without tools**

- **Triggers**: Investigation metadata questions, simple summaries
- **Tools**: None - answers from investigation context only
- **Execution**: Single LLM call with gathered context
- **Context**: Investigation metadata, timeline stats, artifacts, events
- **Response**: Immediate answer
- **Cost**: Low (one LLM call, no tool overhead)
- **Examples**:
  - "What is this investigation about?"
  - "How many timeline entries do we have?"
  - "Summarize the investigation"

### 4. **Augmented Chat Handler** (`services/handlers/rag_handler.py`)

**RAG-powered semantic search with hybrid retrieval and query expansion**

- **Triggers**: Manual mode selection ("Augmented Chat") or semantic search queries
- **Technology**: Hybrid BM25 + PGVector for best-of-both-worlds retrieval, LLM for query expansion and synthesis
- **Execution**: Multi-step pipeline with tool execution persistence
- **Requirements**: Embedding provider configured (OpenAI, Cohere, Ollama)
- **Response**: LLM answer with expandable source citations
- **Cost**: Medium-High (embedding generation + multiple LLM calls)

**Pipeline**:
1. **Query Expansion** - LLM generates 5-7 contextual search terms
   - Example: "credential access" → ["lsass.exe", "mimikatz", "SAM database", "NTLM hash", ...]
   - Saved as tool execution with expanded terms in result

2. **Multi-Query Retrieval** - Hybrid BM25 + vector search for each term
   - Original query + 7 expanded terms = 8 queries
   - Each query uses both BM25 (keyword) and vector (semantic) search
   - Each query retrieves 10 candidates = 80 total candidates
   - BM25 ranking via PostgreSQL `ts_rank_cd` for keyword relevance
   - Vector similarity via PGVector cosine distance for semantic matching

3. **Deduplication** - Remove duplicate events by (owner_type, owner_id)
   - Keeps highest similarity score for each unique event
   - Typical reduction: 80 candidates → 40-50 unique events

4. **Re-ranking** - Sort by similarity score, take top 50
   - Saved as single tool execution with all sources in result
   - Each source includes: owner_type, owner_id, score, full text

5. **LLM Synthesis** - Build context from sources and generate answer
   - Context includes all 50 sources with metadata
   - LLM cites sources by number in response

**Tool Executions Saved**:
- **Query Expansion**: Arguments: {}, Result: {expanded_terms: [...]}
- **Retrieved Sources (X results)**: Arguments: {total_sources, sources_by_type}, Result: {sources: [{index, owner_type, owner_id, score, text_preview, text_full}]}

**Examples**:
- "Is there evidence of credential access?"
- "Find lateral movement indicators"
- "Search for privilege escalation attempts"
- "Look for persistence mechanisms"

### Intent Classification

**LLM-based classification** (`services/chat_router.py:classify_intent`):
- Sends user query + classification prompt to LLM
- LLM responds with intent type (timeline_query, general_chat, execute_agent_policy, etc.)
- Confidence score and reasoning included

**Manual Mode Override**:
Users can force routing by selecting mode in UI:
- **Auto** - LLM classifies intent automatically (default)
- **Agent** - Force agent handler with full tools
- **Timeline** - Force timeline handler for CRUD
- **Augmented Chat** - Force RAG search

**Fallback classification** (when LLM unavailable):
- Keyword matching for timeline operations
- Event search keywords → Agent Handler
- Metadata questions → General Chat
- Default → General Chat (safest, cheapest)

---

## Architecture

```
api/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   ├── deps.py                  # Dependency injection
│   ├── auth.py                  # Authentication utilities
│   │
│   ├── core/                    # Core configuration
│   │   ├── config.py            # Settings management
│   │   ├── database.py          # Database connection
│   │   └── security.py          # Security utilities
│   │
│   ├── routers/                 # API endpoints
│   │   ├── auth.py              # Login, registration
│   │   ├── investigations.py   # Investigation CRUD
│   │   ├── artifacts.py         # Artifact upload/management
│   │   ├── events.py            # Event queries
│   │   ├── timeline.py          # Evidence timeline API
│   │   ├── chat.py              # Chat interface + WebSocket
│   │   ├── chat_history.py      # Conversation history
│   │   ├── jobs.py              # Job status queries
│   │   ├── llm_config.py        # LLM configuration
│   │   └── audit.py             # Audit log access
│   │
│   ├── services/                # Business logic
│   │   ├── chat_router.py       # Intent classification & routing
│   │   ├── policy_router.py     # Policy selection (agent)
│   │   ├── query_expander.py    # Context expansion
│   │   ├── llm_auth_helper.py   # LLM authentication
│   │   ├── chat_persistence.py  # Chat storage
│   │   ├── websocket_manager.py # WebSocket connections
│   │   ├── handlers/            # Specialized handlers
│   │   │   ├── event_handler.py        # Event insertion
│   │   │   ├── policy_handler.py       # Agent execution
│   │   │   ├── timeline_handler.py     # Timeline operations
│   │   │   ├── general_chat_handler.py # Context-based Q&A
│   │   │   └── rag_handler.py          # RAG search (NEW)
│   │   └── rag/                 # RAG components (NEW)
│   │       ├── embedding.py     # Embedding generation
│   │       ├── retriever.py     # Vector similarity search
│   │       ├── event_processor.py # Auto-embedding during parsing
│   │       └── filter_engine.py   # Interesting event filtering
│   │
│   ├── models/                  # SQLAlchemy models
│   ├── schemas/                 # Pydantic schemas
│   └── crud/                    # Database operations
│
├── worker/                      # Async job processor
│   ├── agents/                  # AI agents
│   ├── parsers/                 # Artifact parsers
│   └── tools/                   # Agent tools
│
├── db/                          # Database schema
├── data/                        # Policies and agent configs
├── Dockerfile                   # API container
└── requirements.txt             # Python dependencies
```

---

## Installation

### Docker (Recommended)

The API runs as a Docker container via `docker-compose`:

```bash
# Start all services
docker-compose up -d

# View API logs
docker-compose logs -f api

# Restart API only
docker-compose restart api
```

### Manual Installation

For development without Docker:

```bash
# Install Python 3.11+
python --version  # Should be 3.11 or higher

# Create virtual environment
cd api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://postgres:example@localhost/open_agent_inv"
export JWT_SECRET="your-secret-key-here"

# Run database migrations (if needed)
psql -U postgres -d open_agent_inv -f db/schema.sql

# Start the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Configuration

### Environment Variables

Configure via `.env` file or environment variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:example@db/open_agent_inv

# Security
JWT_SECRET=change-me-in-production-supersecret  # ⚠️ CHANGE THIS!

# API Server
API_HOST=api
API_PORT=8000

# CORS
UI_ORIGIN=http://localhost:5173

# Observability
PROMETHEUS_ENABLED=true

# File Storage
INVESTIGATIONS_BASE_PATH=/data/investigations
POLICIES_PATH=/app/data/policies
AGENTS_PATH=/app/data/agents

# Worker
WORKER_POLL_INTERVAL=1
WORKER_TIMEOUT=30
```

---

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login and receive JWT token |
| POST | `/api/v1/auth/register` | Create new user account |
| GET | `/api/v1/auth/me` | Get current user info |

### Investigations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/investigations` | List all investigations |
| POST | `/api/v1/investigations` | Create new investigation |
| GET | `/api/v1/investigations/{id}` | Get investigation details |
| DELETE | `/api/v1/investigations/{id}` | Delete investigation |

### Chat (Intelligent Routing)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chat/ask` | Ask a question (auto-routed) |
| WS | `/api/v1/chat/ws/{investigation_id}` | WebSocket for real-time updates |
| GET | `/api/v1/chat/history/{investigation_id}` | Get conversation history |

**Chat Flow**:
1. User sends question via WebSocket
2. Chat router classifies intent using LLM
3. Query routed to Agent/Timeline/General handler
4. Handler processes and streams response
5. UI receives updates and displays results

### Timeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/timeline/{investigation_id}` | Get timeline entries |
| POST | `/api/v1/timeline/{investigation_id}/entries` | Create timeline entry |
| PATCH | `/api/v1/timeline/{investigation_id}/entries/{entry_id}` | Update entry |
| DELETE | `/api/v1/timeline/{investigation_id}/entries/{entry_id}` | Delete entry |
| GET | `/api/v1/timeline/{investigation_id}/stats` | Get timeline statistics |

### LLM Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/llm-config` | Get user's LLM configs |
| POST | `/api/v1/llm-config` | Create LLM config (includes embedding config) |
| PUT | `/api/v1/llm-config/{id}` | Update LLM config |
| DELETE | `/api/v1/llm-config/{id}` | Delete LLM config |

### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/reports/generate` | Generate investigation report (markdown) |
| POST | `/api/v1/reports/download` | Download report as PDF |
| GET | `/api/v1/reports/latest/{investigation_id}` | Get most recent report |
| GET | `/api/v1/reports/latest/{investigation_id}/metadata` | Get report metadata only |

### Embeddings (RAG)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/embeddings/generate/investigation/{id}` | Backfill embeddings for investigation |
| GET | `/api/v1/embeddings/stats/{investigation_id}` | Get embedding statistics |

---

## Query Handlers

### Adding a New Handler

The routing system is **extensible**. To add a new handler:

1. **Create handler** in `app/services/handlers/your_handler.py`:
   ```python
   async def handle_your_operation(
       db: AsyncSession,
       investigation_id: UUID,
       user_query: str,
       user_id: int,
   ) -> Dict[str, Any]:
       # Your logic here
       return {
           "type": "your_answer",
           "success": True,
           "message": "Your response",
       }
   ```

2. **Add IntentType** to `app/schemas/chat_message.py`:
   ```python
   class IntentType(str, Enum):
       YOUR_OPERATION = "your_operation"
   ```

3. **Update classification prompt** in `app/services/chat_router.py`:
   ```python
   CLASSIFICATION_PROMPT = """...
   5. **your_operation** - Description
      Examples: ...
   """
   ```

4. **Add routing case** in `chat_router.py:route_chat_message`:
   ```python
   elif classification.intent == IntentType.YOUR_OPERATION:
       result = await handle_your_operation(db, investigation_id, processing_query, user_id)
       yield {"type": "answer_chunk", "content": result.get("message"), "is_final": True}
   ```

---

## Authentication

### JWT Token Flow

1. **Login**: User submits credentials to `/api/v1/auth/login`
2. **Token Generation**: API returns JWT token (valid for 24 hours)
3. **Authorization**: Client includes token in `Authorization: Bearer <token>` header
4. **Validation**: API validates token on each request

### Password Security

- Passwords are hashed using **Argon2id** (memory-hard algorithm)
- Default admin password (`admin123`) should be changed immediately
- Password hashing parameters: `m=65536, t=3, p=4`

---

## WebSocket Support

### Real-time Updates

Connect to WebSocket for streaming responses:

```javascript
const ws = new WebSocket(
  `ws://localhost:8000/api/v1/chat/ws/${investigationId}?token=${jwtToken}`
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'intent_classified':
      console.log('Routed to:', data.intent);
      break;
    case 'answer_chunk':
      console.log('Answer:', data.content);
      if (data.is_final) {
        console.log('Complete!');
      }
      break;
    case 'job_queued':
      console.log('Agent job started:', data.job_id);
      break;
    case 'investigation_state_changed':
      if (data.state === 'idle') {
        console.log('UI unlocked');
      }
      break;
  }
};
```

### Message Types

| Type | Description | Handler |
|------|-------------|---------|
| `intent_classified` | Intent classification result | All |
| `answer_chunk` | Response chunk (Timeline/General) | Timeline, General |
| `job_queued` | Agent job created | Agent |
| `agent_thinking` | Agent reasoning step | Agent |
| `agent_tool_call` | Agent invoking a tool | Agent |
| `investigation_state_changed` | UI lock/unlock signal | All |
| `message_created` | New message added to chat | All |
| `message_updated` | Message content/metadata updated | All |

---

## Development

### Running Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Install dev dependencies
pip install pytest pytest-asyncio httpx black isort flake8

# Run tests
pytest tests/

# Format code
black app/
isort app/

# Lint
flake8 app/
```

### API Documentation

FastAPI auto-generates interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Testing Routing

```bash
# Test intent classification
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"investigation_id": "...", "question": "Show me timeline entries"}'

# Check logs for routing decision
docker-compose logs api | grep "CHAT_ROUTER"
# Output: [CHAT_ROUTER] Classified as: timeline_query (confidence: 0.9)
# Output: [CHAT_ROUTER] → Route 2: Timeline Handler
```

---

## Troubleshooting

### Common Issues

**Problem**: Queries always route to Agent Handler  
**Solution**: Check LLM classification prompt and fallback keywords in `chat_router.py`

**Problem**: Timeline handler transaction errors  
**Solution**: Savepoints are used for transaction isolation. Check logs for specific SQL errors.

**Problem**: General chat returns "No LLM configuration"  
**Solution**: Configure LLM settings via `/api/v1/llm-config`

**Problem**: WebSocket disconnects immediately  
**Solution**: Check JWT token validity and investigation_id format

**Problem**: RAG mode returns "No relevant sources found"  
**Solution**: 
- Check if embeddings exist: `SELECT COUNT(*) FROM embeddings`
- Verify embedding provider is configured in LLM settings
- Check if events have been parsed and embedded
- Create IVFFLAT index if missing: `CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);`

**Problem**: RAG query expansion returns no terms  
**Solution**: Check LLM configuration and ensure LLM endpoint is accessible

### Debug Logging

```bash
# Enable debug logging for routing
export LOG_LEVEL=DEBUG

# Check classification decisions
docker-compose logs api | grep "\[CHAT_ROUTER\]"

# Check handler execution
docker-compose logs api | grep "\[TIMELINE_HANDLER\]"
docker-compose logs api | grep "\[GENERAL_CHAT\]"
```

---

## Further Reading

- [Main README](../README.md) - Platform overview and usage
- [Worker Documentation](worker/README.md) - Agent execution and parsing
- [Database Schema](../db/README.md) - PostgreSQL table definitions
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Framework reference

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../README.md).
