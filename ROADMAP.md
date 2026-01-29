
# LLM/RAG/Agent

**Streamline Chat Routing**

- Too many steps, slower on local LLM's

**Re-Ranker and Config**

- Add an optional re-ranker model.
- Add max-context length for embedding and re-ranker model

**Enhance Investigation Choices**

- Offer suggestions on where to take the investigation next
- Create Mutable Investigation Templates the user can execute to "get started"

**Add Parallel Connections Option**

- Add checkbox for each API endpoint
- Allow parallel API connections to speed up processing for API endpoints that allow it (e.g. local API server vs public & paid)

**Reports**

- Add report profiles
- Clean up prompts and output

---

# Forensics

**Expanded Windows Artifact Support**

- Scheduled Tasks
- SRUM DB
- CryptNetURL Cache
- Automatic Destination Jump List
- Browser History (Edge, Chrome, Opera, Firefox)
- PCA Launch Items
- Windows PE's
- Flat Files (apache logs, one entry per line)
- Binary Files
- PCAP and PCAPNG files

**Expand OS Support**

- Linux
- Mac

**Threat Intel Agent**

- WHOIS query
- Resolve Domains -> IP
- Web Search
- API integrations w/user supplied API key (VT, PassiveTotal/RiskIQ)

---

# UI/UX

**Chat**

- When agent is active, auto-scroll is too grabby
- Allow cancelling of jobs from Jobs Queue modal
- Add Report profile placeholder previews
- Add new users from admin account