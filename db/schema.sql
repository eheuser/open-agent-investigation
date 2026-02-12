-- Open Agent Investigation Database Schema
-- PostgreSQL 15+
-- GPL v3 License

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
-- Extension for trigram-based text search (supports ILIKE with indexes)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Users table (§4.1)
CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role SMALLINT NOT NULL DEFAULT 0,  -- 0=regular, 1=admin
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_role CHECK (role IN (0, 1))
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

-- Investigations table (§4.2)
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    owner_user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    parsing_locked BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investigations_owner ON investigations(owner_user_id);
CREATE INDEX idx_investigations_created ON investigations(created_at DESC);

-- Artifacts table (§4.3)
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    sha256 BYTEA NOT NULL CHECK (length(sha256) = 32),
    filename TEXT NOT NULL,
    classification SMALLINT NOT NULL,  -- 0=SYSTEM_HIVE, 1=LOG_FILE, 2=BINARY, 3=ARCHIVE, 4=UNKNOWN
    size_bytes BIGINT NOT NULL DEFAULT 0,  -- Original file size (tracked at upload time)
    blob BYTEA NOT NULL,
    upload_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_classification CHECK (classification BETWEEN 0 AND 4)
);

CREATE INDEX idx_artifacts_investigation ON artifacts(investigation_id);
CREATE INDEX idx_artifacts_sha256 ON artifacts(sha256);
CREATE INDEX idx_artifacts_upload_ts ON artifacts(upload_ts DESC);
-- Index for filename search (ILIKE queries) - supports case-insensitive search
CREATE INDEX idx_artifacts_filename_trgm ON artifacts USING gin (filename gin_trgm_ops);
-- Index for classification grouping
CREATE INDEX idx_artifacts_classification ON artifacts(classification);

-- MCP Servers table (§4.4)
CREATE TABLE IF NOT EXISTS mcp_servers (
    server_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    auth_token TEXT,
    allowed_agents TEXT[] DEFAULT '{}',
    owner_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mcp_servers_owner ON mcp_servers(owner_user_id);
CREATE INDEX idx_mcp_servers_name ON mcp_servers(name);

-- LLM Provider Configuration table
CREATE TABLE IF NOT EXISTS llm_provider_config (
    config_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider_name TEXT NOT NULL DEFAULT 'openai',
    api_endpoint TEXT NOT NULL,
    api_key TEXT,
    model_name TEXT DEFAULT 'gpt-4',
    max_context_length INTEGER NOT NULL DEFAULT 8192,
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.70,
    top_p NUMERIC(4,3),
    top_k INTEGER,
    min_p NUMERIC(4,3),
    timeout INTEGER NOT NULL DEFAULT 300,
    is_active BOOLEAN NOT NULL DEFAULT true,
    embedding_provider TEXT,
    embedding_api_url TEXT,
    embedding_api_key TEXT,
    embedding_model_name TEXT,
    embedding_max_context_length INTEGER DEFAULT 8192,
    reranker_model_name TEXT,
    reranker_max_context_length INTEGER DEFAULT 8192,
    allow_concurrent_llm_calls BOOLEAN DEFAULT false,
    allow_concurrent_embedding_calls BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_temperature CHECK (temperature >= 0.0 AND temperature <= 2.0),
    CONSTRAINT valid_context_length CHECK (max_context_length > 0 AND max_context_length <= 1000000),
    CONSTRAINT valid_top_p CHECK (top_p IS NULL OR (top_p >= 0.0 AND top_p <= 1.0)),
    CONSTRAINT valid_top_k CHECK (top_k IS NULL OR top_k > 0),
    CONSTRAINT valid_min_p CHECK (min_p IS NULL OR (min_p >= 0.0 AND min_p <= 1.0)),
    CONSTRAINT valid_timeout CHECK (timeout > 0 AND timeout <= 3600)
);

CREATE INDEX idx_llm_config_user ON llm_provider_config(user_id);
CREATE INDEX idx_llm_config_active ON llm_provider_config(user_id, is_active) WHERE is_active = true;



-- Chat messages table (conversation history in OpenAI format)
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- OpenAI message format fields
    role VARCHAR(20) NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT,  -- Nullable for tool_calls
    name VARCHAR(100),  -- Optional name for function/tool messages
    tool_calls JSONB,  -- Tool calls array (for assistant messages)
    tool_call_id VARCHAR(100),  -- Tool call ID (for tool response messages)
    
    -- Refactored fields for single source of truth architecture
    message_type VARCHAR(50),  -- question, assistant_answer, agent_chat, tool_execution, summary, error, system
    parent_message_id BIGINT REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    
        -- Metadata and control fields
    metadata JSONB DEFAULT '{}'::jsonb,
    include_in_llm_context BOOLEAN NOT NULL DEFAULT true,
    visible_in_ui BOOLEAN NOT NULL DEFAULT true,
    deleted_at TIMESTAMPTZ,  -- Soft delete timestamp (tombstone)
    embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_investigation ON chat_messages(investigation_id, created_at DESC);
CREATE INDEX idx_chat_messages_llm_context ON chat_messages(investigation_id, include_in_llm_context, created_at DESC);
CREATE INDEX idx_chat_messages_user ON chat_messages(user_id, created_at DESC);
CREATE INDEX idx_chat_messages_parent ON chat_messages(parent_message_id) WHERE parent_message_id IS NOT NULL;
CREATE INDEX idx_chat_messages_type ON chat_messages(investigation_id, message_type) WHERE message_type IS NOT NULL;
CREATE INDEX idx_chat_messages_visible ON chat_messages(investigation_id, visible_in_ui, deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_chat_messages_embedding ON chat_messages(embedding_id) WHERE embedding_id IS NOT NULL;

-- Tool executions table (explicit tool call tracking)
CREATE TABLE IF NOT EXISTS tool_executions (
    execution_id BIGSERIAL PRIMARY KEY,
    chat_message_id BIGINT NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    display_name TEXT,
    arguments JSONB DEFAULT '{}'::jsonb,
    result JSONB,
    result_summary TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'executing' CHECK (status IN ('executing', 'completed', 'failed')),
    execution_number INTEGER,
    max_tools INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_tool_exec_message ON tool_executions(chat_message_id);
CREATE INDEX idx_tool_exec_message_started ON tool_executions(chat_message_id, started_at ASC);  -- For ordering tool execution history
CREATE INDEX idx_tool_exec_status ON tool_executions(status) WHERE status = 'executing';

-- ============================================================================
-- JOB QUEUE TABLES
-- ============================================================================

-- Job status enum type
DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Parsing jobs queue (§4.5)
-- Set fillfactor to 90 for frequently updated job status transitions
CREATE TABLE IF NOT EXISTS jobs_parsing (
    job_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    artifact_id BIGINT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    status job_status NOT NULL DEFAULT 'pending',
    worker_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
        error_message TEXT
) WITH (fillfactor = 90);

CREATE INDEX idx_jobs_parsing_status ON jobs_parsing(status) WHERE status = 'pending';
CREATE INDEX idx_jobs_parsing_investigation ON jobs_parsing(investigation_id);
CREATE INDEX idx_jobs_parsing_created ON jobs_parsing(created_at DESC);

-- Agent jobs queue (§4.6)
-- Set fillfactor to 90 for frequently updated job status transitions
CREATE TABLE IF NOT EXISTS jobs_agents (
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
    error_message TEXT,
        metadata JSONB DEFAULT '{}'
) WITH (fillfactor = 90);

CREATE INDEX idx_jobs_agents_status ON jobs_agents(status) WHERE status = 'pending';
CREATE INDEX idx_jobs_agents_investigation ON jobs_agents(investigation_id);
CREATE INDEX idx_jobs_agents_user ON jobs_agents(user_id);
CREATE INDEX idx_jobs_agents_created ON jobs_agents(created_at DESC);
CREATE INDEX idx_jobs_agents_policy ON jobs_agents(policy_id);

-- Embedding jobs queue (§4.7)
-- Background queue for generating embeddings from parsed events
-- Set fillfactor to 90 for frequently updated job status transitions
CREATE TABLE IF NOT EXISTS jobs_embedding (
    job_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_ids BIGINT[] NOT NULL,  -- Batch of event IDs to embed
    status job_status NOT NULL DEFAULT 'pending',
    worker_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    events_processed INTEGER DEFAULT 0,  -- Track progress
    CONSTRAINT event_ids_not_empty CHECK (array_length(event_ids, 1) > 0)
) WITH (fillfactor = 90);

CREATE INDEX idx_jobs_embedding_status ON jobs_embedding(status) WHERE status = 'pending';
CREATE INDEX idx_jobs_embedding_investigation ON jobs_embedding(investigation_id, status);
CREATE INDEX idx_jobs_embedding_user ON jobs_embedding(user_id);
CREATE INDEX idx_jobs_embedding_created ON jobs_embedding(created_at DESC);

-- Investigation choices table (agent-suggested next steps)
CREATE TABLE IF NOT EXISTS investigation_choices (
    choice_id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs_agents(job_id) ON DELETE CASCADE,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    
    -- Choice metadata
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    rationale TEXT NOT NULL,
    
    -- Execution parameters
    suggested_query TEXT NOT NULL,
    suggested_effort TEXT NOT NULL DEFAULT 'medium' CHECK (suggested_effort IN ('low', 'medium', 'high')),
    tool_suggestions JSONB,
    
    -- Display ordering
    display_order INTEGER NOT NULL DEFAULT 0,
    
    -- Selection tracking
    selected BOOLEAN NOT NULL DEFAULT false,
    selected_at TIMESTAMPTZ,
    selected_job_id BIGINT REFERENCES jobs_agents(job_id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investigation_choices_job ON investigation_choices(job_id);
CREATE INDEX idx_investigation_choices_investigation ON investigation_choices(investigation_id);
CREATE INDEX idx_investigation_choices_selected ON investigation_choices(selected, selected_at);

-- ============================================================================
-- UNIFIED INVESTIGATION DATA TABLES
-- ============================================================================

-- Events table (unified across all investigations)
CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    event_ts TIMESTAMPTZ NOT NULL,
    artifact_id BIGINT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_investigation ON events(investigation_id, event_ts DESC);
CREATE INDEX idx_events_type ON events(investigation_id, event_type);
CREATE INDEX idx_events_type_ts ON events(investigation_id, event_type, event_ts DESC);  -- For efficient field sampling
CREATE INDEX idx_events_inv_type_ts ON events(investigation_id, event_type, event_ts DESC);  -- Composite for event_type queries with time ordering
CREATE INDEX idx_events_artifact ON events(artifact_id);
CREATE INDEX idx_events_payload ON events USING GIN(payload);

-- Full-text search index for BM25 ranking (Feature 1: Hybrid Search)
CREATE INDEX IF NOT EXISTS idx_events_payload_fts ON events USING GIN (to_tsvector('english', payload::text));

-- Timeline entries table (unified across all investigations)
CREATE TABLE IF NOT EXISTS timeline_entries (
    entry_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    event_id BIGINT REFERENCES events(event_id) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('event', 'finding', 'note', 'observation')),
    title TEXT NOT NULL,
    description TEXT,
    data JSONB DEFAULT '{}'::jsonb,
        tags TEXT[] DEFAULT '{}'::TEXT[],
    created_by_user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_visible BOOLEAN NOT NULL DEFAULT true
    -- NOTE: UNIQUE constraint removed - see partial unique index below to handle NULLs properly
);

CREATE INDEX idx_timeline_investigation ON timeline_entries(investigation_id, timestamp DESC);
CREATE INDEX idx_timeline_type ON timeline_entries(investigation_id, entry_type);
-- Index for entry_type grouping (used in status queries)
CREATE INDEX idx_timeline_entry_type ON timeline_entries(entry_type);
CREATE INDEX idx_timeline_event ON timeline_entries(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX idx_timeline_event_visible ON timeline_entries(event_id, is_visible, timestamp DESC) WHERE event_id IS NOT NULL;  -- For efficient field sampling with JOIN
CREATE INDEX idx_timeline_tags ON timeline_entries USING GIN(tags);
CREATE INDEX idx_timeline_data ON timeline_entries USING GIN(data);
CREATE INDEX idx_timeline_created ON timeline_entries(investigation_id, created_at DESC);
CREATE INDEX idx_timeline_visible ON timeline_entries(investigation_id, is_visible) WHERE is_visible = true;
CREATE INDEX idx_timeline_entries_embedding ON timeline_entries(embedding_id) WHERE embedding_id IS NOT NULL;

-- Unique index to enforce uniqueness on (investigation_id, event_id)
-- PostgreSQL treats NULL as distinct, so multiple rows with NULL event_id are allowed
CREATE UNIQUE INDEX IF NOT EXISTS uq_timeline_investigation_event 
  ON timeline_entries(investigation_id, event_id);

-- Reports table (generated investigation reports)
CREATE TABLE IF NOT EXISTS reports (
    report_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    markdown_content TEXT NOT NULL,
    user_prompt TEXT,
    artifacts_count INTEGER NOT NULL DEFAULT 0,
    timeline_entries_count INTEGER NOT NULL DEFAULT 0,
    event_types_count INTEGER NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reports_investigation ON reports(investigation_id, generated_at DESC);
CREATE INDEX idx_reports_user ON reports(user_id, generated_at DESC);

-- Timeline notes table (user annotations on timeline entries)
CREATE TABLE IF NOT EXISTS timeline_notes (
    note_id BIGSERIAL PRIMARY KEY,
    entry_id BIGINT NOT NULL REFERENCES timeline_entries(entry_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_timeline_notes_entry ON timeline_notes(entry_id, created_at DESC);
CREATE INDEX idx_timeline_notes_user ON timeline_notes(user_id, created_at DESC);

-- ============================================================================
-- CHAT LOG SUMMARIES TABLE
-- ============================================================================

-- Chat log summaries table (token-efficient context management)
-- Stores LLM-generated summaries of chat history for context compaction
CREATE TABLE IF NOT EXISTS chat_log_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    job_id BIGINT REFERENCES jobs_agents(job_id) ON DELETE CASCADE,
    iteration_number INTEGER NOT NULL,
    
    -- Original chat log metadata
    messages_start_idx INTEGER NOT NULL,
    messages_end_idx INTEGER NOT NULL,
    original_message_count INTEGER NOT NULL,
    original_token_count INTEGER NOT NULL,
    
    -- Summary content
    summary_text TEXT NOT NULL,
    summary_token_count INTEGER NOT NULL,
    
    -- Preserved data
    event_ids_discovered TEXT[],  -- Event IDs mentioned in summarized messages
    tools_executed TEXT[],  -- Tools called in summarized messages
    key_findings TEXT[],  -- Important observations extracted
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_summary_investigation_iteration UNIQUE (investigation_id, job_id, iteration_number)
);

CREATE INDEX idx_chat_summaries_investigation ON chat_log_summaries(investigation_id, iteration_number DESC);
CREATE INDEX idx_chat_summaries_job ON chat_log_summaries(job_id) WHERE job_id IS NOT NULL;

-- ============================================================================
-- RAG & EMBEDDING TABLES
-- ============================================================================

-- Embeddings table (polymorphic vector store)
-- Supports flexible vector dimensions for different embedding models (768, 1024, 1536, etc.)
CREATE TABLE IF NOT EXISTS embeddings (
    id BIGSERIAL PRIMARY KEY,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('chat', 'timeline', 'note', 'tool')),
    owner_id BIGINT NOT NULL,
    model_name TEXT NOT NULL,
    vector VECTOR NOT NULL,  -- No dimension constraint - supports any embedding model
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_embeddings_owner ON embeddings(owner_type, owner_id);
-- Index for model_name grouping (used in status queries)
CREATE INDEX idx_embeddings_model ON embeddings(model_name);
-- Composite index for tool-type embeddings (optimizes event embedding coverage queries)
CREATE INDEX idx_embeddings_tool_owner ON embeddings(owner_type, owner_id) WHERE owner_type = 'tool';
-- Note: Vector indexes are NOT created for large embedding models (>2048 dimensions)
-- Models like qwen3-embedding-8b (8192 dims) exceed PostgreSQL's 8KB index page limit
-- Sequential scans are acceptable for <10k embeddings and avoid index maintenance overhead
-- For smaller models (<= 1536 dims), you can manually create an HNSW index:
-- CREATE INDEX idx_embeddings_vector_hnsw ON embeddings USING hnsw (vector vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Investigation notes table (free-form notes)
CREATE TABLE IF NOT EXISTS investigation_notes (
    note_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investigation_notes_investigation ON investigation_notes(investigation_id, created_at DESC);
CREATE INDEX idx_investigation_notes_user ON investigation_notes(user_id, created_at DESC);
CREATE INDEX idx_investigation_notes_embedding ON investigation_notes(embedding_id) WHERE embedding_id IS NOT NULL;

-- Tool results table (persisted tool execution results for RAG)
CREATE TABLE IF NOT EXISTS tool_results (
    result_id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs_agents(job_id) ON DELETE CASCADE,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    payload JSONB NOT NULL,
    embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tool_results_job ON tool_results(job_id);
CREATE INDEX idx_tool_results_investigation ON tool_results(investigation_id, created_at DESC);
CREATE INDEX idx_tool_results_embedding ON tool_results(embedding_id) WHERE embedding_id IS NOT NULL;

-- Filter configuration table (ingestion filters)
CREATE TABLE IF NOT EXISTS filter_config (
    config_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID REFERENCES investigations(investigation_id) ON DELETE CASCADE,  -- NULL = global
    content JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_filter_config_investigation ON filter_config(investigation_id);
CREATE INDEX idx_filter_config_updated ON filter_config(updated_at DESC);



-- ============================================================================
-- PLAYBOOKS TABLES
-- ============================================================================

-- User-created playbooks table
CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) > 0),
    description TEXT NOT NULL CHECK (length(description) > 0),
    playbook TEXT NOT NULL CHECK (length(playbook) > 0),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT playbook_name_not_empty CHECK (length(name) > 0),
    CONSTRAINT playbook_description_not_empty CHECK (length(description) > 0),
    CONSTRAINT playbook_content_not_empty CHECK (length(playbook) > 0)
);

CREATE INDEX idx_playbooks_user ON playbooks(user_id);
CREATE INDEX idx_playbooks_name ON playbooks(name);
CREATE INDEX idx_playbooks_enabled ON playbooks(is_enabled) WHERE is_enabled = true;

-- Investigation-playbook relationship table
CREATE TABLE IF NOT EXISTS investigation_playbooks (
    id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    playbook_id BIGINT NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_investigation_playbook UNIQUE (investigation_id, playbook_id)
);

CREATE INDEX idx_investigation_playbooks_investigation ON investigation_playbooks(investigation_id);
CREATE INDEX idx_investigation_playbooks_playbook ON investigation_playbooks(playbook_id);
CREATE INDEX idx_investigation_playbooks_enabled ON investigation_playbooks(investigation_id, is_enabled) WHERE is_enabled = true;

-- ============================================================================
-- AUDIT & DELETION LOGS
-- ============================================================================

-- Audit log (immutable)
CREATE TABLE IF NOT EXISTS audit_log (
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

CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_investigation ON audit_log(investigation_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);

-- Deletion log (immutable)
CREATE TABLE IF NOT EXISTS deletion_log (
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

CREATE INDEX idx_deletion_log_timestamp ON deletion_log(timestamp DESC);
CREATE INDEX idx_deletion_log_investigation ON deletion_log(investigation_id);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to ensure only one active LLM config per user
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

-- Triggers for llm_provider_config (must be after function definitions)
CREATE TRIGGER update_llm_config_updated_at
    BEFORE UPDATE ON llm_provider_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER enforce_single_active_config
    BEFORE INSERT OR UPDATE ON llm_provider_config
    FOR EACH ROW
    WHEN (NEW.is_active = true)
    EXECUTE FUNCTION enforce_single_active_llm_config();

-- Triggers for timeline tables (must be after function definitions)
CREATE TRIGGER update_timeline_entries_updated_at
    BEFORE UPDATE ON timeline_entries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_timeline_notes_updated_at
    BEFORE UPDATE ON timeline_notes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Triggers for RAG tables
CREATE TRIGGER update_investigation_notes_updated_at
    BEFORE UPDATE ON investigation_notes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_filter_config_updated_at
    BEFORE UPDATE ON filter_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger to update updated_at timestamp on playbooks
CREATE TRIGGER update_playbooks_updated_at
    BEFORE UPDATE ON playbooks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- CACHE REFRESH STRATEGY
-- ============================================================================
-- NOTE: Cache refresh is handled by the worker, NOT by triggers
-- Triggers would be too expensive for millions of events
-- 
-- Refresh happens:
-- 1. On worker startup (initial population)
-- 2. After each parsing job completes (system_stats_cache only)
-- 3. After each embedding job completes (both caches)
-- 4. Every 5 minutes during periodic maintenance (investigation_stats_mv)
--
-- This provides <5 minute staleness while avoiding trigger overhead

-- Analysis results cache table (for analysis modules like Autoruns, Execution Evidence, etc.)
CREATE TABLE IF NOT EXISTS analysis_results (
    result_id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL,  -- 'autoruns', 'execution_evidence', 'browsed_urls', 'logons'
    analysis_version TEXT NOT NULL,  -- Version of the analyzer (e.g., '1.0')
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Filter parameters used
    results JSONB NOT NULL,  -- Cached analysis results
    entry_count INTEGER,  -- Number of entries in results
    categories_analyzed TEXT[],  -- Categories/filters that were analyzed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- NULL = never expires, or timestamp for cache expiration
    CONSTRAINT uq_analysis_cache_key UNIQUE (investigation_id, analysis_type, parameters)
);

CREATE INDEX idx_analysis_results_investigation ON analysis_results(investigation_id, analysis_type);
CREATE INDEX idx_analysis_results_expires ON analysis_results(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- PERFORMANCE OPTIMIZATION: MATERIALIZED VIEWS & AGGREGATES
-- ============================================================================

-- Materialized view for investigation statistics (refreshed on-demand)
-- Pre-computes expensive event/timeline embedding coverage calculations
CREATE MATERIALIZED VIEW IF NOT EXISTS investigation_stats_mv AS
SELECT 
    i.investigation_id,
    i.title,
    u.username as owner,
    i.created_at,
    COUNT(DISTINCT e.event_id) AS total_events,
    COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NOT NULL) AS events_with_embeddings,
    COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NULL) AS events_without_embeddings,
    ROUND(
        100.0 * COUNT(DISTINCT e.event_id) FILTER (WHERE emb_e.id IS NOT NULL) / 
        NULLIF(COUNT(DISTINCT e.event_id), 0), 
        2
    ) AS event_embedding_coverage_percent,
    COUNT(DISTINCT te.entry_id) AS total_timeline_entries,
    COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NOT NULL) AS timeline_with_embeddings,
    COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NULL) AS timeline_without_embeddings,
    ROUND(
        100.0 * COUNT(DISTINCT te.entry_id) FILTER (WHERE te.embedding_id IS NOT NULL) / 
        NULLIF(COUNT(DISTINCT te.entry_id), 0), 
        2
    ) AS timeline_embedding_coverage_percent
FROM investigations i
LEFT JOIN users u ON u.user_id = i.owner_user_id
LEFT JOIN events e ON e.investigation_id = i.investigation_id
LEFT JOIN embeddings emb_e ON emb_e.owner_type = 'tool' AND emb_e.owner_id = e.event_id
LEFT JOIN timeline_entries te ON te.investigation_id = i.investigation_id
GROUP BY i.investigation_id, i.title, u.username, i.created_at;

-- Index on materialized view for fast lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_stats_mv_id ON investigation_stats_mv(investigation_id);
CREATE INDEX IF NOT EXISTS idx_investigation_stats_mv_created ON investigation_stats_mv(created_at DESC);

-- Function to refresh investigation stats (call after parsing/embedding jobs)
CREATE OR REPLACE FUNCTION refresh_investigation_stats()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY investigation_stats_mv;
END;
$$ LANGUAGE plpgsql;

-- System-wide aggregate statistics table (updated via trigger)
-- Avoids expensive COUNT(*) queries on large tables
CREATE TABLE IF NOT EXISTS system_stats_cache (
    stat_key TEXT PRIMARY KEY,
    stat_value BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Initialize cache with zero values
INSERT INTO system_stats_cache (stat_key, stat_value) VALUES
    ('total_events', 0),
    ('events_with_embeddings', 0),
    ('total_timeline_entries', 0),
    ('timeline_with_embeddings', 0),
    ('total_embeddings', 0),
    ('total_artifacts', 0),
    ('total_artifact_bytes', 0),
    ('jobs_parsing_pending', 0),
    ('jobs_parsing_running', 0),
    ('jobs_parsing_completed', 0),
    ('jobs_parsing_failed', 0),
    ('jobs_agents_pending', 0),
    ('jobs_agents_running', 0),
    ('jobs_agents_completed', 0),
    ('jobs_agents_failed', 0),
    ('jobs_embedding_pending', 0),
    ('jobs_embedding_running', 0),
    ('jobs_embedding_completed', 0),
    ('jobs_embedding_failed', 0)
ON CONFLICT (stat_key) DO NOTHING;

-- Function to update system stats cache (called periodically or on-demand)
CREATE OR REPLACE FUNCTION update_system_stats_cache()
RETURNS void AS $$
BEGIN
    -- Update event counts
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM events), updated_at = NOW() WHERE stat_key = 'total_events';
    UPDATE system_stats_cache SET stat_value = (
        SELECT COUNT(DISTINCT e.event_id) 
        FROM events e 
        INNER JOIN embeddings emb ON emb.owner_type = 'tool' AND emb.owner_id = e.event_id
    ), updated_at = NOW() WHERE stat_key = 'events_with_embeddings';
    
    -- Update timeline counts
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM timeline_entries), updated_at = NOW() WHERE stat_key = 'total_timeline_entries';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM timeline_entries WHERE embedding_id IS NOT NULL), updated_at = NOW() WHERE stat_key = 'timeline_with_embeddings';
    
    -- Update embedding counts
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM embeddings), updated_at = NOW() WHERE stat_key = 'total_embeddings';
    
        -- Update artifact counts
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM artifacts), updated_at = NOW() WHERE stat_key = 'total_artifacts';
    UPDATE system_stats_cache SET stat_value = (SELECT COALESCE(SUM(size_bytes), 0) FROM artifacts), updated_at = NOW() WHERE stat_key = 'total_artifact_bytes';
    
    -- Update job counts
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_parsing WHERE status = 'pending'), updated_at = NOW() WHERE stat_key = 'jobs_parsing_pending';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_parsing WHERE status = 'running'), updated_at = NOW() WHERE stat_key = 'jobs_parsing_running';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_parsing WHERE status = 'completed'), updated_at = NOW() WHERE stat_key = 'jobs_parsing_completed';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_parsing WHERE status = 'failed'), updated_at = NOW() WHERE stat_key = 'jobs_parsing_failed';
    
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_agents WHERE status = 'pending'), updated_at = NOW() WHERE stat_key = 'jobs_agents_pending';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_agents WHERE status = 'running'), updated_at = NOW() WHERE stat_key = 'jobs_agents_running';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_agents WHERE status = 'completed'), updated_at = NOW() WHERE stat_key = 'jobs_agents_completed';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_agents WHERE status = 'failed'), updated_at = NOW() WHERE stat_key = 'jobs_agents_failed';
    
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_embedding WHERE status = 'pending'), updated_at = NOW() WHERE stat_key = 'jobs_embedding_pending';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_embedding WHERE status = 'running'), updated_at = NOW() WHERE stat_key = 'jobs_embedding_running';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_embedding WHERE status = 'completed'), updated_at = NOW() WHERE stat_key = 'jobs_embedding_completed';
    UPDATE system_stats_cache SET stat_value = (SELECT COUNT(*) FROM jobs_embedding WHERE status = 'failed'), updated_at = NOW() WHERE stat_key = 'jobs_embedding_failed';
END;
$$ LANGUAGE plpgsql;

-- Composite indexes for faster aggregation queries
CREATE INDEX IF NOT EXISTS idx_events_investigation_id_only ON events(investigation_id);
CREATE INDEX IF NOT EXISTS idx_timeline_entries_investigation_id_only ON timeline_entries(investigation_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_tool_type_only ON embeddings(owner_type) WHERE owner_type = 'tool';

-- Index for job status aggregations (covers all status values)
CREATE INDEX IF NOT EXISTS idx_jobs_parsing_status_all ON jobs_parsing(status);
CREATE INDEX IF NOT EXISTS idx_jobs_agents_status_all ON jobs_agents(status);
CREATE INDEX IF NOT EXISTS idx_jobs_embedding_status_all ON jobs_embedding(status);

-- ============================================================================
-- DEFAULT DATA
-- ============================================================================

-- Create default admin user (password: admin123 - CHANGE IN PRODUCTION!)
-- Password hash is argon2 hash of "admin123"
INSERT INTO users (username, password_hash, role)
VALUES ('admin', '$argon2id$v=19$m=65536,t=3,p=4$g1BKCYEwJsS4l5LyPickJA$8ZGtyRXgCPnXyShzNjjZ1ByH2Qgyp2nLRTInMVWMUZc', 1)
ON CONFLICT (username) DO NOTHING;