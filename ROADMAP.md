
# Open Agent Investigation - Roadmap

This document outlines planned enhancements and future directions for the project. Items are grouped by area and roughly ordered by effort/priority.

---

## LLM/RAG/Agent

### Chat Routing Optimization

**Goal:** Reduce latency and LLM calls for faster response times, especially on local/self-hosted models.

- Simplify intent classification pipeline (fewer intermediate LLM calls)
- Implement caching for common query patterns
- Add fast-path routing for simple queries (metadata, counts)
- Optimize context window usage to reduce token overhead

### Investigation Guidance

**Goal:** Help users and agents navigate complex investigations more effectively.

- Surface next-step suggestions based on current findings
- Recommend relevant playbooks dynamically during investigation
- Highlight unexplored artifact types or time gaps
- Suggest correlation opportunities between artifact types

### Reporting Enhancements

**Goal:** Improve report quality and customization options.

- Add report profiles/templates (executive summary, technical deep-dive, timeline-focused)
- Refine prompts for clearer, more actionable output
- Support custom report sections via playbook configuration
- Improve PDF formatting and visual presentation

---

## Forensic Artifact Support

### Expanded Windows Artifacts

**Priority:** Artifacts with existing Python libraries.

- **BAM/DAM** - Background Activity Moderator (Windows 10+ execution via Registry)
- **UserAssist** - GUI program execution tracking (Registry)
- **BITS** - Background Intelligent Transfer Service logs
- **USB Device History** - USB connection artifacts (Registry and setupapi.log)
- **PowerShell History** - ConsoleHost_history.txt and event logs
- **WMI Persistence** - Event subscriptions and filters (Repository files)
- **Windows Defender Logs** - Quarantine and detection history

**Lower Priority:** Artifacts requiring custom parsers or complex formats.

- **Recycle Bin** - $I and $R files (deletion tracking)
- **Hibernation Files** - Memory extraction from hiberfil.sys
- **Page Files** - Memory artifacts from pagefile.sys
- **Volume Shadow Copies** - VSS snapshot parsing
- **Event Trace Logs (ETL)** - .etl files for advanced diagnostics

### Cross-Platform Artifact Support

**Linux:**
- System logs (syslog, auth.log, journalctl)
- Bash/Zsh history
- Cron jobs and systemd timers
- Package manager logs (apt, yum, dnf)
- User profiles and SSH artifacts

**macOS:**
- Unified Logs (log show, tracev3 format)
- Bash/Zsh history
- LaunchAgents/LaunchDaemons
- Quarantine events (com.apple.quarantine)
- Spotlight metadata

### Binary and Executable Analysis

**Priority:** Leverage existing libraries first.

- **PE Analysis** - pefile library (headers, imports, exports, resources)
- **ELF Analysis** - pyelftools (Linux binaries)
- **Mach-O Analysis** - macholib (macOS binaries)
- **Disassembly** - Capstone integration (cross-platform)
- **YARA-X** - Scan files with YARA
- **CAPA** - Analyze executables with CAPA

**Lower Priority:** Advanced analysis requiring external tools.

- Headless Ghidra or Radare2 integration
- Decompilation and control flow analysis
- Malware unpacking and obfuscation detection

### Network and Log Analysis

**Priority:** Standard formats with Python support.

- **PCAP/PCAPNG** - Scapy or dpkt (network traffic analysis) + YARA-X support
- **Apache/Nginx Logs** - Line-by-line parsing (access/error logs)
- **Windows Firewall Logs** - pfirewall.log parsing
- **DNS Logs** - Query/response analysis


### Forensic Image Support

**Goal:** Enable direct analysis of disk images without manual extraction.

- **E01/Ex01** - libewf integration (Expert Witness Format)
- **Raw DD Images** - Direct mounting and artifact extraction
- **VMDK/VHD** - Virtual disk parsing
- **Automated Artifact Extraction** - Detect and extract artifacts from mounted images

### Third-Party Tool Integration

**Goal:** Ingest output from existing forensic tools.

- **PLASO/log2timeline** - Import super timeline CSV/JSON
- **Velociraptor** - Parse collection artifacts
- **Volatility** - Memory analysis output integration
- **KAPE** - Automated triage collection support

---

## Agent Capabilities

### File Analysis Agent

**Goal:** Provide deep analysis of suspicious files during investigations.

- PE/ELF/Mach-O disassembly and static analysis
- Document/PDF metadata and embedded object extraction
- Binary entropy, strings, and magic byte analysis
- Archive and embedded file extraction (recursive)
- Hash-based threat intelligence lookups

### Threat Intelligence Agent

**Goal:** Enrich investigations with external context.

- WHOIS queries for domain/IP attribution
- DNS resolution and reverse lookups
- Web scraping for threat reports and IOC lists
- API integrations (user-supplied keys):
  - VirusTotal (file/URL/domain/IP reputation)
  - PassiveTotal/RiskIQ (PDNS, WHOIS, certificates)
  - AbuseIPDB (IP reputation)
  - Shodan (IP/port scanning data)
  - URLhaus/MalwareBazaar (malware samples)

### Binary Analysis Tools

**Goal:** Extend file analysis with specialized binary capabilities.

- Advanced entropy analysis (per-section, sliding window)
- String extraction with encoding detection (ASCII, UTF-16, base64)
- XOR/ROT brute-forcing for obfuscated strings
- Embedded file carving (PE, ZIP, etc.)
- Yara rule scanning (user-supplied rulesets)

---

## UI/UX Improvements

### Chat Interface Refinements

- Add job cancellation from Jobs Queue modal
- Display report profile previews before generation
- Improve onboarding flow (force LLM config on first login)
- Add inline help/tooltips for LLM configuration options

### Analysis Views

**Goal:** Provide interactive explorers for complex artifacts.

- **Registry Viewer** - Tree navigation, search, value inspection
- **MFT Explorer** - File system timeline, path reconstruction
- **Network Traffic Viewer** - PCAP analysis with filters (future)
- **Executable/File Viewer** - View detailed analysis results from CAPA, YARA-X and Disassembly (headless Ghidra docker)

### User Management

- Admin panel for creating/managing user accounts
- Role-based permissions (admin, analyst, read-only)
- Investigation sharing and collaboration features

---

## Infrastructure and Performance

### Database Optimizations

- Table partitioning for large investigations (events, timeline)
- Improved indexing strategies for JSONB queries
- Query result caching for analysis modules
- Archive/compress old investigations

### Worker Enhancements

- Prioritized job queues (parsing > embedding > agents)
- Dynamic worker scaling based on load
- Progress checkpointing for long-running jobs
- Retry logic with exponential backoff

---

## Documentation

- Video tutorials for common workflows
- Playbook authoring guide with examples
- Custom parser development guide
- API integration examples (Python, curl)
- Troubleshooting guide for common issues
