# Getting Started

This guide covers installation, system requirements, and initial configuration for Open Agent Investigation.

## System Requirements

### Minimum Requirements

- CPU: 2 cores
- RAM: 4 GB
- Storage: 20 GB available space
- Operating System: Linux, macOS, or Windows with WSL2

### Recommended Requirements

- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- Operating System: Linux (Ubuntu 20.04+ or similar)

### Software Dependencies

- Docker 20.10 or later
- Docker Compose 2.0 or later
- Git (for cloning the repository)
- LLM Backend: OpenAI API key, Ollama, or compatible endpoint

## Installation Methods

### Docker Installation (Recommended)

Docker provides the simplest installation path with all dependencies bundled.

#### Step 1: Install Docker

Follow the official Docker installation guide for your operating system:

- Linux: https://docs.docker.com/engine/install/
- macOS: https://docs.docker.com/desktop/install/mac-install/
- Windows: https://docs.docker.com/desktop/install/windows-install/

Verify installation:

```bash
docker --version
docker compose --version
```

#### Step 2: Clone Repository

```bash
git clone https://github.com/eheuser/open-agent-investigation.git
cd open-agent-investigation
```

#### Step 3: Start Services

```bash
docker compose up -d
```

This starts four services:
- `db` - PostgreSQL 15 with PGVector extension
- `api` - FastAPI backend server
- `worker` - Asynchronous job processor
- `ui` - React frontend served by nginx

#### Step 4: Verify Installation

Check service status:

```bash
docker compose ps
```

All services should show "Up" status.

Access the application:
- UI: https://localhost (accept self-signed certificate warning)
- API: http://localhost:8000/docs (Swagger documentation)
- Health check: http://localhost:8000/health

#### Step 5: Login

Default credentials (change immediately):
- Username: `admin`
- Password: `admin123`

#### Step 6: Configure LLM and (optional) Embeddings

Before adding artifacts or creating investigations you will need to configure the inference API.
* Click the username in the lower left corner of the screen and select `Settings`.
* Defaults are provided that will connect to the docker hosting machine (usually your laptop).
* You will need to configure the LLM API at a minimum in order to use the application. The embedding configuration is optional, but will disable the RAG functionality.

**Note** If you configure an embedding API and model, be sure to select the `Embedding Provider` or the RAG functionality will remain disabled.

![image](./img/configure.png)

**Note** Tested settings for API, local is usable with gpt-oss-20b and a small embedding model.

### Manual Installation

Manual installation is recommended for development or when Docker is not available.

#### Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- PostgreSQL 15 with PGVector extension

#### Backend Setup

```bash
cd api

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost/open_agent_inv"
export JWT_SECRET="your-secret-key-here"

# Initialize database
psql -U postgres -d open_agent_inv -f db/schema.sql

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Worker Setup

In a separate terminal:

```bash
cd api
source venv/bin/activate

# Start worker
python -m worker.main
```

#### Frontend Setup

In a separate terminal:

```bash
cd ui

# Install dependencies
npm install

# Start development server
npm run dev
```

Access at http://localhost:5173

## Initial Configuration

### LLM Provider Setup

Before asking questions, configure an LLM provider:

1. Navigate to **Settings** in the UI
2. Click **LLM Configuration**
3. Fill in provider details:

#### OpenAI Configuration

```
Provider Name: openai
API Endpoint: https://api.openai.com/v1/chat/completions
API Key: sk-your-api-key-here
Model Name: gpt-4o
Max Context Length: 128000
Temperature: 0.7
```

#### Ollama Configuration (Local)

```
Provider Name: ollama
API Endpoint: http://host.docker.internal:11434/v1/chat/completions
API Key: (leave empty)
Model Name: llama3
Max Context Length: 131072
Temperature: 0.7
```

#### Embedding Configuration (for RAG mode)

```
Embedding Provider: openai
Embedding API URL: https://api.openai.com/v1/embeddings
Embedding API Key: sk-your-api-key-here
Embedding Model: text-embedding-ada-002
```

4. Click **Save Configuration**
5. Set as active configuration

### User Management

#### Create Additional Users

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "analyst1",
    "password": "secure-password-here",
    "role": 0
  }'
```

Role values:
- 0: Regular user
- 1: Administrator

#### Change Default Password

```bash
# Via psql
docker compose exec db psql -U postgres -d open_agent_inv

UPDATE users
SET password_hash = crypt('new-password', gen_salt('bf'))
WHERE username = 'admin';
```

## Verification Steps

### Test Database Connection

```bash
docker compose exec api python -c "
from app.core.database import engine
import asyncio
asyncio.run(engine.connect())
print('Database connection successful')
"
```

### Test LLM Connection

```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "investigation_id": "550e8400-e29b-41d4-a716-446655440000",
    "question": "Test connection",
    "mode": "general_chat"
  }'
```

### Test Artifact Upload

1. Create investigation in UI
2. Click **Upload Artifacts**
3. Drag and drop a `.evtx` file
4. Verify parsing job completes successfully

## Troubleshooting

### Port Conflicts

If ports 8000, 5432, or 443 are already in use:

```bash
# Modify docker-compose.yml
ports:
  - "8001:8000"  # Change API port
  - "5433:5432"  # Change database port
  - "8443:443"   # Change UI port
```

### Database Connection Errors

```bash
# Check database is running
docker compose ps db

# View database logs
docker compose logs db

# Restart database
docker compose restart db
```

### API Not Starting

```bash
# View API logs
docker compose logs api

# Check for Python errors
docker compose exec api python -c "import app.main"
```

### Worker Not Processing Jobs

```bash
# View worker logs
docker compose logs worker

# Check worker is running
docker compose ps worker

# Restart worker
docker compose restart worker
```

## Next Steps

- [Quickstart Guide](quickstart.md) - Run your first investigation
- [User Guide](user-guide.md) - Learn common workflows
- [Architecture](architecture.md) - Understand system design
- [Configuration Reference](reference/configuration.md) - Detailed configuration options