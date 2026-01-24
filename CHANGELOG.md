# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release
- Windows artifact parsing (EVTX, Registry, MFT, Prefetch, LNK)
- LLM-powered agent with 16+ forensic tools
- Query routing system (Agent, Timeline, RAG, General Chat)
- Evidence timeline builder
- PDF and Markdown report generation
- Semantic search with hybrid BM25 + vector retrieval
- Docker-based deployment
- Comprehensive test suite
- CI/CD workflows

### Security
- JWT authentication with 24-hour expiration
- Argon2id password hashing
- API key encryption at rest
- SQL injection prevention
- Input validation

## [0.1.0] - TBD

Initial release.

---

## Release Types

- **Major** (x.0.0): Breaking changes
- **Minor** (0.x.0): New features, backwards compatible
- **Patch** (0.0.x): Bug fixes, backwards compatible

## Categories

- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security improvements
