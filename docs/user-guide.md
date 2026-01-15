# User Guide

This guide covers common workflows and usage patterns for Open Agent Investigation.

## Overview

Open Agent Investigation provides four main interfaces:

1. **Chat** - Natural language investigation interface
2. **Timeline** - Chronological evidence viewer and editor
3. **Events** - Raw event browser with advanced filtering
4. **Reports** - Investigation report generation

## Uploading Artifacts

### Supported File Types

| Artifact Type | File Extensions | Description |
|---------------|----------------|-------------|
| Event Logs | .evtx | Windows Event Log files |
| Registry Hives | No extension | SYSTEM, SOFTWARE, SAM, SECURITY, NTUSER.DAT |
| Master File Table | $MFT | NTFS file system metadata |
| Prefetch | .pf | Windows prefetch files |
| Shortcuts | .lnk | Windows shortcut files |

### Upload Process

1. Navigate to investigation detail page
2. Click **Upload Artifacts** button
3. Drag and drop files or click to browse
4. Wait for parsing to complete (progress shown in UI)
5. View parsed events in Events tab

### Parsing Status

Check parsing job status:

- **Pending**: Job queued, waiting for worker
- **Running**: Worker processing artifact
- **Completed**: Events inserted successfully
- **Failed**: Parsing error (check worker logs)

### Troubleshooting Upload

**Problem**: Upload succeeds but no events appear

**Solutions**:
- Check file format is supported
- Verify file is not corrupted
- View worker logs: `docker-compose logs worker`
- Check database space: `docker exec db df -h`

**Problem**: Parsing fails with error message

**Solutions**:
- Review error message in Jobs tab
- Verify artifact classification is correct
- Check worker logs for detailed traceback
- Ensure worker has sufficient memory

## Asking Questions

### Query Modes

#### Auto Mode (Recommended)

System automatically routes to best handler:

```
"Find failed logon attempts"           → Agent Handler
"Show timeline entries from today"     → Timeline Handler
"How many events were parsed?"         → General Chat
"Is there evidence of lateral movement?" → Augmented Chat (if embeddings configured)
```

#### Agent Mode

Force full agent execution with tools:

```
"Analyze PowerShell activity"
"Investigate suspicious process creation"
"Find evidence of persistence mechanisms"
```

Use when:
- Complex multi-step analysis needed
- Multiple artifact types involved
- Pattern discovery required

#### Timeline Mode

Force timeline operations:

```
"Add this event to timeline"
"Delete timeline entry 42"
"Show timeline entries tagged 'critical'"
"Timeline statistics"
```

Use when:
- Managing timeline entries
- Filtering timeline by criteria
- Getting timeline statistics

#### Augmented Chat Mode

Force semantic search (requires embeddings):

```
"Evidence of credential access?"
"Lateral movement indicators?"
"Privilege escalation attempts?"
```

Use when:
- Semantic search needed
- Keyword search insufficient
- Exploring unfamiliar attack patterns

#### General Chat Mode

Force context-based Q&A (automatically selected for metadata):

```
"What is this investigation about?"
"How many artifacts uploaded?"
"What's the date range of data?"
```

Use when:
- Simple metadata questions
- No tool execution needed
- Fast response required

### Effort Levels (Agent Mode Only)

- **Quick** (5 turns): Simple queries, fast triage
- **Standard** (10 turns): Balanced depth and speed
- **Thorough** (15 turns): Comprehensive analysis

Agent can request up to 15 additional turns (hard ceiling: 30 total).

### Query Best Practices

**Be specific:**

- Good: "Find failed logon attempts from external IPs in the last 24 hours"
- Bad: "Show me security events"

**Use appropriate mode:**

- Timeline operations → Timeline mode
- Complex analysis → Agent mode
- Metadata questions → Auto mode (routes to General Chat)
- Semantic search → Augmented Chat mode

**Start broad, then narrow:**

1. "How many security events were parsed?"
2. "Find failed authentication events"
3. "Analyze failed logons to admin account"
4. "Show lateral movement from compromised admin account"

## Timeline Management

### Timeline Entry Types

- **Event**: Forensic event from parsed artifacts
- **Finding**: High-level investigative conclusion
- **Observation**: Notable pattern or anomaly
- **Note**: User annotation or context

### Adding Entries

**Via Agent:**

Agent automatically registers significant events using `register_timeline_entry` tool.

**Via Events Tab:**

1. Navigate to Events tab
2. Filter events to find target
3. Click **Add to Timeline** button
4. Entry created with complete event data

**Via Chat (Timeline Mode):**

```
"Add a timeline entry for suspicious PowerShell execution at 14:30 on March 24"
```

### Filtering Timeline

**By Entry Type:**

Select from dropdown: Event, Finding, Observation, Note

**By Event Type:**

Select from autocomplete dropdown (shows only types present in timeline)

**By Tags:**

Enter tags: suspicious, lateral_movement, persistence, credential_access

**By JSONB Data Fields:**

Query specific fields within timeline entry data:

```
Field: TargetUserName
Operator: =
Value: admin
```

**By Date Range:**

Select start and end dates

**By Content:**

Search title and description text

### Removing Entries

1. Expand timeline entry
2. Click **Remove from Timeline** button
3. Confirm removal

Note: This removes the timeline entry only. Source events remain in events table.

### Adding Notes

1. Expand timeline entry
2. Click **Add Note** button
3. Enter note text
4. Click **Save**

Notes appear below timeline entry and are included in reports.

## Event Browsing

### Query Builder

**Event Type Filter:**

Select from dropdown (shows counts per type)

**JSONB Field Queries:**

Build complex queries on event payload fields:

```
Field: payload->>'TargetUserName'
Operator: = (equals)
Value: admin
```

Supported operators:
- `=` Equal
- `!=` Not equal
- `>` Greater than
- `<` Less than
- `>=` Greater than or equal
- `<=` Less than or equal
- `LIKE` Pattern match (case-sensitive)
- `ILIKE` Pattern match (case-insensitive)
- `CONTAINS` Array contains value
- `IS NULL` Field is null
- `IS NOT NULL` Field is not null

**Multiple Filters:**

Add multiple JSONB filters (AND logic):

```
TargetUserName = 'admin'
AND IpAddress LIKE '192.168.%'
AND LogonType = '3'
```

**Date Range:**

Filter by event timestamp (start and end dates)

**Full-Text Search:**

Search payload content (all JSONB fields)

### Dynamic Field Suggestions

Field suggestions update based on selected event type:

1. Select event type filter
2. Field suggestions show only fields from that type
3. Autocomplete dropdown with keyboard navigation
4. "Show all fields" button to browse available fields

### Viewing Event Details

1. Click event row to expand
2. View complete JSONB payload
3. Click **Copy JSON** to copy to clipboard
4. Click **Add to Timeline** to register

### Query Replication

Replicate agent queries to Events tab:

1. Agent executes query tool in Chat
2. Expand tool execution card
3. Click **Query** button
4. Events tab opens with filters pre-populated
5. Explore results with full query builder

Supported tools:
- `query_jsonb_field`
- `query_jsonb_multiple`
- `search_events_by_type`
- `search_events_by_timerange`
- `search_events_by_content`

## Report Generation

### Creating Reports

1. Navigate to Reports tab
2. Optional: Enter custom instructions
   ```
   Focus on lateral movement patterns and credential access attempts.
   Highlight timeline events tagged as 'critical'.
   ```
3. Click **Generate Markdown Report**
4. Review generated report
5. Click **Download PDF** to export

### Report Contents

**Executive Summary:**

LLM-generated high-level findings and recommendations

**Investigation Scope:**

- Investigation title and date range
- Artifacts analyzed (count and types)
- Events parsed (total count by type)
- Timeline entries (count by type and tags)

**Timeline Narrative:**

Chronological walkthrough of significant events with context

**Findings:**

Detailed analysis of discoveries with ATT&CK framework mapping (if applicable)

**Recommendations:**

Suggested next steps for further investigation

**Appendix:**

- Timeline entries (full details)
- Tool executions (agent activity log)
- Event statistics

### Report Persistence

- Reports auto-save to database (one per investigation)
- Previous report loads automatically on tab open
- Regenerating overwrites previous report

### PDF Formatting

- 9pt body text
- 8pt tables and code blocks
- Professional layout with headers and footers
- Syntax highlighting for code blocks

## Configuration

### LLM Provider

Configure in Settings > LLM Configuration:

**Required Fields:**

- Provider Name: openai, ollama, custom
- API Endpoint: Full URL to chat completions endpoint
- Model Name: Model identifier
- Max Context Length: Token limit
- Temperature: 0.0 to 2.0

**Optional Fields:**

- API Key: For authenticated endpoints (leave empty for cookie-based auth)

**Embedding Configuration (for Augmented Chat):**

- Embedding Provider: openai, cohere, ollama
- Embedding API URL: Full URL to embeddings endpoint
- Embedding API Key: API key if required
- Embedding Model: Model identifier
- Vector Dimensions: 768, 1024, 1536, etc.

**Multiple Configurations:**

Create multiple LLM configs and switch between them. Only one can be active at a time.

### User Preferences

**Theme:**

Toggle dark/light mode in header

**Default Mode:**

Set preferred query routing mode (Auto, Agent, Timeline, Augmented Chat)

**Default Effort:**

Set preferred effort level (Quick, Standard, Thorough)

## Common Workflows

### Investigating Failed Authentication

```
1. Upload Security.evtx
2. Ask: "Find failed logon attempts"
3. Review agent analysis (account patterns, source IPs)
4. Filter timeline by tag 'brute_force'
5. Generate report focused on authentication
```

### Analyzing Process Execution

```
1. Upload Sysmon.evtx or Security.evtx (Event ID 4688)
2. Ask: "Find process creation events with suspicious command lines"
3. Review PowerShell, cmd.exe, wscript.exe activity
4. Add suspicious processes to timeline
5. Ask: "Analyze parent-child process relationships"
```

### Discovering Persistence Mechanisms

```
1. Upload SYSTEM and SOFTWARE registry hives
2. Ask: "Search for evidence of persistence mechanisms"
3. Review Run keys, services, scheduled tasks
4. Filter timeline by tag 'persistence'
5. Cross-reference with process execution events
```

### Identifying Lateral Movement

```
1. Upload Security.evtx from multiple systems
2. Ask: "Find remote logon events (Type 3 and 10)"
3. Review source IPs and target systems
4. Ask: "Identify PsExec or WMI usage"
5. Build timeline of lateral movement progression
```

### Triaging Alerts

```
1. Upload relevant artifacts
2. Use Quick effort level for fast triage
3. Ask specific questions based on alert
4. Escalate to Standard or Thorough if needed
5. Generate report for documentation
```

## Tips and Tricks

### Performance Optimization

- Use specific event type filters
- Narrow time ranges when possible
- Use Quick effort for initial triage
- Escalate to Thorough only when needed

### Investigation Organization

- Use consistent tag conventions
- Add notes to timeline entries for context
- Generate reports incrementally
- Create separate investigations for different incidents

### Tag Conventions

Suggested tags:
- `suspicious` - Potentially malicious
- `lateral_movement` - Network traversal
- `persistence` - Persistence mechanisms
- `credential_access` - Credential theft
- `exfiltration` - Data theft
- `verified_malicious` - Confirmed malicious
- `false_positive` - Benign activity

### Keyboard Shortcuts

- `Enter` - Send chat message
- `Escape` - Close modals
- `Arrow keys` - Navigate autocomplete
- `Tab` - Focus next field

### Batch Operations

Use agent with `auto_register=true` for bulk timeline registration:

```
Agent calls: search_events_by_type(event_type="evtx_security_4625", auto_register=true)
Result: All 42 failed logon events registered to timeline automatically
```

## Troubleshooting

### Chat Not Responding

1. Check LLM configuration is active
2. Verify LLM endpoint is reachable
3. View API logs: `docker-compose logs api`
4. Check worker is running: `docker-compose ps worker`

### Timeline Entries Not Appearing

1. Refresh page
2. Clear all filters
3. Check Events tab to verify events exist
4. View chat history to confirm registration

### Slow Performance

1. Reduce effort level
2. Use more specific queries
3. Filter by event type and time range
4. Check database performance: `docker stats db`

### Export Fails

1. Check browser console for errors
2. Verify report was generated successfully
3. Try Markdown export first
4. Check available disk space

## Next Steps

- [Architecture](architecture.md) - Understand system design
- [Reference](reference/api.md) - Explore API documentation
- [Operations](operations.md) - Deploy to production
