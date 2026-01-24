# Open Agent Investigation - Worker

The **Worker** is an asynchronous job processor that handles artifact parsing and AI agent execution. It polls the database for pending jobs, claims them atomically, and processes them in the background with real-time streaming to the UI.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Job Types](#job-types)
- [Parsers](#parsers)
- [Agents](#agents)
- [Configuration](#configuration)
- [Development](#development)

---

## Overview

The Worker service is responsible for:

1. **Multiprocessing Pool**: Runs min(CPU_count, 4) worker processes for parallel job execution
2. **Job Polling**: Each worker continuously polls `jobs_parsing` and `jobs_agents` tables
3. **Atomic Job Claiming**: Uses PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` for concurrency
4. **Artifact Parsing**: Extracts events from EVTX, Registry, MFT, Prefetch, and LNK files
5. **Agent Execution**: Runs AssistantAgent with bounded turn execution
6. **Progress Streaming**: Sends real-time agent reasoning and findings via WebSocket
7. **Turn-Based Execution**: Limits tools per turn (5 max), configurable max turns
8. **Stop Signal Handling**: Graceful stop via control queue, force-kill after timeout
9. **Error Handling**: Gracefully handles failures and updates job status
10. **Process Monitoring**: Automatically restarts crashed worker processes

### Key Features

✅ **Multiprocessing Pool** - Runs min(CPU_count, 4) worker processes for parallel execution  
✅ **Process Isolation** - Each worker has its own database connection and event loop  
✅ **Graceful Stop** - Stop signal via control queue, force-kill after 30 seconds  
✅ **Process Monitoring** - Automatically restarts crashed workers  
✅ **Concurrent Processing** - Multiple workers can claim jobs simultaneously  
✅ **Idempotent Operations** - Jobs can be safely retried  
✅ **Real-time Streaming** - WebSocket notifications with agent reasoning  
✅ **LLM Integration** - Supports OpenAI, Ollama, and custom endpoints  
✅ **Bounded Turn Execution** - 5 tools per turn, configurable max turns (5/10/15)  
✅ **Turn Progress Tracking** - UI shows "Turn X/Y" instead of confusing tool counts  
✅ **Agent-Controlled Timeline** - Optional auto_register parameter for bulk registration  
✅ **Event-First Timeline** - Auto-fetches complete event data (no transcription errors)  
✅ **Tool Descriptions** - Every tool execution shows user-friendly description in UI  
✅ **Investigation Context** - Agents load timeline, chat history, and available data  
✅ **Seamless Continuation** - Resume incomplete investigations in same chat bubble  
✅ **Extensible** - Easy to add new parsers and tools  

---

## Architecture

### Multiprocessing Model

```
┌────────────────────────────────────────────────────────────┐
│                    Main Process (Manager)                    │
│                                                              │
│  - Recovers stale jobs on startup                           │
│  - Spawns min(CPU_count, 4) worker processes                │
│  - Creates control queues for each worker                   │
│  - Monitors workers and restarts if they crash              │
│  - Handles SIGINT/SIGTERM for graceful shutdown             │
└────────────────────────────────────────────────────────────┘
                               │
                               │ spawns
                               │
         ┌─────────────────────────┴────────────────────────┐
         │                                                │
    ┌────┴────┐   ┌───────────┐   ┌────┴────┐
    │ Worker-0 │   │  Worker-1  │   │ Worker-N │
    │          │   │           │   │          │
    │  - Own DB │   │  - Own DB  │   │  - Own DB │
    │  - Own    │   │  - Own     │   │  - Own    │
    │    loop   │   │    loop    │   │    loop   │
    │  - Control│   │  - Control │   │  - Control│
    │    queue  │   │    queue   │   │    queue  │
    └────┬────┘   └────┬─────┘   └────┬────┘
         │              │              │
         │              │              │
         └──────────────┬──────────────┘
                        │
                        │ poll jobs (SKIP LOCKED)
                        │
                   ┌────┴────┐
                   │ Database │
                   │          │
                   │ jobs_*   │
                   │ events   │
                   └─────────┘
```

### Stop Signal Flow

```
1. User clicks "Stop" button in UI
   ↓
2. UI sends POST /api/v1/jobs/agent/{job_id}/stop
   ↓
3. API sets metadata.stop_requested = true in database
   ↓
4. API schedules force-stop after 30 seconds (background task)
   ↓
5. Worker process checks stop_requested flag during execution
   ↓
6a. Graceful stop: Worker finishes current turn, marks job as failed
    → Job completed within 30 seconds
   ↓
6b. Force stop: After 30 seconds, API marks job as failed
    → Worker detects status change and terminates
```

### Directory Structure

```
worker/
├── main.py                      # Worker manager and process spawner
├── agents/                      # AI agents
│   ├── __init__.py
│   ├── base_agent.py            # Legacy base agent class
│   ├── assistant_agent.py       # AssistantAgent (primary, bounded turns)
│   ├── unified_agent.py         # UnifiedAgent (legacy, self-directed)
│   └── cli_harness.py           # CLI testing harness (deprecated)
├── parsers/                     # Artifact parsers
│   ├── __init__.py
│   ├── dispatcher.py            # Parser routing
│   ├── evtx_parser.py           # Windows Event Logs
│   ├── registry_parser.py       # Registry hives
│   ├── mft_parser.py            # Master File Table
│   ├── prefetch_parser.py       # Prefetch files
│   ├── lnk_parser.py            # LNK shortcuts
│   └── utils.py                 # Shared utilities
├── tools/                       # Agent tools
│   ├── __init__.py
│   ├── event_tools.py           # Event querying tools
│   ├── timeline_tools.py        # Timeline management tools
│   ├── control_tools.py         # Agent control tools
│   ├── tool_wrappers.py         # Tool wrappers with auto_register support
│   └── websearch_tool.py        # Web search tool (retrieve_and_parse_url)
├── Dockerfile                   # Worker container
└── README.md                    # This file
```

---

## Installation

### Docker (Recommended)

The Worker runs as a Docker container:

```bash
# Start worker with docker compose
docker compose up -d worker

# View worker logs
docker compose logs -f worker

# Scale workers (for parallel processing)
docker compose up -d --scale worker=3

# Restart worker
docker compose restart worker
```

### Manual Installation

For development:

```bash
cd api

# Activate virtual environment
source venv/bin/activate

# Install dependencies (same as API)
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://postgres:example@localhost/open_agent_inv"
export API_HOST="localhost"
export API_PORT="8000"

# Run worker
python -m worker.main
```

---

## Job Types

### 1. Parsing Jobs

Parsing jobs extract structured events from forensic artifacts.

**Database Table**: `jobs_parsing`

**Job Flow**:
1. User uploads artifact → API creates `ParsingJob` with status `pending`
2. Worker claims job → status changes to `running`
3. Worker dispatches to appropriate parser
4. Parser extracts events → inserts into `events` table
5. Worker updates job status to `completed` or `failed`

**Example**:
```python
# Create parsing job (done by API)
job = ParsingJob(
    investigation_id=UUID("..."),
    artifact_id=42,
    status=JobStatus.PENDING
)
await db.commit()

# Worker claims and processes
job = await claim_parsing_job(db)
await process_parsing_job(db, job)
```

### 2. Agent Jobs

Agent jobs run AI-powered investigations using LLM models.

**Database Table**: `jobs_agents`

**Job Flow**:
1. User asks question → API creates `AgentJob` with status `pending`
2. Worker claims job → status changes to `running`
3. Worker initializes agent with user's LLM config
4. Agent executes investigation loop (query events, build graph, reason)
5. Worker streams progress updates via WebSocket
6. Worker updates job status to `completed` or `failed`

**Example**:
```python
# Create agent job (done by API)
job = AgentJob(
    investigation_id=UUID("..."),
    user_id=1,
    policy_id="event_search",
    rule_values={"effort": "medium"},
    seed_instructions="Find failed logon attempts",
    status=JobStatus.PENDING
)
await db.commit()

# Worker claims and processes
job = await claim_agent_job(db)
await process_agent_job(db, job)
```

---

## Parsers

### Parser Dispatcher

The dispatcher routes artifacts to the correct parser based on file classification:

```python
# worker/parsers/dispatcher.py
async def parse_artifact(
    db: AsyncSession,
    investigation_id: UUID,
    artifact_id: int
) -> int:
    """
    Parse artifact and insert events.
    Returns: Number of events inserted
    """
    artifact = await get_artifact(db, artifact_id)
    
    if artifact.classification == ArtifactClassification.LOG_FILE:
        # EVTX parser
        return await parse_evtx(db, investigation_id, artifact)
    elif artifact.classification == ArtifactClassification.SYSTEM_HIVE:
        # Registry parser
        return await parse_registry(db, investigation_id, artifact)
    # ... etc
```

### EVTX Parser

Parses Windows Event Logs (`.evtx` files).

**Library**: `evtx` (Python)

**Output Event Type**: `evtx_<channel>_<event_id>` (e.g., `evtx_security_4624`, `evtx_security_4688`, `evtx_sysmon_1`)

**Payload Structure** (flattened):
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

**Common Event IDs**:
- `4624` - Successful logon
- `4625` - Failed logon
- `4688` - Process creation
- `4689` - Process termination
- `4720` - User account created
- `7045` - Service installed

### Registry Parser

Parses Windows Registry hives (`SYSTEM`, `SOFTWARE`, `SAM`, `NTUSER.DAT`).

**Library**: `regipy` (Python)

**Output Event Types**:
- `registry_value` - Individual registry key/value pairs
- `registry_<plugin_name>` - Plugin-specific outputs (e.g., `registry_run_keys`)

**Payload Structure**:
```json
{
  "key_path": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
  "value_name": "UpdateService",
  "value_data": "C:\\Program Files\\UpdateService\\service.exe",
  "value_type": "REG_SZ",
  "last_modified": "2024-03-24T10:15:00Z"
}
```

### MFT Parser

Parses NTFS Master File Table (`$MFT`).

**Library**: `mft` (Python)

**Output Event Type**: `mft_entry`

**Payload Structure**:
```json
{
  "record_number": 12345,
  "file_name": "document.pdf",
  "full_path": "C:\\Users\\jsmith\\Documents\\document.pdf",
  "file_size": 524288,
  "is_directory": false,
  "created": "2024-03-24T08:30:00Z",
  "modified": "2024-03-24T08:35:00Z",
  "accessed": "2024-03-24T09:00:00Z"
}
```

### Prefetch Parser

Parses Windows Prefetch files (`*.pf`).

**Library**: `prefetch2es` (Python)

**Output Event Type**: `prefetch_execution`

**Payload Structure**:
```json
{
  "executable_name": "CHROME.EXE",
  "file_size": 2048,
  "file_path": "CHROME.EXE-A1B2C3D4.pf"
}
```

### LNK Parser

Parses Windows shortcut files (`*.lnk`).

**Library**: `LnkParse3` (Python)

**Output Event Type**: `lnk_file`

**Payload Structure**:
```json
{
  "header.write_time": 1679654567.123,
  "header.access_time": 1679654568.456,
  "link_info.local_base_path": "C:\\Users\\jsmith\\Documents\\report.xlsx",
  "string_data.working_dir": "C:\\Users\\jsmith\\Documents"
}
```

---

## Agents

### Base Agent

All agents inherit from `BaseAgent` (`worker/agents/base_agent.py`):

```python
class BaseAgent:
    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        job_id: int,
        question: str,
        effort: str = "medium",
        llm_endpoint: str = None,
        llm_model: str = None,
        llm_api_key: str = None,
        llm_max_context: int = 8192,
        llm_temperature: float = 0.7,
    ):
        ...
    
    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """Execute agent and yield progress updates."""
        ...
```

### Assistant Agent (Primary)

The primary forensic analysis agent with bounded turn execution.

**File**: `api/worker/agents/assistant_agent.py`

**Architecture**:
- **Bounded Turns**: Each turn limited to 5 tool executions max
- **Configurable Depth**: Max turns based on effort level (Quick=5, Standard=10, Thorough=15)
- **Two-Phase Workflow**: Investigation phase (tools) → Reporting phase (explanation)
- **Real-time Streaming**: Progress updates via WebSocket after each tool
- **Turn Progress**: UI shows "Turn X/Y" instead of confusing tool counts
- **Agent-Controlled Timeline**: Optional auto_register parameter for bulk registration
- **Tool Descriptions**: REQUIRED description parameter for all search tools (shown in UI)

**Capabilities**:
- Loads full investigation context on startup (timeline entries, chat history, event counts)
- Query events by type, time range, content (all return event_ids)
- Aggregate JSONB fields for pattern discovery
- Register events to timeline (agent decides when to use auto_register)
- Automatic event data retrieval (no transcription errors)
- Explains findings after each tool execution (enforced by system prompt)
- Streams all reasoning and progress in real-time
- Only calls complete_investigation when investigation is truly complete (not for status updates)
- Can be continued seamlessly if turn limit is reached (reuses same message bubble)

**Tools** (11 total):
1. `count_events` - Count events matching criteria
2. `search_events_by_type` - Find events by type pattern (returns event_ids, optional auto_register)
3. `search_events_by_timerange` - Time-based queries (returns event_ids, optional auto_register)
4. `search_events_by_content` - Full-text search (returns event_ids, optional auto_register)
5. `query_jsonb_field` - Query specific JSONB fields (returns event_ids, optional auto_register)
6. `aggregate_jsonb_field` - Aggregate for pattern discovery
7. `get_event_by_id` - Retrieve specific event
8. `register_timeline_entry` - Add single event to timeline (auto-fetches complete event data)
9. `register_finding` - Record investigation finding
10. `complete_investigation` - Signal investigation completion with summary (FINAL ANSWER ONLY)
11. `retrieve_and_parse_url` - Fetch and parse web content (for threat intel lookups)

**Dynamic Context**:
- Agent sees available JSONB fields in investigation context
- Agent sees event type counts and total events
- Agent receives investigation-specific context on startup

**Investigation Workflow**:
```
1. Agent receives question and effort level (max turns: Quick=5, Standard=10, Thorough=15)
2. Agent immediately yields agent_started (UI shows feedback)
3. Agent loads investigation context (event counts, available fields)

Then, for each turn (max 5 tools per turn):

**PHASE 1 - INVESTIGATION**:
   a. Agent calls up to 5 tools (queries, aggregations)
   b. Each tool MUST have 'description' parameter (shown in UI)
   c. Tools can optionally set auto_register=true to bulk-register results
   d. Agent yields tool_executing → UI shows "Turn X/Y" and description
   e. Tool executes → Agent yields tool_result with summary
   f. If auto_register=true, system bulk-registers events and yields timeline_updated

**PHASE 2 - REPORTING**:
   g. Agent explains what it found (1-2 sentences)
   h. Agent yields agent_thinking with explanation
   i. Agent decides: continue to next turn OR call complete_investigation

4. Agent calls complete_investigation ONLY when it has a COMPLETE final answer
5. Agent yields agent_completed with summary and stats
6. Real-time streaming of all reasoning and findings to UI via WebSocket
```

**Example Agent Execution**:
```
Question: "Find failed logon attempts"
Effort: Standard (10 turns max)

[Agent yields agent_started → UI shows message card immediately]

**Turn 1** (5 tools max):
Tool 1: search_events_by_type(event_type="evtx_security_4625", description="Failed logon attempts")
        → UI shows: "Turn 1/10 - Failed logon attempts"
        → Returns 42 events with event_ids
Agent: "Found 42 failed authentication events. Analyzing account patterns..."

Tool 2: aggregate_jsonb_field(jsonb_path="TargetUserName", aggregation="top_values",
                              description="Target account analysis")
        → UI shows: "Turn 1/10 - Target account analysis"
        → Top target: 'admin' account (18 attempts)
Agent: "One account shows 18 attempts. Checking source patterns..."

Tool 3: aggregate_jsonb_field(jsonb_path="IpAddress", aggregation="top_values",
                              description="Source IP analysis")
        → UI shows: "Turn 1/10 - Source IP analysis"
        → Top source: 192.168.1.100 (18 attempts)
Agent: "Single source IP made all attempts. Registering to timeline..."

Tool 4: search_events_by_type(event_type="evtx_security_4625", description="Failed logons for timeline",
                              auto_register=true)
        → UI shows: "Turn 1/10 - Failed logons for timeline"
        → Auto-registers 18 events to timeline
        → UI receives timeline_updated message, counter increments
Agent: "Timeline updated with 18 events. Creating finding..."

Tool 5: register_finding(title="Brute force pattern detected",
                        evidence_event_ids=[528571, 528572, ...])
        → UI shows: "Turn 1/10 - Register finding"

[Agent yields turn_complete]

**Turn 2**:
Agent: "Investigation complete. All evidence documented."
Tool 6: complete_investigation(summary="Found 42 failed logon events from single source IP targeting 'admin' account. Registered 18 events to timeline.")
        → Agent yields agent_completed
        → UI shows stats: "2 turns, 6 tools, 18 timeline entries"

Result:
- Evidence timeline with 18 entries (complete event data, auto-fetched)
- Finding: "Brute force pattern: 18 failed logons to 'admin' from 192.168.1.100"
- Stats: 2 turns executed, 6 tools used, 18 timeline entries created
- User saw real-time progress: "Turn 1/10", "Turn 2/10", tool descriptions, agent explanations
```

---

## Configuration

### Worker Settings

Configure via environment variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:example@db/open_agent_inv

# API Server (for WebSocket callbacks)
API_HOST=api
API_PORT=8000

# Worker Behavior
WORKER_POLL_INTERVAL=1    # Seconds between job polls
WORKER_TIMEOUT=30          # Job timeout (not yet implemented)

# File Storage
INVESTIGATIONS_BASE_PATH=/data/investigations
POLICIES_PATH=/app/data/policies
AGENTS_PATH=/app/data/agents
```

### LLM Configuration

LLM settings are per-user and stored in the database (`llm_provider_config` table).

**Supported Providers**:
- **OpenAI** - `https://api.openai.com/v1/chat/completions`
- **Ollama** - `http://ollama:11434/v1/chat/completions`
- **Custom** - Any OpenAI-compatible endpoint

**Authentication Methods**:
1. **Bearer Token** - `Authorization: Bearer sk-...`
2. **Cookie-based** - For Ollama and local models

---

## Development

### Running Worker Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://postgres:example@localhost/open_agent_inv"
export API_HOST="localhost"
export API_PORT="8000"

# Run worker
python -m worker.main
```

### Testing Agents Locally

```bash
# Test AssistantAgent with full database context
python -m worker.agents.assistant_agent \
  --investigation-id "550e8400-e29b-41d4-a716-446655440000" \
  --question "Find failed logon attempts" \
  --effort standard \
  --llm-endpoint "http://localhost:11434/v1/chat/completions" \
  --llm-model "llama3"

# Note: CLI harness is deprecated, use direct agent execution
```

### Adding a New Parser

1. Create parser file in `worker/parsers/`:
   ```python
   # worker/parsers/my_parser.py
   async def parse_my_artifact(
       db: AsyncSession,
       investigation_id: UUID,
       artifact: Artifact
   ) -> int:
       """Parse custom artifact type."""
       events = []
       
       # Parse artifact.blob
       for item in parse_custom_format(artifact.blob):
           events.append({
               "investigation_id": investigation_id,
               "event_ts": item.timestamp,
               "artifact_id": artifact.artifact_id,
               "event_type": "custom_event",
               "payload": item.to_dict()
           })
       
       # Bulk insert
       await insert_events(db, investigation_id, events)
       return len(events)
   ```

2. Register in dispatcher:
   ```python
   # worker/parsers/dispatcher.py
   from .my_parser import parse_my_artifact
   
   async def parse_artifact(...):
       if artifact.classification == ArtifactClassification.CUSTOM:
           return await parse_my_artifact(db, investigation_id, artifact)
   ```

### Adding a New Agent

1. Create agent class in `worker/agents/`:
   ```python
   # worker/agents/my_agent.py
   from .base_agent import BaseAgent
   
   class MyAgent(BaseAgent):
       async def run(self):
           # Custom investigation logic
           async for update in super().run():
               yield update
   ```

2. Create agent YAML in `api/data/agents/`:
   ```yaml
   # api/data/agents/my_agent.yaml
   agent_name: my_agent
   description: Custom investigation agent
   
   system_prompt: |
     You are a specialized investigator...
   
   tools:
     - name: my_custom_tool
       description: Does something special
       parameters:
         param1: "string (description)"
   ```

3. Register in worker:
   ```python
   # worker/main.py
   from worker.agents import MyAgent
   
   async def process_agent_job(db, job):
       if job.policy_id == "my_policy":
           agent = MyAgent(...)
       else:
           agent = EventAgent(...)
   ```

---

## WebSocket Notifications

The worker sends real-time updates to the API server, which broadcasts to WebSocket clients.

### Notification Flow

```
Worker → HTTP POST → API → WebSocket → UI Client
```

### Implementation

```python
# worker/main.py
async def notify_websocket_clients(
    investigation_id: UUID,
    message: dict,
    max_retries: int = 3
):
    """Send notification to API server."""
    url = f"http://{settings.api_host}:{settings.api_port}/api/v1/chat/broadcast/{investigation_id}"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=message) as response:
            if response.status == 200:
                logger.info(f"Broadcast successful")
```

### Message Types

See [API Documentation](../README.md#websocket-support) for message type details.

---

## Performance Optimization

### Parallel Processing

Run multiple workers for concurrent job processing:

```bash
# Scale to 3 workers
docker compose up -d --scale worker=3

# Each worker polls independently
# Jobs are claimed atomically (no conflicts)
```

### Memory Management

Agents implement context compaction to stay within LLM token limits:

```python
# worker/agents/base_agent.py
if self._estimate_tokens(messages) > self.max_context_tokens * 0.85:
    # Compact older messages
    messages = self._compact_context(messages)
```

### Database Optimization

- Use `SKIP LOCKED` for job claiming (no blocking)
- Batch insert events (1000 at a time)
- Index JSONB fields for fast queries

---

## Error Handling

### Job Failures

When a job fails:
1. Worker catches exception
2. Updates job status to `failed`
3. Stores error message (truncated to 1000 chars)
4. Sends failure notification via WebSocket

```python
try:
    await process_agent_job(db, job)
except Exception as e:
    job.status = JobStatus.FAILED
    job.error_message = str(e)[:1000]
    await db.commit()
    
    await notify_websocket_clients(
        investigation_id=job.investigation_id,
        message={"type": "job_failed", "error": str(e)}
    )
```

### Retry Strategy

Jobs are NOT automatically retried. Failed jobs remain in the database for debugging.

To retry manually:
```sql
-- Reset job status to pending
UPDATE jobs_agents
SET status = 'pending', worker_id = NULL, error_message = NULL
WHERE job_id = 42;
```

---

## Monitoring

### Logs

```bash
# View worker logs
docker compose logs -f worker

# Filter for errors
docker compose logs worker | grep ERROR

# Filter for specific job
docker compose logs worker | grep "job_id=42"
```

### Job Queue Status

```sql
-- Check job queue
SELECT status, COUNT(*)
FROM jobs_agents
GROUP BY status;

-- Find stuck jobs (running > 1 hour)
SELECT job_id, started_at, NOW() - started_at AS duration
FROM jobs_agents
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '1 hour';
```

### Worker Health

```bash
# Check if worker is running
docker compose ps worker

# Check worker resource usage
docker stats worker
```

---

## Troubleshooting

### Worker Not Processing Jobs

**Symptoms**: Jobs stuck in `pending` status

**Diagnosis**:
```bash
# Check worker logs
docker compose logs worker

# Verify worker is running
docker compose ps worker

# Check database connectivity
docker compose exec worker python -c "from app.core.database import engine; print('DB OK')"
```

**Solutions**:
- Restart worker: `docker compose restart worker`
- Check database connection string
- Verify PostgreSQL is healthy: `docker compose ps db`

### LLM Connection Errors

**Symptoms**: Agent jobs fail with "LLM endpoint not reachable"

**Diagnosis**:
```bash
# Check LLM config
docker compose exec api psql -U postgres -d open_agent_inv -c "SELECT * FROM llm_provider_config WHERE is_active = true;"

# Test LLM endpoint manually
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "test"}]}'
```

**Solutions**:
- Verify API key is correct
- Check network connectivity to LLM endpoint
- Try a different model (e.g., `gpt-3.5-turbo` instead of `gpt-4`)

### Parser Failures

**Symptoms**: Parsing jobs fail with error message

**Diagnosis**:
```bash
# Check error message
docker compose exec api psql -U postgres -d open_agent_inv -c "SELECT job_id, error_message FROM jobs_parsing WHERE status = 'failed';"

# Check artifact classification
docker compose exec api psql -U postgres -d open_agent_inv -c "SELECT artifact_id, filename, classification FROM artifacts WHERE artifact_id = 42;"
```

**Solutions**:
- Verify artifact file is not corrupted
- Check artifact classification is correct
- Review parser logs for specific error

---

## Further Reading

- [API Documentation](../README.md) - REST API and WebSocket
- [Database Schema](../../db/README.md) - PostgreSQL tables
- [Agent Configuration](../data/agents/README.md) - YAML agent definitions
- [Policy Configuration](../data/policies/README.md) - Investigation policies

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../../README.md).
