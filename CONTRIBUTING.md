# Contributing to Open Agent Investigation

First off, thank you for considering contributing to Open Agent Investigation! It's people like you that make this tool better for the digital forensics community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Ways to Contribute

- **Report bugs**: Found a bug? Let us know by opening an issue
- **Suggest features**: Have an idea? We'd love to hear it
- **Write documentation**: Help improve our docs
- **Fix bugs**: Check out open issues labeled `bug`
- **Implement features**: Look for issues labeled `enhancement`
- **Improve tests**: Help us achieve better test coverage
- **Review PRs**: Help review and test pull requests

### First-Time Contributors

Look for issues labeled `good first issue` or `help wanted`. These are great starting points!

## Development Setup

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+
- Node.js 18+
- Git

### Local Development Environment

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/YOUR_USERNAME/open-agent-investigation.git
   cd open-agent-investigation
   ```

2. **Set up the backend**

   ```bash
   cd api
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-test-minimal.txt
   ```

3. **Set up the frontend**

   ```bash
   cd ui
   npm install
   ```

4. **Start development services**

   ```bash
   docker compose up -d
   ```

5. **Run the application**

   - Backend: `cd api && uvicorn app.main:app --reload`
   - Frontend: `cd ui && npm run dev`

### Running Tests

#### Backend Tests

```bash
# Using Docker Compose (recommended)
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# Or locally
cd api
pytest tests/ -v --cov=app
```

#### Frontend Tests

```bash
cd ui
npm run build  # Verify build succeeds
npx tsc --noEmit  # Type checking
```

#### Linting

```bash
# Backend
cd api
ruff check app/ tests/
black --check app/ tests/
isort --check-only app/ tests/

# Frontend
cd ui
npx tsc --noEmit
```

## How to Contribute

### Reporting Bugs

Before creating a bug report:

1. **Check existing issues** to avoid duplicates
2. **Verify the bug** exists in the latest version
3. **Collect information**:
   - Version/commit hash
   - Operating system
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs or screenshots

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) when creating an issue.

### Suggesting Features

Before suggesting a feature:

1. **Check existing feature requests** to avoid duplicates
2. **Ensure it aligns** with project goals (forensic investigation)
3. **Describe the use case** clearly

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml).

### Code Contributions

1. **Find an issue** to work on or create one
2. **Comment on the issue** to let others know you're working on it
3. **Fork the repository**
4. **Create a feature branch**: `git checkout -b feature/your-feature-name`
5. **Make your changes** following our coding standards
6. **Write/update tests** for your changes
7. **Update documentation** as needed
8. **Commit your changes** with clear commit messages
9. **Push to your fork**: `git push origin feature/your-feature-name`
10. **Open a pull request** using our PR template

## Coding Standards

### Python (Backend)

- **Style Guide**: PEP 8
- **Formatter**: Black (line length: 100)
- **Linter**: Ruff
- **Import Sorting**: isort (Black profile)
- **Type Hints**: Use type hints where appropriate
- **Async/Await**: Use async patterns for I/O operations
- **Docstrings**: Google-style docstrings for public functions/classes

#### Example

```python
from typing import Optional

async def get_event_by_id(event_id: int) -> Optional[dict]:
    """Retrieve an event by its ID.
    
    Args:
        event_id: The unique identifier of the event
        
    Returns:
        Event data dictionary if found, None otherwise
        
    Raises:
        DatabaseError: If database connection fails
    """
    # Implementation here
    pass
```

### TypeScript (Frontend)

- **Style Guide**: Airbnb TypeScript style guide
- **Formatter**: Prettier (via Vite)
- **Type Safety**: Strict TypeScript configuration
- **Components**: Functional components with hooks
- **Props**: Always define prop types

#### Example

```typescript
interface EventCardProps {
  eventId: number;
  timestamp: string;
  eventType: string;
  onSelect?: (id: number) => void;
}

export const EventCard: React.FC<EventCardProps> = ({ 
  eventId, 
  timestamp, 
  eventType,
  onSelect 
}) => {
  // Implementation here
};
```

### General Guidelines

- **Keep it simple**: Prefer clarity over cleverness
- **DRY principle**: Don't repeat yourself
- **SOLID principles**: Follow object-oriented design principles
- **Error handling**: Always handle errors gracefully
- **Security first**: Validate inputs, sanitize outputs
- **Performance**: Consider performance implications
- **Comments**: Explain *why*, not *what*

## Testing Guidelines

### Test Coverage

- Aim for **80%+ code coverage**
- **Unit tests**: Test individual functions/components
- **Integration tests**: Test component interactions
- **End-to-end tests**: Test complete workflows

### Test Structure

```python
# Backend test example
def test_event_retrieval_success():
    """Test successful event retrieval."""
    # Arrange
    event_id = 1
    
    # Act
    result = get_event_by_id(event_id)
    
    # Assert
    assert result is not None
    assert result["id"] == event_id
```

### Test Naming

- Use descriptive names: `test_<function>_<scenario>_<expected_result>`
- Examples:
  - `test_login_with_valid_credentials_returns_token`
  - `test_parse_evtx_with_corrupted_file_raises_error`

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements

### Examples

```
feat(agent): add timeline search tool

Implement new tool for searching timeline entries with
support for date ranges and event type filtering.

Closes #123
```

```
fix(parser): handle corrupted EVTX files gracefully

Previously, corrupted EVTX files would crash the parser.
Now we catch the exception and log a warning.

Fixes #456
```

## Pull Request Process

1. **Update documentation** for any user-facing changes
2. **Add/update tests** to maintain coverage
3. **Ensure all tests pass** locally
4. **Update CHANGELOG.md** if applicable
5. **Fill out the PR template** completely
6. **Request review** from maintainers
7. **Address feedback** promptly and professionally
8. **Keep PR focused**: One feature/fix per PR

### PR Review Criteria

- Code quality and style compliance
- Test coverage and quality
- Documentation completeness
- No breaking changes (unless discussed)
- Security considerations
- Performance impact

### After PR Approval

- **Squash commits** if requested
- **Rebase on main** if needed
- Maintainers will merge when ready

## Community

### Getting Help

- **GitHub Discussions**: Ask questions, share ideas
- **Issues**: Report bugs, request features
- **Documentation**: Check docs first

### Recognition

Contributors are recognized in:

- GitHub contributors list
- Release notes for significant contributions
- Special thanks in documentation

### License

By contributing, you agree that your contributions will be licensed under the project's [GPL-3.0 License](LICENSE).

---

## Questions?

Don't hesitate to ask! Open an issue with the `question` label or start a discussion.

Thank you for contributing to Open Agent Investigation!
