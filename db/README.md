# Database Component

PostgreSQL 15 database storing all investigation data, events, timelines, artifacts, jobs, and audit logs.

## Table of Contents

- [Overview](#overview)
- [Schema Design](#schema-design)
- [Tables](#tables)
- [Indexes](#indexes)
- [Functions & Triggers](#functions--triggers)
- [Migrations](#migrations)
- [Backup & Restore](#backup--restore)
- [Performance Tuning](#performance-tuning)

---

## Overview

The database uses:
- **PostgreSQL 15** - Modern relational database with JSONB support
- **pg_crypto** - Encryption extension for sensitive data
- **uuid-ossp** - UUID generation
- **JSONB** - Flexible JSON storage with indexing
- **GIN Indexes** - Fast JSONB and array queries
- **Triggers** - Automatic timestamp updates

### Design Principles

**Multi-Tenancy**: All tables use `investigation_id` for data isolation between investigations

**Flexible Schema**: JSONB payloads accommodate diverse artifact types without schema changes

**Event-First Architecture**: Timeline entries reference events by ID to prevent data duplication

**Audit Trail**: Immutable audit logs track all actions for forensic integrity

**Cascade Deletes**: Deleting an investigation automatically removes all related data

**Concurrency**: `SELECT FOR UPDATE SKIP LOCKED` enables multiple workers to claim jobs safely

**Deduplication**: Unique constraints prevent duplicate timeline entries

---

## Schema Design

### Entity-Relationship Diagram

```
┌──────────────┐
│    users     │
│ (user_id PK) │
└──────┬───────┘
       │
       │ owner_user_id
       ▼
┌──────────────────────┐
│   investigations     │
│ (investigation_id PK)│
└──────┬───────────────┘
       │
       ├──────────────────────────────────────┐
       │                                      │
       │ investigation_id                     │ investigation_id
       ▼                                      ▼
┌──────────────┐                      ┌──────────────┐
│  artifacts   │                      │    events    │
│(artifact_id) │                      │  (event_id)  │
└──────┬───────┘                      └──────────────┘
       │
       │ artifact_id                   investigation_id
       ▼                                      ▼
┌──────────────┐                      ┌──────────────┐
│jobs_parsing  │                      │ graph_nodes  │
│  (job_id)    │                      │  (node_id)   │
└──────────────┘                      └──────┬───────┘
                                             │
                                             │ source_id, target_id
                                             ▼
                                      ┌──────────────┐
                                      │ graph_edges  │
                                      │  (edge_id)   │
                                      └──────────────┘
```

---

## Tables

### Core Tables

#### users

User accounts with role-based access control.

```sql
CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role SMALLINT NOT NULL DEFAULT 0,  -- 0=regular, 1=admin
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `user_id` - Auto-incrementing primary key
- `username` - Unique username (case-sensitive)
- `password_hash` - Argon2id hash (never store plaintext!)
- `role` - 0 (regular user) or 1 (admin)
- `created_at` - Account creation timestamp

**Indexes**:
- `idx_users_username` - Fast username lookups
- `idx_users_role` - Filter by role

**Default Data**:
- Username: `admin`, Password: `admin123` (hash: `$argon2id$v=19$m=65536,t=3,p=4$...`)

#### investigations

Investigation metadata.

```sql
CREATE TABLE investigations (
    investigation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    owner_user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `investigation_id` - UUID primary key (auto-generated)
- `title` - Investigation name (e.g., "Ransomware Investigation - March 2024")
- `owner_user_id` - User who created the investigation (nullable if user deleted)
- `created_at` - Creation timestamp

**Indexes**:
- `idx_investigations_owner` - Filter by owner
- `idx_investigations_created` - Sort by creation date

**Cascade Behavior**:
- Deleting an investigation cascades to: artifacts, events, graph_nodes, graph_edges, jobs

#### artifacts

Uploaded forensic files with binary storage.

```sql
CREATE TABLE artifacts (
    artifact_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    sha256 BYTEA NOT NULL CHECK (length(sha256) = 32),
    filename TEXT NOT NULL,
    classification SMALLINT NOT NULL,  -- 0=SYSTEM_HIVE, 1=LOG_FILE, 2=BINARY, 3=ARCHIVE, 4=UNKNOWN
    blob BYTEA NOT NULL,
    upload_ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `artifact_id` - Auto-incrementing primary key
- `investigation_id` - Parent investigation
- `sha256` - SHA-256 hash (32 bytes) for deduplication
- `filename` - Original filename (e.g., "Security.evtx")
- `classification` - Artifact type (see enum below)
- `blob` - Binary file contents
- `upload_ts` - Upload timestamp

**Classification Enum**:
- `0` - SYSTEM_HIVE (Registry hive)
- `1` - LOG_FILE (EVTX, text logs)
- `2` - BINARY (Executables, DLLs)
- `3` - ARCHIVE (ZIP, TAR)
- `4` - UNKNOWN

**Indexes**:
- `idx_artifacts_investigation` - Filter by investigation
- `idx_artifacts_sha256` - Deduplication checks
- `idx_artifacts_upload_ts` - Sort by upload time

#### events

Unified event data across all investigations.

```sql
CREATE TABLE events (
    event_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    event_ts TIMESTAMPTZ NOT NULL,
    artifact_id BIGINT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `event_id` - Auto-incrementing primary key
- `investigation_id` - Parent investigation
- `event_ts` - When the event occurred (forensic timestamp)
- `artifact_id` - Source artifact (nullable if artifact deleted)
- `event_type` - Event type (e.g., "evtx_security_4624", "mft_entry")
- `payload` - Flattened JSONB data (see [Payload Structure](#payload-structure))
- `created_at` - When event was inserted

**Indexes**:
- `idx_events_investigation` - Filter by investigation + sort by event_ts
- `idx_events_type` - Filter by event type
- `idx_events_artifact` - Filter by artifact
- `idx_events_payload` (GIN) - Fast JSONB queries

**Payload Structure**:

Events use **flattened JSONB** (dotted notation for nested fields):

```json
{
  "event_id": 4624,
  "timestamp": "2024-03-24T12:38:23.153533Z",
  "record_id": 123456,
  "system.Computer": "WORKSTATION01",
  "system.Channel": "Security",
  "system.EventID": 4624,
  "SubjectUserName": "SYSTEM",
  "TargetUserName": "jsmith",
  "IpAddress": "192.168.1.100",
  "LogonType": "3"
}
```

#### graph_nodes

Knowledge graph nodes (entities and findings).

```sql
CREATE TABLE graph_nodes (
    node_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    tags TEXT[] DEFAULT '{}'::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `node_id` - Auto-incrementing primary key
- `investigation_id` - Parent investigation
- `label` - Human-readable label (e.g., "User: jsmith", "Process: powershell.exe")
- `data` - JSONB metadata (event_ids, timestamps, custom fields)
- `tags` - Array of tags (e.g., `["suspicious", "authentication"]`)
- `created_at` - Creation timestamp
- `updated_at` - Last modification timestamp (auto-updated by trigger)

**Indexes**:
- `idx_graph_nodes_investigation` - Filter by investigation
- `idx_graph_nodes_label` - Search by label
- `idx_graph_nodes_tags` (GIN) - Filter by tags
- `idx_graph_nodes_data` (GIN) - Query JSONB data
- `idx_graph_nodes_created` - Sort by creation time

**Common Node Types**:
- `user` - User accounts
- `computer` - Systems
- `ip_address` - Network endpoints
- `process` - Executed programs
- `file` - Files of interest
- `registry_key` - Registry modifications
- `event` - Significant events
- `finding` - Investigation conclusions

#### graph_edges

Knowledge graph edges (relationships).

```sql
CREATE TABLE graph_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    tags TEXT[] DEFAULT '{}'::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_graph_edges_no_self_loop CHECK (source_id != target_id)
);
```

**Columns**:
- `edge_id` - Auto-incrementing primary key
- `investigation_id` - Parent investigation
- `source_id` - Source node ID
- `target_id` - Target node ID
- `relationship` - Relationship type (e.g., "authenticated_from", "spawned")
- `data` - JSONB metadata (timestamps, confidence, etc.)
- `tags` - Array of tags
- `created_at` - Creation timestamp
- `updated_at` - Last modification timestamp (auto-updated by trigger)

**Indexes**:
- `idx_graph_edges_investigation` - Filter by investigation
- `idx_graph_edges_source` - Find edges from node
- `idx_graph_edges_target` - Find edges to node
- `idx_graph_edges_relationship` - Filter by relationship type
- `idx_graph_edges_tags` (GIN) - Filter by tags
- `idx_graph_edges_created` - Sort by creation time

**Common Relationships**:
- `authenticated_from` - User → IP
- `authenticated_as` - User → Computer
- `spawned` - Process → Process (parent-child)
- `created` - Process → File
- `modified` - Process → File/Registry
- `accessed` - User/Process → File
- `related_to` - Generic association

### Job Queue Tables

#### jobs_parsing

Queue for artifact parsing jobs.

```sql
CREATE TABLE jobs_parsing (
    job_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    artifact_id BIGINT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    status job_status NOT NULL DEFAULT 'pending',
    worker_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);
```

**Status Enum**: `pending`, `running`, `completed`, `failed`

**Indexes**:
- `idx_jobs_parsing_status` (partial) - Only indexes `pending` jobs for fast claiming
- `idx_jobs_parsing_investigation` - Filter by investigation
- `idx_jobs_parsing_created` - Sort by creation time

#### jobs_agents

Queue for agent execution jobs.

```sql
CREATE TABLE jobs_agents (
    job_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL,
    rule_values JSONB DEFAULT '{}',
    seed_instructions TEXT NOT NULL,
    status job_status NOT NULL DEFAULT 'pending',
    worker_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);
```

**Columns**:
- `policy_id` - Policy YAML filename (e.g., "event_search")
- `rule_values` - Policy parameters (e.g., `{"effort": "medium"}`)
- `seed_instructions` - Agent prompt template with question

**Indexes**:
- `idx_jobs_agents_status` (partial) - Only indexes `pending` jobs
- `idx_jobs_agents_investigation` - Filter by investigation
- `idx_jobs_agents_user` - Filter by user (for LLM config lookup)
- `idx_jobs_agents_created` - Sort by creation time
- `idx_jobs_agents_policy` - Filter by policy

### Configuration Tables

#### llm_provider_config

Per-user LLM provider configuration.

```sql
CREATE TABLE llm_provider_config (
    config_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider_name TEXT NOT NULL DEFAULT 'openai',
    api_endpoint TEXT NOT NULL,
    api_key TEXT,
    model_name TEXT DEFAULT 'gpt-4',
    max_context_length INTEGER NOT NULL DEFAULT 8192,
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.70,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_temperature CHECK (temperature >= 0.0 AND temperature <= 2.0),
    CONSTRAINT valid_context_length CHECK (max_context_length > 0 AND max_context_length <= 1000000)
);
```

**Columns**:
- `provider_name` - Provider identifier (e.g., "openai", "ollama", "custom")
- `api_endpoint` - LLM API URL (e.g., "https://api.openai.com/v1/chat/completions")
- `api_key` - API key (encrypted at rest, nullable for cookie-based auth)
- `model_name` - Model identifier (e.g., "gpt-4", "llama3")
- `max_context_length` - Token limit (e.g., 8192, 32768)
- `temperature` - Sampling temperature (0.0-2.0)
- `is_active` - Whether this config is currently active (only one per user)
- `allow_concurrent_llm_calls` - Enable parallel LLM requests (default: false)
- `embedding_provider` - Embedding provider for RAG (e.g., "openai", "cohere", "ollama")
- `embedding_api_url` - Embedding API endpoint
- `embedding_api_key` - Embedding API key (encrypted)
- `embedding_model_name` - Model for initial embedding generation (e.g., "text-embedding-3-small")
- `embedding_max_context_length` - Max tokens for embedding model (default: 8192)
- `reranker_model_name` - Model for reranking top candidates (e.g., "text-embedding-3-large")
- `reranker_max_context_length` - Max tokens for reranker model (default: 8192)
- `allow_concurrent_embedding_calls` - Enable parallel embedding/reranking requests (default: false)

**Indexes**:
- `idx_llm_config_user` - Filter by user
- `idx_llm_config_active` (partial) - Only indexes active configs

**Trigger**: `enforce_single_active_config` - Ensures only one active config per user

#### chat_messages

Conversation history in OpenAI message format.

```sql
CREATE TABLE chat_messages (
    message_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    
    role VARCHAR(20) NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT,
    name VARCHAR(100),
    tool_calls JSONB,
    tool_call_id VARCHAR(100),
    
    metadata JSONB DEFAULT '{}'::jsonb,
    include_in_llm_context BOOLEAN NOT NULL DEFAULT true,
    visible_in_ui BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Columns**:
- `role` - OpenAI role (system, user, assistant, tool)
- `content` - Message text (nullable for tool_calls)
- `name` - Optional name for tool messages
- `tool_calls` - Tool invocation array (for assistant messages)
- `tool_call_id` - Tool call ID (for tool response messages)
- `metadata` - Additional data (intent, confidence, job_id, etc.)
- `include_in_llm_context` - Whether to include when building LLM context
- `visible_in_ui` - Whether to display in chat UI

**Indexes**:
- `idx_chat_messages_investigation` - Filter by investigation + sort by created_at
- `idx_chat_messages_llm_context` - Filter by investigation + include_in_llm_context
- `idx_chat_messages_user` - Filter by user

### Audit & Logging Tables

#### audit_log

Immutable audit trail of all system actions.

```sql
CREATE TABLE audit_log (
    log_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    investigation_id UUID REFERENCES investigations(investigation_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details JSONB,
    request_id UUID
);
```

**Columns**:
- `action` - Action performed (e.g., "create", "delete", "update")
- `entity_type` - Entity affected (e.g., "investigation", "artifact", "user")
- `entity_id` - Entity identifier (as text for flexibility)
- `details` - JSONB metadata (old values, new values, etc.)
- `request_id` - Request correlation ID

**Indexes**:
- `idx_audit_log_timestamp` - Sort by time
- `idx_audit_log_user` - Filter by user
- `idx_audit_log_investigation` - Filter by investigation
- `idx_audit_log_action` - Filter by action

#### deletion_log

Immutable record of deleted investigations.

```sql
CREATE TABLE deletion_log (
    deletion_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    investigation_id UUID NOT NULL,
    investigation_title TEXT NOT NULL,
    deleted_by_user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    artifact_count INTEGER,
    event_count INTEGER,
    node_count INTEGER,
    edge_count INTEGER,
    storage_bytes BIGINT
);
```

**Purpose**: Track deleted investigations for compliance and auditing.

**Indexes**:
- `idx_deletion_log_timestamp` - Sort by deletion time
- `idx_deletion_log_investigation` - Filter by investigation UUID

---

## Indexes

### Primary Indexes

All tables have primary key indexes (automatic).

### Secondary Indexes

- **B-tree indexes** - For exact matches and range queries (timestamps, IDs)
- **GIN indexes** - For JSONB and array queries (payload, tags)
- **Partial indexes** - For filtered queries (only `pending` jobs)

### Index Maintenance

```sql
-- Rebuild indexes (if fragmented)
REINDEX TABLE events;

-- Analyze table statistics (for query planner)
ANALYZE events;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

---

## Functions & Triggers

### update_updated_at_column()

Automatically updates `updated_at` timestamp on row modification.

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Applied to: graph_nodes, graph_edges, llm_provider_config
```

### enforce_single_active_llm_config()

Ensures only one active LLM config per user.

```sql
CREATE OR REPLACE FUNCTION enforce_single_active_llm_config()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_active = true THEN
        UPDATE llm_provider_config
        SET is_active = false
        WHERE user_id = NEW.user_id
          AND config_id != COALESCE(NEW.config_id, -1)
          AND is_active = true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Backup & Restore

### Backup Database

```bash
# Full database dump
docker compose exec db pg_dump -U postgres open_agent_inv > backup.sql

# Compressed backup
docker compose exec db pg_dump -U postgres open_agent_inv | gzip > backup.sql.gz

# Schema only (no data)
docker compose exec db pg_dump -U postgres --schema-only open_agent_inv > schema.sql

# Data only (no schema)
docker compose exec db pg_dump -U postgres --data-only open_agent_inv > data.sql
```

### Restore Database

```bash
# Restore from dump
docker compose exec -T db psql -U postgres open_agent_inv < backup.sql

# Restore from compressed dump
gunzip -c backup.sql.gz | docker compose exec -T db psql -U postgres open_agent_inv
```

### Automated Backups

Add to cron:

```bash
# Daily backup at 2 AM
0 2 * * * /usr/bin/docker compose -f /path/to/docker-compose.yml exec -T db pg_dump -U postgres open_agent_inv | gzip > /backups/open_agent_inv_$(date +\%Y\%m\%d).sql.gz
```

---

## Performance Tuning

### Materialized Views, Caching & Sampling

The system uses **materialized views**, **aggregate caches**, and **statistical sampling** to speed up expensive statistics queries.

**Why NOT Use Triggers?**

Database triggers on `events`, `timeline_entries`, and `embeddings` tables would be **extremely expensive**:
- Investigations can have **millions of events**
- Batch inserts would trigger refresh after every statement
- Parsing a single EVTX file (100k events) would trigger 100k refreshes
- Materialized view refresh takes 1-2 seconds (unacceptable overhead)

**Solution: Worker-Based Refresh**

Caches are refreshed by the workers at strategic points:
- ✅ After **ALL parsing jobs for an investigation** complete (not per-job)
- ✅ After **ALL embedding jobs for an investigation** complete (not per-job)
- ✅ Every **10 minutes** during periodic maintenance (worker 0 only)
- ✅ On **worker startup** (initial population)

**Why Batch Refreshes?**
- Uploading 10 artifacts creates 10 parsing jobs
- Refreshing after each job = 10 expensive refreshes
- Refreshing after ALL jobs = 1 refresh (10x less overhead)
- Cache refresh takes 1-2 seconds (acceptable when done once)

**Race Condition Prevention**:
- Workers use `SELECT FOR UPDATE` to lock investigation row when checking for completion
- Only the first worker to see "no remaining jobs" will flush the embedding pool
- Other workers check the `parsing_locked` flag - if already cleared, they skip flushing
- This prevents duplicate embedding jobs when multiple parsing jobs complete simultaneously

**Dedicated Embedding Worker**:
- Runs as separate process (`embedding-worker` service)
- Processes embedding jobs **in parallel** with parsing jobs
- Not blocked by parsing or agent jobs
- Ensures embeddings start generating immediately
- Configurable: `NUM_EMBEDDING_WORKERS` (default: 4)

This provides <10 minute staleness with **minimal overhead** during event insertion.

#### Statistical Sampling for GROUP BY Queries

**Why Sampling?**

Exact `COUNT(*)` and `GROUP BY` queries on large tables (millions of events/embeddings) are slow:
- `SELECT event_type, COUNT(*) FROM events GROUP BY event_type` → 5-10 seconds
- `SELECT owner_type, COUNT(*) FROM embeddings GROUP BY owner_type` → 2-5 seconds

**Solution: TABLESAMPLE**

PostgreSQL's `TABLESAMPLE SYSTEM(percent)` provides fast row estimates:
```sql
-- Exact count (slow)
SELECT event_type, COUNT(*) FROM events GROUP BY event_type;

-- Estimated count (fast)
WITH event_type_sample AS (
    SELECT 
        event_type,
        COUNT(*) as sample_count
    FROM events
    TABLESAMPLE SYSTEM(5)  -- Sample 5% of blocks
    GROUP BY event_type
)
SELECT 
    event_type,
    (sample_count * 20)::bigint as estimated_count  -- Extrapolate to 100%
FROM event_type_sample
ORDER BY estimated_count DESC;
```

**Performance Impact**:
- **Before**: 5-10 seconds for event type breakdown
- **After**: <200ms (25-50x faster)
- **Accuracy**: ±5-10% (acceptable for status dashboard)

**Sampling Rates**:
- `events` (millions of rows): 5% sample → 20x multiplier
- `embeddings` (hundreds of thousands): 10% sample → 10x multiplier
- `timeline_entries` (thousands): 10% sample → 10x multiplier
- `artifacts` (hundreds): 25% sample → 4x multiplier

**Trade-offs**:
- ✅ **Pros**: 25-50x faster, minimal overhead, no locks
- ⚠️ **Cons**: Estimates (not exact), may miss rare categories in small samples
- ✅ **When to Use**: Status dashboards, analytics, trends
- ❌ **When NOT to Use**: Financial reports, compliance audits, exact counts required

#### Investigation Statistics Materialized View

**Purpose**: Pre-computes expensive event/timeline embedding coverage calculations per investigation.

**Refresh Strategy**:

The cache is **automatically refreshed** by the worker:
- After every parsing job completes (updates event counts)
- After every embedding job completes (updates embedding coverage)
- Every 5 minutes during periodic maintenance
- On worker startup (initial cache population)

**Manual Refresh** (if needed):
```sql
-- Manual refresh (fast, allows concurrent reads)
SELECT refresh_investigation_stats();

-- Or via API endpoint
POST /api/v1/system/refresh-stats
```

**Performance Impact**:
- **Before**: 5-10 seconds for status modal (multiple LEFT JOINs on embeddings table + GROUP BY queries)
- **After**: <200ms (materialized view + sampling)
- **Staleness**: <5 minutes for totals, ±5-10% for breakdowns (acceptable trade-off for 25-50x performance gain)

#### System Stats Cache Table

**Purpose**: Stores pre-computed aggregate counts (total events, artifacts, jobs, etc.) to avoid expensive COUNT(*) queries.

**Refresh Strategy**:
```sql
-- Update all cached stats
SELECT update_system_stats_cache();
```

**Cached Statistics**:
- `total_events` - Total event count
- `events_with_embeddings` - Events with embeddings
- `total_timeline_entries` - Total timeline entries
- `timeline_with_embeddings` - Timeline entries with embeddings
- `total_embeddings` - Total embeddings
- `total_artifacts` - Total artifacts
- `total_artifact_bytes` - Total artifact storage
- `jobs_*_pending/running/completed/failed` - Job status counts

**Performance Impact**:
- **Before**: 2-3 seconds for aggregate counts (full table scans)
- **After**: <100ms (indexed lookups on small cache table)

#### Automatic Refresh (Implemented)

The worker automatically refreshes caches:

**After Parsing Jobs** (`api/worker/main.py`):
```python
# After parsing job completes
await db.execute(text("SELECT update_system_stats_cache()"))
await db.commit()
```

**After Embedding Jobs** (`api/worker/embedding_worker.py`):
```python
# After embedding job completes
await db.execute(text("SELECT refresh_investigation_stats()"))
await db.execute(text("SELECT update_system_stats_cache()"))
await db.commit()
```

**Periodic Refresh** (every 5 minutes):
```python
# During periodic maintenance in worker loop
await db.execute(text("SELECT refresh_investigation_stats()"))
await db.commit()
```

**Startup Initialization**:
```python
# On worker startup
await db.execute(text("SELECT refresh_investigation_stats()"))
await db.execute(text("SELECT update_system_stats_cache()"))
await db.commit()
```

### Query Optimization

```sql
-- Use EXPLAIN ANALYZE to understand query plans
EXPLAIN ANALYZE
SELECT * FROM events
WHERE investigation_id = '550e8400-e29b-41d4-a716-446655440000'
  AND event_type LIKE 'evtx_%'
ORDER BY event_ts DESC
LIMIT 100;

-- Look for:
-- - Index Scan (good) vs Seq Scan (bad for large tables)
-- - Bitmap Heap Scan (good for JSONB queries)
-- - High "Execution Time" (needs optimization)
```

### Table Partitioning

For large datasets, partition `events` table by `investigation_id`:

```sql
-- Create partitioned table (requires migration)
CREATE TABLE events_partitioned (
    LIKE events INCLUDING ALL
) PARTITION BY HASH (investigation_id);

-- Create partitions (16 partitions example)
CREATE TABLE events_p0 PARTITION OF events_partitioned FOR VALUES WITH (MODULUS 16, REMAINDER 0);
CREATE TABLE events_p1 PARTITION OF events_partitioned FOR VALUES WITH (MODULUS 16, REMAINDER 1);
-- ... repeat for p2-p15
```

### Connection Pooling

Configure PostgreSQL for high concurrency:

```ini
# postgresql.conf
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB
```

### Vacuum & Analyze

```sql
-- Manual vacuum (reclaim space)
VACUUM FULL events;

-- Auto-vacuum settings (postgresql.conf)
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 1min
```

---

## Monitoring

### Database Size

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size('open_agent_inv'));

-- Table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Active Connections

```sql
-- Current connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'open_agent_inv';

-- Connection details
SELECT pid, usename, application_name, state, query_start, query
FROM pg_stat_activity
WHERE datname = 'open_agent_inv';
```

### Slow Queries

```sql
-- Enable query logging (postgresql.conf)
log_min_duration_statement = 1000  # Log queries > 1 second

-- View slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

---

## Security

### User Permissions

```sql
-- Create read-only user
CREATE USER readonly WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE open_agent_inv TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;

-- Create application user (used by API/Worker)
CREATE USER app_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE open_agent_inv TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
```

### Encryption

- **Passwords**: Argon2id hashing (never plaintext)
- **API Keys**: Stored encrypted (pg_crypto extension)
- **Connection**: Use SSL for production (`sslmode=require`)

```bash
# Enable SSL in postgresql.conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'
```

---

## Troubleshooting

### Connection Refused

```bash
# Check if PostgreSQL is running
docker compose ps db

# Check logs
docker compose logs db

# Test connection
docker compose exec db psql -U postgres -d open_agent_inv -c "SELECT 1;"
```

### Disk Space Issues

```bash
# Check disk usage
docker compose exec db df -h

# Find large tables
docker compose exec db psql -U postgres -d open_agent_inv -c "
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 5;
"

# Vacuum to reclaim space
docker compose exec db psql -U postgres -d open_agent_inv -c "VACUUM FULL;"
```

### Corrupted Indexes

```bash
# Rebuild all indexes
docker compose exec db psql -U postgres -d open_agent_inv -c "REINDEX DATABASE open_agent_inv;"
```

---

## Further Reading

- [API Documentation](../api/README.md) - Backend API using this database
- [Worker Documentation](../api/worker/README.md) - Job processing
- [PostgreSQL Documentation](https://www.postgresql.org/docs/15/) - Official docs
- [JSONB Performance](https://www.postgresql.org/docs/15/datatype-json.html) - JSONB best practices

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../README.md).
