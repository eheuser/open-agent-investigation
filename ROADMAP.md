
# LLM/RAG/Agent

**Streamline Chat Routing**

- Too many steps, slower on local LLM's

**Re-Ranker and Config**

- Add an optional re-ranker model.
- Add max-context length for embedding and re-ranker model

**Enhance Investigation Choices**

- Offer suggestions on where to take the investigation next

**Add Parallel Connections Option**

- Add checkbox for each API endpoint
- Allow parallel API connections to speed up processing for API endpoints that allow it (e.g. local API server vs public & paid)

**Reports**

- Add report profiles/playbooks
- Clean up prompts and output

---

# Forensics

**Expanded Artifact Support**

- PE's, ELF< Mach-O>
- Flat Files (apache logs, one entry per line)
- Binary Files
- PCAP and PCAPNG files
- PLASO output
- Velociraptor target
- Extract artifacts automatically from .E01, .dd, etc

**Expand OS Support**

- Linux
- Mac

---

# UI/UX

**Chat**

- When agent is active, auto-scroll is too grabby
- Allow cancelling of jobs from Jobs Queue modal
- Add Report profile placeholder previews
- Add new users from admin account
- For onboarding, make sure the settings screen is the first the user sees when no llm is configured
- Add instructions to the llm config screen

**Analysis Views**

Provide computed analysis views to get the agents and user started on an investigation.

- Autorun list
- Evidence of Execution list
- Browsed URLs list
- Service list
- Logon list
- Registry Viewer/Explorer
- MFT Viewer/Explorer

# Agents

**File Analysis**

- PE, ELF and Mach-O disassembly and analysis
- Document/PDF analysis
- Binary (any other file) analysis
- Threat Intelligence gathering

**Executable Agent**

- Disassembler (headless Ghidra? Radare? Capstone?)

**Binary Agent**

- Hashes
- Entropy
- Strings
- Magic/Header analysis
- Embedded file extraction and analysis
- Custom XOR and other tools

**Threat Intel Agent**

- WHOIS query
- Resolve Domains -> IP
- Web Search
- API integrations w/user supplied API key (VT, PassiveTotal/RiskIQ)
