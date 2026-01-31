# Open Agent Investigation

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A micro-forensics workbench. Upload forensic artifacts, ask questions in natural language, and let agents help you analyze Windows artifacts, build timelines, and generate reports.

## Quick Start

```bash
git clone https://github.com/eheuser/open-agent-investigation.git
cd open-agent-investigation
docker compose up -d
```

Access the web interface at `https://localhost` (default credentials: `admin` / `admin123`)

**Note:** This project is under active development. See the [Roadmap](ROADMAP.md) for planned features.

## Key Features

### AI-Assisted Investigation
- Natural language queries with intelligent routing to specialized handlers
- Autonomous agent investigations using 16+ forensic tools
- Semantic search over embedded event data (RAG with hybrid BM25 + vector similarity)
- 20+ built-in investigation playbooks covering MITRE ATT&CK tactics

### Artifact Processing
- Automatic extraction of forensic collection archives (ZIP, 7z, RAR)
- Support for 8+ Windows artifact categories (EVTX, Registry, MFT, Prefetch, Browser History, etc.)
- Comprehensive file metadata extraction with hash calculation and entropy analysis
- Automatic event deduplication and normalization

### Investigation Workflow
- Build chronological evidence timelines with automatic event linking
- Create custom investigation playbooks or clone built-in templates
- Generate investigation reports in PDF and Markdown formats
- Real-time agent progress streaming via WebSocket

### Query and Analysis
- Advanced JSONB field queries for complex data filtering
- Event aggregation for pattern discovery
- SQL execution for custom analysis
- Diagram generation (GraphViz/Mermaid) for relationship visualization

## What Makes This Different

**Traditional DFIR tools** require you to know exactly what you're looking for and where to find it. You write queries, parse logs, and manually correlate events across multiple artifacts.

**Open Agent Investigation** lets you ask questions in plain English. The AI agent understands forensic concepts, selects appropriate tools, queries the right artifacts, and explains what it finds. It's like having an experienced analyst helping you investigate.

**Example workflow:**
1. Upload a forensic collection archive (or individual artifacts)
2. Ask: "Find evidence of lateral movement"
3. Agent automatically:
   - Selects the lateral movement playbook
   - Queries Event ID 4624 (network logons)
   - Analyzes source IPs and target accounts
   - Identifies suspicious patterns
   - Adds significant events to your timeline
   - Explains findings in natural language

You can continue the conversation, ask follow-up questions, or switch to manual querying when needed.

## Who Should Use This

**DFIR Practitioners** who want to:
- Speed up initial triage and pattern identification
- Leverage AI to suggest investigation paths
- Automate repetitive analysis tasks
- Learn from built-in playbooks covering common attack techniques

**Incident Responders** who need to:
- Quickly analyze forensic collections from compromised systems
- Correlate events across multiple artifact types
- Generate timeline reports for stakeholders
- Document findings with cited evidence

**SOC Analysts** investigating:
- EDR alerts requiring host-based artifact analysis
- Suspicious authentication patterns
- Lateral movement indicators
- Persistence mechanisms

**Security Researchers** exploring:
- Forensic automation techniques
- LLM applications in digital forensics
- RAG-based semantic search over forensic data

## Project Goals

This project explores how AI can augment forensic analysis by:
- Reducing time spent on repetitive queries and pattern matching
- Suggesting investigation paths based on known attack techniques
- Automating timeline construction and evidence correlation
- Making forensic analysis more accessible to junior analysts

## Roadmap

**Near-term:**
- Additional Windows artifact parsers (Amcache, ShimCache, BITS)
- Memory forensics integration (Volatility)
- Enhanced playbook system with user contributions
- Improved agent reasoning and tool selection

**Long-term:**
- Linux and macOS artifact support
- Network traffic analysis (PCAP parsing)
- Multi-investigation correlation
- Community playbook repository


## How It Works

### Intelligent Query Routing

The system automatically routes your questions to the most appropriate handler:

- **Agent Handler**: Complex multi-step investigations with autonomous tool execution
  - Example: "Find evidence of credential dumping"
  - Uses 16+ forensic tools to query events, aggregate patterns, and build timelines
  - Follows investigation playbooks based on MITRE ATT&CK tactics
  
- **Augmented Chat**: Semantic search using RAG (Retrieval-Augmented Generation)
  - Example: "Is there evidence of lateral movement?"
  - Expands your query into forensic search terms
  - Retrieves relevant events using hybrid keyword + vector similarity
  - Synthesizes findings with source citations
  
- **Timeline Handler**: Direct timeline manipulation
  - Example: "Show timeline entries from March 20-24"
  - Query, add, update, or delete timeline entries
  - Get timeline statistics

- **General Chat**: Quick metadata and context queries
  - Example: "How many events are in this investigation?"
  - Fast responses without tool overhead
  - Answers from investigation metadata only

The system uses LLM-based intent classification to route queries automatically, or you can manually select the mode.

### Supported Artifacts

#### Archive Processing
Upload entire forensic collections as a single ZIP file. The system automatically extracts all files recursively and queues them for parsing.

**Supported formats:** ZIP, 7z, RAR  
**Safety limits:** 10 GB max size, 50,000 files, 5-level nesting depth  
**Structure preservation:** Directory paths encoded in filenames (e.g., `Windows__System32__Security.evtx`)

#### Windows Artifacts

**Event Logs** (.evtx)  
Security, System, Application, Sysmon logs  
Parsed using: evtx (Rust-based parser)

**Registry** (SYSTEM, SOFTWARE, SAM, SECURITY, NTUSER.DAT)  
Registry hives with plugin-based value extraction  
Parsed using: regipy

**File System** ($MFT)  
NTFS Master File Table with full file metadata  
Parsed using: mft

**Prefetch** (*.pf)  
Program execution tracking  
Parsed using: prefetch2es

**Shortcuts** (*.lnk)  
LNK file metadata and targets  
Parsed using: LnkParse3

**Jump Lists** (*.automaticDestinations-ms, *.customDestinations-ms)  
Recently accessed files per application  
Parsed using: olefile

**Browser History** (Chrome, Firefox, Edge)  
Web browsing activity and downloads  
Parsed using: sqlite3, pyesedb

**Scheduled Tasks** (*.job, *.xml)  
Scheduled task definitions and metadata  
Parsed using: xml.etree.ElementTree

**SRUM** (srudb.dat)  
System Resource Usage Monitor database  
Parsed using: pyesedb

**Windows Search** (Windows.edb)  
Indexed file and email metadata  
Parsed using: pyesedb

**Other Artifacts**  
PCA files, bitmap cache, notifications, CryptNetUrlCache

**Unknown Files**  
Automatic fallback to file metadata extraction (hashes, entropy, strings, PE headers)

See [Parser Documentation](api/worker/parsers/README.md) for complete specifications.

### Evidence Timeline

Build chronological timelines of significant events during your investigation:

- Timeline entries reference source events by ID (no data duplication)
- Complete event data auto-fetched when viewing timeline
- Automatic deduplication prevents duplicate entries
- Add findings, observations, and notes to provide context
- Export timelines to reports for stakeholder review

### Agent Execution

Agents use a bounded turn-based execution model:

**Effort Levels:**
- Quick: 3 turns (fast triage)
- Standard: 6 turns (balanced investigation)
- Thorough: 9 turns (deep analysis)
- Dynamic: Agent can request up to 30 turns with justification

**Execution:**
- Each turn allows up to 5 tool executions
- Real-time progress streamed to UI via WebSocket
- Stop execution at any time
- Resume incomplete investigations seamlessly

### Investigation Playbooks

Playbooks guide the AI agent through common investigation scenarios based on MITRE ATT&CK tactics:

**Built-in Playbooks (20):**
- 14 MITRE ATT&CK tactics (Initial Access, Execution, Persistence, etc.)
- 6 attack techniques (Lateral Movement, Kerberoasting, Living off the Land, etc.)
- Automatically selected based on your question
- Immutable templates ensuring consistent analysis

**Custom Playbooks:**
- Clone built-in playbooks and customize for your environment
- Create organization-specific investigation workflows
- Enable/disable per investigation
- Markdown format with syntax highlighting

**Example:** Ask "Find lateral movement" → Agent loads the Lateral Movement playbook → Queries Event ID 4624 (network logons), 4648 (explicit credentials), 5140 (network shares) → Analyzes patterns → Registers findings to timeline

See [Investigation Playbooks](docs/playbooks.md) for the complete list.

## Installation

### Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- LLM API access (OpenAI, Ollama, or compatible endpoint)
- 4 GB RAM minimum (8 GB recommended)
- 20 GB disk space for artifacts and database

### Setup

```bash
git clone https://github.com/eheuser/open-agent-investigation.git
cd open-agent-investigation
docker compose up -d
```

### First Steps

1. **Access the web interface:** `https://localhost` (accept self-signed certificate)
2. **Login:** Default credentials are `admin` / `admin123` (change immediately in Settings)
3. **Configure LLM:**
   - Navigate to Settings > LLM Configuration
   - Add your OpenAI API key, or configure Ollama/local LLM endpoint
   - Select model (e.g., gpt-4, llama3)
   - Save configuration
4. **Create an investigation:**
   - Click "Create Investigation" on the dashboard
   - Enter a title (e.g., "Ransomware Analysis - March 2024")
5. **Upload artifacts:**
   - Upload individual files or entire forensic collection as ZIP
   - System automatically parses and extracts events
6. **Start investigating:**
   - Ask questions in the chat interface
   - Review events in the Events tab
   - Build timeline in the Timeline tab
   - Generate reports when complete

### Testing

```bash
docker compose -f docker-compose.test.yml run --rm test-runner pytest tests/unit/ -v --tb=short
```


## Documentation

- [Getting Started Guide](docs/getting-started.md) - Detailed installation and configuration
- [User Guide](docs/user-guide.md) - Common investigation workflows
- [Investigation Playbooks](docs/playbooks.md) - Playbook reference and customization
- [Architecture Overview](docs/architecture.md) - System design and components
- [API Documentation](api/README.md) - REST API and WebSocket reference
- [Parser Documentation](api/worker/parsers/README.md) - Supported artifacts and formats

## Architecture

```
User Browser <--HTTPS/WSS--> nginx (443) <--HTTP--> API (8000) <--SQL--> PostgreSQL (5432)
                                |                        |                      |
                            Static UI              Worker (AsyncIO)         PGVector
                                                        |                      |
                                                   LLM Backend            Embeddings
```

**Components:**

- **UI**: React 18 frontend with TypeScript and TailwindCSS
- **nginx**: Reverse proxy and static file server (HTTPS on port 443)
- **API**: FastAPI backend with async SQLAlchemy ORM
- **Worker**: Multiprocessing job processor for parsing and agent execution
- **Database**: PostgreSQL 15 with PGVector extension for vector similarity search
- **LLM**: OpenAI, Ollama, or compatible endpoint for AI capabilities

**Technology Stack:**
- Python 3.11+, FastAPI 0.110, React 18.2, PostgreSQL 15, Node.js 18+

## Security Considerations

**Authentication:**
- JWT token-based authentication (24-hour expiration)
- Argon2id password hashing with memory-hard parameters
- Role-based access control (regular users, administrators)

**Data Protection:**
- API keys encrypted at rest using PostgreSQL pg_crypto
- SSL/TLS for all network communication
- Prepared statements prevent SQL injection
- No plaintext password storage

**Deployment:**
- Change default admin password immediately
- Use strong passwords (12+ characters, mixed case, numbers, symbols)
- Configure firewall rules to restrict access
- Regularly update dependencies for security patches
- Review audit logs for suspicious activity

## System Requirements

**Operating Systems:**
- Linux (Ubuntu 20.04+, Debian 11+)
- macOS 12+
- Windows 10/11 with WSL2

**Browsers:**
- Chrome 100+, Firefox 100+, Safari 15+, Edge 100+

**LLM Providers:**
- OpenAI (GPT-4, GPT-3.5-turbo)
- Ollama (Llama 3, Mistral, Mixtral)
- Azure OpenAI Service
- Any OpenAI-compatible endpoint (LM Studio, etc.)

## Current Limitations

- **Windows artifacts only** - Linux and macOS support planned
- **No memory forensics** - Volatility integration on roadmap
- **No network analysis** - PCAP parsing planned
- **Single investigation per session** - Multi-investigation correlation planned
- **PostgreSQL only** - No alternative database backends

## Frequently Asked Questions

**Q: Do I need OpenAI to use this?**  
A: No. You can use Ollama or any OpenAI-compatible local LLM. No internet connection required for local models.

**Q: What's the difference between Agent and Augmented Chat modes?**  
A: Agent mode uses autonomous tool execution for complex multi-step investigations. Augmented Chat uses semantic search (RAG) for finding relevant events. Agent is more thorough but slower. Augmented Chat is faster for targeted searches.

**Q: Can I use this on real investigations?**  
A: Yes, but verify AI-generated findings manually. The agent can miss subtle indicators or make incorrect correlations. Always validate conclusions with traditional forensic methods.

**Q: How much data can it handle?**  
A: Tested with 1+ million events per investigation. Practical limits depend on available RAM and storage. Recommend 8 GB RAM and SSD storage for large investigations.

**Q: Is this production-ready?**  
A: This is an active development project. Use for research, learning, and experimental investigations. Not recommended for mission-critical production use without thorough testing in your environment.

**Q: Can I contribute?**  
A: Absolutely! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Contributions welcome for parsers, playbooks, bug fixes, and documentation.


## Contributing

Contributions are welcome! Areas where you can help:

- **Parsers**: Add support for additional Windows artifacts or other operating systems
- **Playbooks**: Create investigation playbooks for specific attack scenarios
- **Tools**: Develop agent tools for specialized analysis
- **Documentation**: Improve guides, add examples, fix typos
- **Bug Reports**: Report issues with detailed reproduction steps
- **Feature Requests**: Suggest improvements or additional capabilities

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

**Security Issues:** Report security vulnerabilities privately via [SECURITY.md](SECURITY.md)

## Support and Community

- **Documentation**: [docs/index.md](docs/index.md)
- **Discussions**: [GitHub Discussions](https://github.com/eheuser/open-agent-investigation/discussions)
- **Bug Reports**: [Issue Tracker](https://github.com/eheuser/open-agent-investigation/issues)
- **Security Issues**: [SECURITY.md](SECURITY.md)

## Acknowledgments

This project builds on excellent open-source tools:

- **Frameworks**: [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [PostgreSQL](https://www.postgresql.org/)
- **Parsers**: [evtx](https://github.com/omerbenamram/evtx), [regipy](https://github.com/mkorman90/regipy), [LnkParse3](https://github.com/Matmaus/LnkParse3), [prefetch2es](https://github.com/forensicmatt/prefetch2es)
- **Vector Search**: [pgvector](https://github.com/pgvector/pgvector)

Thank you to the DFIR community for sharing knowledge and tools that make projects like this possible.

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE) for details.

---

**Found this useful? Star the repo and share with the DFIR community!**