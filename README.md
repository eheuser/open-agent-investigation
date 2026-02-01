# Open Agent Investigation

[![License: GPL‑v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python ≥ 3.11](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker required](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A micro‑forensics workbench that ingests forensic artifacts, accepts natural‑language queries, and orchestrates a suite of forensic tools to produce timelines, reports, and actionable insight.

---

## Overview

Open Agent Investigation (OAI) provides an end‑to‑end workflow for Windows host investigations:

* **Automated artifact ingestion** – ZIP/7z/RAR collections are unpacked recursively; supported formats include EVTX, Registry hives, $MFT, Prefetch, LNK, Jump Lists, browser histories, scheduled tasks, SRUM, and more.
* **Natural‑language driven analysis** – Queries such as “find evidence of lateral movement” are mapped to a predefined playbook that executes the appropriate parsers, correlation logic, and timeline updates.
* **Hybrid retrieval** – Event data is indexed with both BM25 keyword search and vector embeddings (PGVector) enabling fast semantic lookup.
* **Playbook engine** – Over 20 built‑in MITRE ATT&CK‑aligned playbooks; users can clone and customize them in Markdown.
* **Timeline construction** – Chronological aggregation of deduplicated events, with support for manual annotation and export to PDF/Markdown.
* **Extensible architecture** – Workers run as asynchronous multiprocess tasks; new parsers or tools are added via a plugin interface.

The system is deliberately modular: the front‑end (React) communicates with a FastAPI back‑end over HTTPS/WSS, which persists data in PostgreSQL 15 + PGVector. All LLM interactions occur through a configurable inference endpoint (OpenAI, Ollama, Azure OpenAI, etc.) and are limited to tool selection and response generation; no model is hosted within the repository.


## Visual Overview

| Feature | Thumbnail (click to enlarge) |
|---------|------------------------------|
| **Chat** | [![Chat](docs/img/chat-thumb.png)](docs/img/chat.png) |
| **Events** | [![Events](docs/img/events-thumb.png)](docs/img/events.png) |
| **Timeline** | [![Timeline](docs/img/timeline-thumb.png)](docs/img/timeline.png) |
| **Report** | [![Report](docs/img/report-thumb.png)](docs/img/report.png) |
| **Logging** | [![Logging](docs/img/logging-thumb.png)](docs/img/logging.png) |
| **Playbooks** | [![Playbooks](docs/img/playbooks-thumb.png)](docs/img/playbooks.png) |
| **Configure** | [![Playbooks](docs/img/configure-thumb.png)](docs/img/configure.png) |

---

## Quick Start

```bash
git clone https://github.com/eheuser/open-agent-investigation.git
cd open-agent-investigation
docker compose up -d
```

The UI becomes available at `https://localhost`. Default credentials are:

* **Username:** admin  
* **Password:** admin123  

> **Note:** This project is under active development. See the [Roadmap](ROADMAP.md) for planned features.

---

## Core Features

### 1. Intelligent Query Routing
| Handler | Typical Use‑Case | Operation |
|--------|------------------|-----------|
| **Agent Handler** | Multi‑step investigations (e.g., credential dumping) | Executes a playbook, invokes parsers, aggregates results, updates timeline |
| **Augmented Search** | Semantic retrieval of events (e.g., “any suspicious logons”) | Expands query, performs hybrid BM25 + vector search, synthesises findings |
| **Timeline Handler** | Direct manipulation of the evidence timeline | Query, insert, edit, or delete entries; export to report formats |
| **General Metadata** | Quick statistics (event count, artifact list) | Reads investigation metadata without invoking parsers |

Routing is performed by an LLM‑based intent classifier; manual selection is also supported.

### 2. Artifact Processing
* **Archive handling:** Automatic extraction of nested archives up to 5 levels deep (max 10 GB, 50 000 files). Path information is encoded in filenames (`Windows__System32__Security.evtx`).
* **Supported Windows artifacts** – EVTX logs, Registry hives, $MFT, Prefetch, LNK shortcuts, Jump Lists, Chrome/Firefox/Edge histories, scheduled tasks, SRUM, Windows Search index, and generic file metadata (hashes, entropy, strings, PE headers). See `api/worker/parsers/README.md` for the full list.
* **Parsing stack:** Rust‑based EVTX parser, Regipy, MFT parser, prefetch2es, LnkParse3, olefile, pyesedb, and custom SQLite adapters.

### 3. Evidence Timeline
* Events are stored once; timeline entries reference source IDs to avoid duplication.
* Automatic deduplication across artifact types.
* Annotations can be added manually or programmatically by playbooks.
* Export options: PDF (via WeasyPrint) and Markdown.

### 4. Playbook Engine
* **Built‑in library:** 20+ MITRE ATT&CK‑aligned playbooks covering Initial Access, Execution, Persistence, Privilege Escalation, Defense Evasion, Credential Access, Discovery, Lateral Movement, Collection, Exfiltration, and Impact.
* **Customization:** Clone any playbook, edit steps in Markdown, enable/disable per investigation.
* **Execution model:** Bounded turn‑based system (quick = 3 turns, standard = 6, thorough = 9; dynamic up to 30 with justification). Each turn may invoke up to five tool calls.

### 5. Reporting
* One‑click generation of comprehensive reports that include timeline entries, raw event excerpts, and playbook rationale.
* Reports are versioned alongside the investigation for auditability.

---

## Installation Details

### Prerequisites
| Component | Minimum Version |
|-----------|-----------------|
| Docker & Docker Compose | 20.10 / 2.0 |
| LLM endpoint (OpenAI, Ollama, Azure) | – |
| RAM | 4 GB (8 GB recommended) |
| Disk space | 20 GB for artifacts + database |

### Deployment
```bash
docker compose up -d          # Start nginx, API, worker, PostgreSQL
```

#### Post‑deployment configuration
1. **Login** with the default credentials.
2. **Configure LLM endpoint** under *Settings → LLM* (API key, model name, temperature, etc.).
3. **Create an investigation**, upload artifacts, and begin querying.

### Testing
```bash
docker compose -f docker-compose.test.yml run --rm test-runner pytest tests/unit/ -v --tb=short
```

---

## Architecture Diagram

```
User Browser <--HTTPS/WSS--> nginx (443) <--HTTP--> FastAPI (8000)
                                   |                     |
                               Static UI          Worker (asyncio)
                                                    |
                                                PostgreSQL 15 + PGVector
                                                    |
                                               LLM Inference Endpoint
```

* **UI:** React 18, TypeScript, TailwindCSS  
* **Proxy:** nginx with self‑signed TLS (replace with trusted cert in production)  
* **API:** FastAPI 0.110, async SQLAlchemy ORM, JWT authentication (24 h expiry)  
* **Worker:** Multiprocessing pool handling parsing jobs and playbook execution  
* **Database:** PostgreSQL 15, PGVector for embedding storage, pg_crypto for encrypted API keys  
* **LLM Backend:** Configurable; supports OpenAI, Ollama, Azure OpenAI, or any compatible endpoint  

All inter‑process communication occurs over HTTP/HTTPS; no direct socket exposure of the worker.

---

## Security Model

| Aspect | Implementation |
|--------|----------------|
| **Authentication** | JWT tokens signed with RSA‑2048; Argon2id password hashing (memory‑hard) |
| **Authorization** | Role‑based access control (admin, regular user) enforced at API layer |
| **Transport security** | TLS for all inbound/outbound traffic (nginx termination) |
| **Data protection** | API keys encrypted with `pg_crypto`; no plaintext passwords stored |
| **Input sanitisation** | Parameterised queries via SQLAlchemy; prepared statements prevent injection |
| **Isolation** | Workers run in separate containers; artifact processing confined to a non‑privileged user |

---

## Contributing

Contributions are encouraged. Areas of interest include:

* New parsers for additional Windows or cross‑platform artifacts
* Expansion of the playbook library (technique‑specific investigations)
* Enhancements to the retrieval pipeline (indexing, ranking)
* Documentation improvements and example investigations
* Security hardening and audit logging

Please read `CONTRIBUTING.md` for workflow guidelines and code standards. Security vulnerabilities must be reported privately via `SECURITY.md`.

---

## Community & Support

* **Documentation:** `docs/` – Getting Started, User Guide, Playbooks, Architecture, API reference
* **Discussions:** GitHub Discussions (link)
* **Issue Tracker:** GitHub Issues (link)
* **Security Reports:** `SECURITY.md`

---

## License

GNU General Public License v3.0 – see `LICENSE`.

--- 

*Star the repository if you find it useful and consider contributing to advance forensic automation.*