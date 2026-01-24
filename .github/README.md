# GitHub Configuration

This directory contains GitHub-specific configuration files for Open Agent Investigation.

## Workflows

### CI/CD Pipelines

- **`ci.yml`**: Main CI pipeline
  - Backend tests with Docker Compose
  - Backend linting (ruff, black, isort, mypy)
  - Frontend build and TypeScript checks
  - Security scanning (Trivy, Bandit)
  - Docker image builds
  
- **`codeql.yml`**: CodeQL security analysis
  - Runs on push/PR to main/develop
  - Weekly scheduled scans
  - Analyzes Python and JavaScript
  
- **`release.yml`**: Release automation
  - Triggered on version tags (v*.*.*)
  - Creates GitHub releases
  - Builds and pushes Docker images to GHCR
  - Multi-platform builds (amd64, arm64)

### Automation

- **`stale.yml`**: Marks inactive issues/PRs as stale
  - Issues: 60 days inactive → stale, 7 days → close
  - PRs: 30 days inactive → stale, 14 days → close
  
- **`labeler.yml`**: Auto-labels PRs based on changed files

## Issue Templates

- **`bug_report.yml`**: Structured bug reports
- **`feature_request.yml`**: Feature suggestions

## Pull Request Template

- **`PULL_REQUEST_TEMPLATE.md`**: Standardized PR format

## Dependabot

- **`dependabot.yml`**: Automated dependency updates
  - Python dependencies (weekly)
  - npm dependencies (weekly)
  - Docker base images (weekly)
  - GitHub Actions (weekly)

## Labels

Auto-applied labels:
- `backend`, `frontend`, `database`
- `documentation`, `tests`, `docker`
- `ci/cd`, `dependencies`, `agent`, `parsers`
- `security`, `stale`

## Secrets Required

Configure these in repository settings:

- `CODECOV_TOKEN`: (Optional) For code coverage reports
- `GITHUB_TOKEN`: Automatically provided by GitHub

## Branch Protection

Recommended settings for `main` branch:

- Require PR reviews (1+ approvals)
- Require status checks to pass:
  - Backend Tests
  - Backend Linting
  - Frontend Tests & Build
  - Security Scan
  - Docker Build
- Require branches to be up to date
- Require signed commits (recommended)
- Include administrators

## Release Process

1. Update version in relevant files
2. Update `CHANGELOG.md`
3. Create and push tag: `git tag v0.1.0 && git push origin v0.1.0`
4. GitHub Actions automatically:
   - Creates release
   - Builds Docker images
   - Publishes to GHCR

## Maintenance

- Review Dependabot PRs weekly
- Triage new issues within 48 hours
- Review stale issues monthly
- Update workflows as needed
