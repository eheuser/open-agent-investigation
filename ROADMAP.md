
# LLM/RAG/Agent

**Streamline Chat Routing**

- Too many steps, slower on local LLM's

**Enhance Investigation Choices**

- Offer suggestions on where to take the investigation next

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


## Replace existing installation with new (upgrades only supported with full releases)

```shell
docker compose down
docker volume rm oai-pg-data
git pull
docker compose up --build -d
```