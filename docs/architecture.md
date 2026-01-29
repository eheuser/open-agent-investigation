# Architecture

This document describes the system architecture, component interactions, and key design decisions.

## System Overview

A micro-forensics workbench for analyzing artifacts. The system is a multi-tier application consisting of four main components:

```
┌─────────────────────────────────────────────────────────────┐
│                         UI (React)                          │
│  Browser-based interface for investigations and analysis   │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTPS / WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    API (FastAPI)                            │
│  REST endpoints, WebSocket server, query routing           │
└────────────────────────────┬────────────────────────────────┘
                             │ PostgreSQL protocol
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                PostgreSQL 15 + PGVector                     │
│  Events, timeline, artifacts, chat history, embeddings     │
└────────────────────────────┬────────────────────────────────┘
                             │ Job queue polling
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Worker (AsyncIO)                         │
│  Artifact parsing, agent execution, job processing          │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### UI (React Frontend)

**Purpose:** Interactive web interface for forensic investigations

**Technology:**
- React 18.2 with TypeScript
- Vite build system
- TailwindCSS for styling
- Axios for HTTP requests
- WebSocket for real-time updates

**Key Features:**
- Investigation dashboard
- Chat interface with mode selection
- Evidence timeline viewer
- Events table with advanced filtering
- Artifact upload with drag-and-drop
- Report generation
- LLM configuration

**Location:** `ui/`

### API (FastAPI Backend)

**Purpose:** REST API server, WebSocket hub, and query router

**Technology:**
- FastAPI 0.110 (async Python web framework)
- SQLAlchemy 2.0 (async ORM)
- Pydantic 2.7 (data validation)
- PyJWT (authentication)
- Uvicorn (ASGI server)

**Key Responsibilities:**
- HTTP request handling
- WebSocket connection management
- Query routing and intent classification
- Authentication and authorization
- Job queue management
- Real-time progress broadcasting

**Location:** `api/app/`

### Database (PostgreSQL 15)

**Purpose:** Persistent data storage with JSONB and vector support

**Technology:**
- PostgreSQL 15
- PGVector extension (vector similarity search)
- pg_crypto extension (encryption)

**Key Features:**
- JSONB columns for flexible event storage
- GIN indexes for fast JSONB queries
- Vector embeddings for semantic search
- Full-text search with ts_rank_cd
- Transaction isolation with savepoints

**Schema Tables:**
- `users` - User accounts
- `investigations` - Investigation metadata
- `artifacts` - Uploaded forensic files
- `events` - Parsed forensic events
- `timeline_entries` - Evidence timeline
- `chat_messages` - Conversation history
- `tool_executions` - Agent tool invocations
- `embeddings` - Vector embeddings for RAG
- `jobs_parsing` - Parsing job queue
- `jobs_agents` - Agent job queue
- `llm_provider_config` - LLM settings
- `audit_log` - Immutable audit trail

**Location:** `db/`

### Worker (Async Job Processor)

**Purpose:** Background processing for parsing and agent execution

**Technology:**
- Python asyncio
- Multiprocessing pool (min(CPU_count, 4) workers)
- aiohttp (HTTP client for LLM calls)

**Key Responsibilities:**
- Artifact parsing (EVTX, Registry, MFT, Prefetch, LNK)
- Agent execution with bounded turns
- Real-time progress streaming
- Job queue polling with atomic claiming
- Process monitoring and restart

**Parsers:**
- `evtx_parser.py` - Windows Event Logs
- `registry_parser.py` - Registry hives
- `mft_parser.py` - NTFS Master File Table
- `prefetch_parser.py` - Prefetch files
- `lnk_parser.py` - LNK shortcuts

**Agents:**
- `assistant_agent_v2.py` - Primary forensic agent (bounded turns)

**Investigation Playbooks:**
- 21 YAML-based playbooks for attack scenarios
- LLM-driven automatic selection
- Dynamic loading and hot-reload support
- See [Investigation Playbooks](playbooks.md) for details

**Location:** `api/worker/`

## Data Flow

### Artifact Upload and Parsing

```
1. User uploads file via UI
   ↓
2. API receives file, calculates SHA-256
   ↓
3. API stores artifact in database (blob column)
   ↓
4. API creates ParsingJob (status: pending)
   ↓
5. Worker polls database, claims job (SELECT FOR UPDATE SKIP LOCKED)
   ↓
6. Worker dispatches to appropriate parser
   ↓
7. Parser extracts events, inserts to events table (batch 1000)
   ↓
8. Worker updates job status to completed
   ↓
9. UI polls job status, displays completion
```

### Question and Answer Flow

```
1. User asks question in Chat tab
   ↓
2. UI sends question via WebSocket
   ↓
3. API classifies intent (LLM or keyword matching)
   ↓
4. API routes to appropriate handler:
   - Agent Handler → Creates AgentJob, worker processes
   - Timeline Handler → Executes timeline tools synchronously
   - General Chat → Single LLM call with context
   - Augmented Chat → RAG pipeline with embeddings
   ↓
5. Handler executes and streams progress
   ↓
6. API broadcasts updates via WebSocket
   ↓
7. UI receives updates, displays in real-time
   ↓
8. Handler completes, final answer sent
   ↓
9. UI displays complete response with statistics
```

## Query Routing

Query routing is the core intelligence layer that directs user questions to the most appropriate handler.

### Routing Decision Tree

```
User Question + Mode Selection
         │
         ├─ Manual Mode Selected? ───→ Use selected mode
         │
         └─ Auto Mode ───→ LLM Classification
                                │
                                ├─ Timeline keywords? ───→ Timeline Handler
                                ├─ Event search keywords? ───→ Agent Handler
                                ├─ Metadata keywords? ───→ General Chat
                                └─ Semantic search? ───→ Augmented Chat
```

### Handler Comparison

| Handler | Execution | Tools | Cost | Use Case |
|---------|-----------|-------|------|----------|
| Agent | Async (worker) | 16+ forensic tools | High | Complex analysis, multi-step investigation |
| Timeline | Sync (API) | 5 timeline tools | Medium | Timeline CRUD, filtering, statistics |
| General | Sync (API) | None | Low | Metadata questions, simple summaries |
| Augmented Chat | Sync (API) | RAG pipeline | Medium-High | Semantic search, evidence discovery |

### Agent Handler Architecture

The Agent Handler uses a bounded turn execution model with investigation playbook support:

**Playbook Integration:**

Before each investigation, the system:
1. Loads all available playbooks from `api/worker/agents/playbooks/`
2. Presents playbook descriptions to LLM
3. LLM selects most relevant playbook (or "none")
4. Selected playbook content injected into investigation strategy
5. Agent follows playbook guidance during execution

**Example:** User asks "Find evidence of lateral movement" → LLM selects `lateral_movement.yaml` → Agent receives strategic guidance on Event IDs 4624, 4648, network logons, admin shares, etc.

**Turn Execution:**

```
Agent Job Created (status: pending)
         │
         ▼
Worker Claims Job (SELECT FOR UPDATE SKIP LOCKED)
         │
         ▼
Initialize Agent (load context, LLM config)
         │
         ▼
┌────────────────────────────────────────┐
│          Turn Loop (max 5-15)          │
│                                        │
│  1. Agent plans next action            │
│  2. Agent calls up to 5 tools          │
│  3. Tools execute, return results      │
│  4. Agent analyzes results             │
│  5. Agent explains findings            │
│  6. Stream progress to UI              │
│                                        │
│  Repeat until:                         │
│  - Max turns reached                   │
│  - Agent calls complete_investigation  │
│  - Error occurs                        │
└────────────────────────────────────────┘
         │
         ▼
Agent Completes (status: completed)
         │
         ▼
Final Summary Sent to UI
```

**Turn Budget:**
- Quick: 3 turns max
- Standard: 6 turns max
- Thorough: 9 turns max
- Dynamic extension: Agent can request 3-9 additional turns (hard ceiling: 30)

**Tools per Turn:** Maximum 5 tool executions per turn

### Timeline Handler Architecture

The Timeline Handler uses a synchronous multi-turn loop with automatic retry:

```
Timeline Query Received
         │
         ▼
Initialize LLM with Timeline Tools
         │
         ▼
┌────────────────────────────────────────┐
│       Multi-Turn Loop (max 10)         │
│                                        │
│  1. LLM decides which tool to call     │
│  2. Tool executes with savepoint       │
│  3. Retry up to 3 times on failure     │
│  4. LLM receives results               │
│  5. LLM decides: continue or finish    │
│                                        │
│  Repeat until:                         │
│  - LLM generates final answer          │
│  - Max iterations reached              │
│  - Error occurs                        │
└────────────────────────────────────────┘
         │
         ▼
Response Sent with Micro-Summary
```

**Transaction Safety:** Each tool execution uses a savepoint to prevent transaction pollution.

**Retry Logic:** Failed tool executions are retried up to 3 times with exponential backoff.

### Augmented Chat (RAG) Architecture

The Augmented Chat Handler implements a hybrid retrieval-augmented generation pipeline:

```
User Question
     │
     ▼
┌─────────────────────────────────────┐
│      Query Expansion (LLM)          │
│  Generate 5-7 contextual terms      │
│  Example: "credential access" →     │
│    ["lsass.exe", "mimikatz", ...]   │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│   Multi-Query Retrieval             │
│  - Generate embeddings (8 queries)  │
│  - BM25 search (keyword matching)   │
│  - Vector search (semantic)         │
│  - Retrieve 10 per query (80 total) │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│   Deduplication & Re-ranking        │
│  - Remove duplicates by event ID    │
│  - Sort by similarity score         │
│  - Take top 50 sources              │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│      LLM Synthesis                  │
│  - Build context from 50 sources    │
│  - Generate answer with citations   │
│  - Save tool executions             │
└─────────────────────────────────────┘
     │
     ▼
Answer with Expandable Sources
```

**Hybrid Search:** Combines BM25 (keyword) and vector similarity (semantic) for best results.

**Query Expansion:** LLM generates contextually relevant search terms to improve recall.

**Deduplication:** Ensures each event appears only once in results.

## Evidence Timeline Design

The timeline uses an event-first architecture to ensure data integrity.

### Event-First Principles

1. **Timeline entries reference events by ID** - No data duplication
2. **Event data auto-fetched** - Complete payload retrieved on demand
3. **Immutable events** - Original forensic data never modified
4. **Deduplication enforced** - Unique constraint on (investigation_id, event_id)

### Timeline Entry Structure

```sql
CREATE TABLE timeline_entries (
    entry_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL,
    event_id BIGINT REFERENCES events(event_id),  -- Foreign key to events
    entry_type TEXT NOT NULL,  -- 'event', 'finding', 'observation', 'note'
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    data JSONB,  -- Additional context, NOT event payload
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (investigation_id, event_id)  -- Prevent duplicates
);
```

### Timeline Population

**Automatic (Agent):**
- Agent calls `register_timeline_entry(event_id, title, tags)`
- System fetches complete event data from events table
- Timeline entry created with reference to event
- UI displays entry with auto-fetched event payload

**Manual (User):**
- User clicks "Add to Timeline" in Events tab
- System creates entry referencing selected event
- Complete event data available immediately

**Bulk (Agent with auto_register):**
- Agent calls search tool with `auto_register=true`
- System bulk-registers all returned event IDs
- Timeline updated with multiple entries
- UI counter increments automatically

## Security Architecture

### Authentication

**JWT Token-Based:**
- User logs in with username/password
- Server validates credentials (Argon2id hash verification)
- Server issues JWT token (24-hour expiration)
- Client includes token in Authorization header
- Server validates token on each request

**Token Structure:**
```json
{
  "sub": "user_id",
  "username": "admin",
  "role": 1,
  "exp": 1234567890
}
```

### Authorization

**Role-Based Access Control (RBAC):**
- Regular users (role 0): CRUD on own investigations
- Administrators (role 1): CRUD on all investigations, user management

**Investigation Ownership:**
- Users can only access investigations they own
- Admins can access all investigations
- Ownership enforced at database level (WHERE clauses)

### Data Protection

**Passwords:**
- Hashed with Argon2id (memory-hard algorithm)
- Parameters: m=65536, t=3, p=4
- Never stored or transmitted in plaintext

**API Keys:**
- Stored encrypted in database (pg_crypto)
- Decrypted only when needed for LLM calls
- Never logged or exposed in API responses

**Database:**
- SSL/TLS connections in production (sslmode=require)
- Connection pooling with limited max connections
- Prepared statements prevent SQL injection

## Scalability Considerations

### Horizontal Scaling

**Workers:**
- Multiple worker processes can run concurrently
- Job claiming uses SELECT FOR UPDATE SKIP LOCKED (no conflicts)
- Scale with: `docker compose up -d --scale worker=N`

**API Servers:**
- Multiple API instances behind load balancer
- Stateless design (no session affinity required)
- WebSocket connections sticky to single instance

### Vertical Scaling

**Database:**
- Increase shared_buffers for more memory
- Add indexes for frequently queried JSONB paths
- Partition events table by investigation_id for very large datasets

**Workers:**
- Increase worker count (up to CPU core count)
- Increase memory for large artifact parsing
- Use SSD storage for faster parsing

### Performance Optimization

**Database Queries:**
- GIN indexes on JSONB columns
- Partial indexes on job status (only pending jobs)
- Connection pooling (SQLAlchemy async pool)

**Event Storage:**
- Batch inserts (1000 events per transaction)
- JSONB for flexible schema without ALTER TABLE
- Flattened JSONB keys for efficient indexing

**Caching:**
- LLM responses not cached (investigation-specific)
- Static assets cached by nginx
- Database connection pool reuse

## Deployment Topologies

### Single-Node Deployment (Default)

```
┌─────────────────────────────────────┐
│          Docker Host                │
│                                     │
│  ┌─────┐  ┌─────┐  ┌────────┐     │
│  │ UI  │  │ API │  │ Worker │     │
│  └─────┘  └─────┘  └────────┘     │
│                                     │
│  ┌──────────────────────────┐     │
│  │      PostgreSQL          │     │
│  └──────────────────────────┘     │
└─────────────────────────────────────┘
```

Suitable for: Development, small teams, < 100k events

### Multi-Node Deployment

```
┌──────────────┐     ┌──────────────┐
│  UI (nginx)  │     │  UI (nginx)  │
└──────┬───────┘     └──────┬───────┘
       │                    │
       └────────┬───────────┘
                │
         ┌──────┴──────┐
         │ Load Balancer│
         └──────┬──────┘
                │
       ┌────────┴────────┐
       │                 │
┌──────┴──────┐   ┌──────┴──────┐
│  API Node 1 │   │  API Node 2 │
└──────┬──────┘   └──────┬──────┘
       │                 │
       └────────┬────────┘
                │
         ┌──────┴──────┐
         │  PostgreSQL │
         │  (Primary)  │
         └──────┬──────┘
                │
         ┌──────┴──────┐
         │  PostgreSQL │
         │  (Replica)  │
         └─────────────┘

┌──────────────┐   ┌──────────────┐
│  Worker 1    │   │  Worker 2    │
└──────────────┘   └──────────────┘
```

Suitable for: Production, large teams, > 100k events

## Technology Choices

### Why FastAPI?

- Async/await support for high concurrency
- Automatic OpenAPI documentation
- Pydantic integration for data validation
- WebSocket support built-in
- Modern Python framework with active community

### Why PostgreSQL?

- JSONB support for flexible event storage
- PGVector extension for semantic search
- Full-text search capabilities
- ACID transactions with savepoints
- Mature ecosystem and tooling

### Why React?

- Component-based architecture
- Large ecosystem of libraries
- TypeScript support for type safety
- Virtual DOM for efficient updates
- Strong community and documentation

### Why Docker?

- Consistent environments across dev/prod
- Simplified dependency management
- Easy scaling with docker compose
- Isolation between components
- Portable deployment

## Design Decisions

### JSONB for Event Storage

**Rationale:** Forensic events have diverse schemas across artifact types. JSONB allows flexible storage without schema migrations.

**Trade-offs:**
- Pro: No ALTER TABLE for new fields
- Pro: GIN indexes enable fast queries
- Con: Larger storage footprint than normalized tables
- Con: No foreign key constraints on JSONB fields

### Event-First Timeline

**Rationale:** Prevent data duplication and ensure timeline accuracy.

**Trade-offs:**
- Pro: Single source of truth (events table)
- Pro: No transcription errors
- Pro: Automatic updates if events change
- Con: Requires JOIN to fetch event data
- Con: Timeline entries orphaned if events deleted

### Bounded Turn Execution

**Rationale:** Prevent runaway agent execution and control costs.

**Trade-offs:**
- Pro: Predictable execution time
- Pro: Cost control (max 5 tools × 15 turns = 75 tools)
- Pro: Forces agent to be efficient
- Con: May not complete complex investigations
- Con: Requires continuation mechanism

### Multiprocessing Workers

**Rationale:** Parallelize job processing for faster throughput.

**Trade-offs:**
- Pro: Utilize multiple CPU cores
- Pro: Fault isolation (crashed worker doesn't affect others)
- Con: More complex process management
- Con: Higher memory usage

## Future Architecture Considerations

### Planned Enhancements

1. **Distributed Workers** - Worker pool across multiple machines
2. **Read Replicas** - PostgreSQL read replicas for query scaling
3. **Object Storage** - S3-compatible storage for artifacts (reduce database size)
4. **Message Queue** - RabbitMQ or Redis for job queue (replace database polling)
5. **Kubernetes** - Container orchestration for production deployments
6. **Caching Layer** - Redis for frequently accessed data

### Research Areas

1. **Graph Database** - Neo4j for knowledge graph storage and queries
2. **Time-Series Database** - TimescaleDB for event timeline optimization
3. **Distributed Tracing** - OpenTelemetry for performance monitoring
4. **Multi-Tenancy** - Database-per-tenant or schema-per-tenant isolation
