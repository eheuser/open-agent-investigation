-- Open Agent Investigation Database Schema
-- PostgreSQL 15+
-- GPL v3 License

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

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
    blob BYTEA NOT NULL,
    upload_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_classification CHECK (classification BETWEEN 0 AND 4)
);

CREATE INDEX idx_artifacts_investigation ON artifacts(investigation_id);
CREATE INDEX idx_artifacts_sha256 ON artifacts(sha256);
CREATE INDEX idx_artifacts_upload_ts ON artifacts(upload_ts DESC);

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

-- Add embedding provider configuration columns
ALTER TABLE llm_provider_config ADD COLUMN IF NOT EXISTS embedding_provider TEXT;
ALTER TABLE llm_provider_config ADD COLUMN IF NOT EXISTS embedding_api_url TEXT;
ALTER TABLE llm_provider_config ADD COLUMN IF NOT EXISTS embedding_api_key TEXT;
ALTER TABLE llm_provider_config ADD COLUMN IF NOT EXISTS embedding_model_name TEXT;

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_investigation ON chat_messages(investigation_id, created_at DESC);
CREATE INDEX idx_chat_messages_llm_context ON chat_messages(investigation_id, include_in_llm_context, created_at DESC);
CREATE INDEX idx_chat_messages_user ON chat_messages(user_id, created_at DESC);
CREATE INDEX idx_chat_messages_parent ON chat_messages(parent_message_id) WHERE parent_message_id IS NOT NULL;
CREATE INDEX idx_chat_messages_type ON chat_messages(investigation_id, message_type) WHERE message_type IS NOT NULL;
CREATE INDEX idx_chat_messages_visible ON chat_messages(investigation_id, visible_in_ui, deleted_at) WHERE deleted_at IS NULL;

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
);

CREATE INDEX idx_jobs_parsing_status ON jobs_parsing(status) WHERE status = 'pending';
CREATE INDEX idx_jobs_parsing_investigation ON jobs_parsing(investigation_id);
CREATE INDEX idx_jobs_parsing_created ON jobs_parsing(created_at DESC);

-- Agent jobs queue (§4.6)
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
);

CREATE INDEX idx_jobs_agents_status ON jobs_agents(status) WHERE status = 'pending';
CREATE INDEX idx_jobs_agents_investigation ON jobs_agents(investigation_id);
CREATE INDEX idx_jobs_agents_user ON jobs_agents(user_id);
CREATE INDEX idx_jobs_agents_created ON jobs_agents(created_at DESC);
CREATE INDEX idx_jobs_agents_policy ON jobs_agents(policy_id);

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
CREATE INDEX idx_events_artifact ON events(artifact_id);
CREATE INDEX idx_events_payload ON events USING GIN(payload);

-- Full-text search index for BM25 ranking (Feature 1: Hybrid Search)
CREATE INDEX IF NOT EXISTS idx_events_payload_fts ON events USING GIN (to_tsvector('english', payload::text));
COMMENT ON INDEX idx_events_payload_fts IS 'Full-text search index for BM25 ranking in hybrid search. Enables ts_rank_cd queries.';

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_visible BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT uq_timeline_investigation_event UNIQUE (investigation_id, event_id)
);

CREATE INDEX idx_timeline_investigation ON timeline_entries(investigation_id, timestamp DESC);
CREATE INDEX idx_timeline_type ON timeline_entries(investigation_id, entry_type);
CREATE INDEX idx_timeline_event ON timeline_entries(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX idx_timeline_tags ON timeline_entries USING GIN(tags);
CREATE INDEX idx_timeline_data ON timeline_entries USING GIN(data);
CREATE INDEX idx_timeline_created ON timeline_entries(investigation_id, created_at DESC);
CREATE INDEX idx_timeline_visible ON timeline_entries(investigation_id, is_visible) WHERE is_visible = true;

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

COMMENT ON TABLE chat_log_summaries IS 'LLM-generated summaries of chat history for token-efficient context management. Enables 40%+ token reduction while preserving critical information.';
COMMENT ON COLUMN chat_log_summaries.messages_start_idx IS 'Starting index in chat_log array that was summarized';
COMMENT ON COLUMN chat_log_summaries.messages_end_idx IS 'Ending index in chat_log array that was summarized';
COMMENT ON COLUMN chat_log_summaries.summary_text IS 'Compact LLM-generated summary preserving key findings, event IDs, and decisions';
COMMENT ON COLUMN chat_log_summaries.event_ids_discovered IS 'Array of event IDs mentioned in the summarized portion';
COMMENT ON COLUMN chat_log_summaries.tools_executed IS 'Array of tool names executed in the summarized portion';

-- ============================================================================
-- FIELD DICTIONARY TABLE
-- ============================================================================

-- Field dictionary table (permanent storage of JSONB field descriptions)
-- Stores LLM-generated descriptions for forensic JSONB fields, organized by event type
CREATE TABLE IF NOT EXISTS field_dictionary (
    field_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    description TEXT NOT NULL,
    sample_values TEXT[],  -- Example values to help with context
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_field_dict_event_field UNIQUE (event_type, field_name)
);

CREATE INDEX idx_field_dict_event_type ON field_dictionary(event_type);
CREATE INDEX idx_field_dict_field_name ON field_dictionary(field_name);
CREATE INDEX idx_field_dict_updated ON field_dictionary(updated_at DESC);

COMMENT ON TABLE field_dictionary IS 'Permanent storage of JSONB field descriptions for all event types. LLM-generated descriptions help agents understand available fields.';
COMMENT ON COLUMN field_dictionary.event_type IS 'Event type this field belongs to (e.g., evtx_security_4624, mft_entry)';
COMMENT ON COLUMN field_dictionary.field_name IS 'JSONB field name (e.g., TargetUserName, system.Computer)';
COMMENT ON COLUMN field_dictionary.description IS 'Brief forensic description of what this field represents (5-10 words)';
COMMENT ON COLUMN field_dictionary.sample_values IS 'Example values from actual events to provide context';

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
-- Note: IVFFLAT index will be created manually after first embeddings are inserted
-- with the correct dimension for your model (e.g., 768, 1024, or 1536)
-- Example: CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);

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

-- Add embedding_id columns to existing tables
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL;
ALTER TABLE timeline_entries ADD COLUMN IF NOT EXISTS embedding_id BIGINT REFERENCES embeddings(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_embedding ON chat_messages(embedding_id) WHERE embedding_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_timeline_entries_embedding ON timeline_entries(embedding_id) WHERE embedding_id IS NOT NULL;

-- ============================================================================
-- MIGRATION TRACKING
-- ============================================================================

-- Schema migrations tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by TEXT DEFAULT CURRENT_USER,
    checksum TEXT
);

CREATE INDEX idx_schema_migrations_applied ON schema_migrations(applied_at DESC);

-- Record initial schema as version 1
INSERT INTO schema_migrations (version, description, checksum)
VALUES (1, 'Initial schema - core tables, job queues, audit logs, unified investigation tables', 'initial')
ON CONFLICT (version) DO NOTHING;

-- Record chat_messages table as version 2
INSERT INTO schema_migrations (version, description, checksum)
VALUES (2, 'Add chat_messages table for conversation persistence', '002_add_chat_messages')
ON CONFLICT (version) DO NOTHING;

-- Record unified tables refactor as version 3
INSERT INTO schema_migrations (version, description, checksum)
VALUES (3, 'Refactor to unified events/graph_nodes/graph_edges tables with investigation_id column', '003_unify_tables')
ON CONFLICT (version) DO NOTHING;

-- Record timeline refactor as version 4
INSERT INTO schema_migrations (version, description, checksum)
VALUES (4, 'Refactor knowledge graph to evidence timeline - replace graph_nodes/edges with timeline_entries/notes', '004_graph_to_timeline')
ON CONFLICT (version) DO NOTHING;

-- Record unique constraint as version 5
INSERT INTO schema_migrations (version, description, checksum)
VALUES (5, 'Add unique constraint on (investigation_id, event_id) for timeline_entries', '005_add_timeline_unique_constraint')
ON CONFLICT (version) DO NOTHING;

-- Record chat refactor as version 6
INSERT INTO schema_migrations (version, description, checksum)
VALUES (6, 'Add message_type and parent_message_id columns to chat_messages for single source of truth architecture', '006_chat_refactor')
ON CONFLICT (version) DO NOTHING;

-- Record RAG feature as version 7
INSERT INTO schema_migrations (version, description, checksum)
VALUES (7, 'Add PGVector extension, embeddings table, investigation_notes, tool_results, filter_config tables for RAG feature', '007_add_rag_feature')
ON CONFLICT (version) DO NOTHING;

-- Record flexible vector dimensions as version 8
INSERT INTO schema_migrations (version, description, checksum)
VALUES (8, 'Support flexible vector dimensions for different embedding models', '008_flexible_vector_dimensions')
ON CONFLICT (version) DO NOTHING;

-- Record investigation choices as version 9
INSERT INTO schema_migrations (version, description, checksum)
VALUES (9, 'Add investigation_choices table for agent-suggested next steps (ChatGPT-style continuation)', '009_add_investigation_choices')
ON CONFLICT (version) DO NOTHING;

-- Record field dictionary as version 10
INSERT INTO schema_migrations (version, description, checksum)
VALUES (10, 'Add field_dictionary table for permanent storage of JSONB field descriptions', '010_add_field_dictionary')
ON CONFLICT (version) DO NOTHING;

-- Record chat log summaries as version 11
INSERT INTO schema_migrations (version, description, checksum)
VALUES (11, 'Add chat_log_summaries table for token-efficient context management (Feature 5)', '011_add_chat_summaries')
ON CONFLICT (version) DO NOTHING;

-- Record reports table as version 12
INSERT INTO schema_migrations (version, description, checksum)
VALUES (12, 'Add reports table for persistent investigation report storage', '012_add_reports')
ON CONFLICT (version) DO NOTHING;

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

-- Trigger for field_dictionary (must be after function definition)
CREATE TRIGGER update_field_dictionary_updated_at
    BEFORE UPDATE ON field_dictionary
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- DEFAULT DATA
-- ============================================================================

-- Create default admin user (password: admin123 - CHANGE IN PRODUCTION!)
-- Password hash is argon2 hash of "admin123"
INSERT INTO users (username, password_hash, role)
VALUES ('admin', '$argon2id$v=19$m=65536,t=3,p=4$g1BKCYEwJsS4l5LyPickJA$8ZGtyRXgCPnXyShzNjjZ1ByH2Qgyp2nLRTInMVWMUZc', 1)
ON CONFLICT (username) DO NOTHING;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE users IS 'User accounts with role-based access control';
COMMENT ON TABLE investigations IS 'Investigation metadata - references unified events/graph tables via investigation_id';
COMMENT ON TABLE events IS 'Unified event data across all investigations, partitioned by investigation_id';
COMMENT ON TABLE timeline_entries IS 'Evidence timeline entries - chronologically ordered events, findings, and observations';
COMMENT ON TABLE timeline_notes IS 'User annotations and notes on timeline entries for collaborative investigation';
COMMENT ON TABLE artifacts IS 'Uploaded files with binary storage and classification';
COMMENT ON TABLE mcp_servers IS 'User-defined MCP server endpoints for agent tool access';
COMMENT ON TABLE jobs_parsing IS 'Queue for parsing jobs (artifact processing)';
COMMENT ON TABLE jobs_agents IS 'Queue for agent execution jobs (policy-driven analysis). User_id links to LLM config for model/API key.';
COMMENT ON TABLE audit_log IS 'Immutable audit trail of all system actions';
COMMENT ON TABLE deletion_log IS 'Immutable record of deleted investigations';
COMMENT ON TABLE schema_migrations IS 'Tracks applied database schema migrations for version control';
COMMENT ON TABLE llm_provider_config IS 'Per-user LLM provider configuration for inference (API endpoint, model, temperature, context length)';
COMMENT ON TABLE chat_messages IS 'Chat conversation history in OpenAI message format';
COMMENT ON TABLE tool_executions IS 'Explicit tool execution tracking - one row per tool call';
COMMENT ON COLUMN tool_executions.chat_message_id IS 'Parent agent message this tool belongs to';
COMMENT ON COLUMN tool_executions.status IS 'Tool status: executing, completed, failed';
COMMENT ON COLUMN chat_messages.deleted_at IS 'Soft delete timestamp - null means not deleted';
COMMENT ON COLUMN chat_messages.role IS 'OpenAI role: system, user, assistant, tool';
COMMENT ON COLUMN chat_messages.content IS 'Message content (null for tool_calls)';
COMMENT ON COLUMN chat_messages.name IS 'Optional name for function/tool messages';
COMMENT ON COLUMN chat_messages.tool_calls IS 'Tool calls array (for assistant messages)';
COMMENT ON COLUMN chat_messages.tool_call_id IS 'Tool call ID (for tool response messages)';
COMMENT ON COLUMN chat_messages.metadata IS 'Additional metadata (intent, confidence, job_id, etc.)';
COMMENT ON COLUMN chat_messages.include_in_llm_context IS 'Whether to include this message when building LLM context';
COMMENT ON COLUMN chat_messages.visible_in_ui IS 'Whether to display this message in the chat UI (excludes internal system messages)';
COMMENT ON COLUMN chat_messages.created_at IS 'Message timestamp';
COMMENT ON COLUMN chat_messages.message_type IS 'Message type: question, assistant_answer, agent_chat, tool_execution, summary, error, system';
COMMENT ON COLUMN investigations.parsing_locked IS 'True while artifact parsing is in progress - blocks new user questions';
COMMENT ON COLUMN chat_messages.parent_message_id IS 'Parent message ID for threading conversations';
COMMENT ON TABLE investigation_choices IS 'Agent-suggested next investigative steps when turn limit reached (ChatGPT-style user interrogation)';
COMMENT ON COLUMN investigation_choices.title IS 'Short title for the suggested path (e.g., "Analyze logon patterns")';
COMMENT ON COLUMN investigation_choices.description IS 'Detailed description of what this choice will investigate';
COMMENT ON COLUMN investigation_choices.rationale IS 'Why the agent suggests this path based on evidence so far';
COMMENT ON COLUMN investigation_choices.suggested_query IS 'The question/query to execute if user selects this choice';
COMMENT ON COLUMN investigation_choices.suggested_effort IS 'Suggested effort level (low=3 turns, medium=6 turns, high=9 turns)';
COMMENT ON COLUMN investigation_choices.tool_suggestions IS 'Optional hints about which tools to use';
COMMENT ON COLUMN investigation_choices.display_order IS 'Order to display choices (lower = higher priority)';
COMMENT ON COLUMN investigation_choices.selected IS 'Whether user has selected this choice';
COMMENT ON COLUMN investigation_choices.selected_at IS 'When the choice was selected';
COMMENT ON COLUMN investigation_choices.selected_job_id IS 'Job ID created when user selected this choice';
COMMENT ON TABLE reports IS 'Generated investigation reports - only the most recent report per investigation is kept';
COMMENT ON COLUMN reports.markdown_content IS 'Full markdown report content including executive summary, timeline narrative, findings, and recommendations';
COMMENT ON COLUMN reports.user_prompt IS 'Optional custom prompt provided by user for report generation';
COMMENT ON COLUMN reports.generated_at IS 'Timestamp when report was generated';


