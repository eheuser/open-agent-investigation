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

#### Step 5: Login

Default credentials (change immediately):
- Username: `admin`
- Password: `admin123`

#### Step 6: Configure LLM Provider (Required)

On first login, you will be automatically redirected to Settings to configure your LLM provider. This is required before you can use the system.

**LLM Configuration (Required):**
1. Navigate to Settings (or you'll be redirected automatically)
2. Click **+ Add Configuration**
3. Fill in LLM provider details:
   - Provider Name: `local`, `openai`, etc.
   - Provider Type: Select from dropdown (OpenAI, Google, Anthropic, Localhost, etc.)
   - API Endpoint: Auto-populated based on type, or enter custom URL
   - Model Name: e.g., `gpt-4o`, `llama3`, etc.
   - API Key: Required for internet providers (OpenAI, Anthropic, etc.)
   - Max Context Length, Temperature, Timeout
4. Click **Test Settings** - Must pass before saving
5. Click **Create** to save configuration

**Embedding Configuration (Optional - for RAG features):**

Embeddings enable semantic search via "Augmented Chat" mode. This is completely optional:

1. Scroll to "Embedding Configuration" section
2. Select **Embedding Provider Type** (OpenAI, Cohere, Ollama, etc.)
3. Fill in embedding fields:
   - Embedding Provider: `openai`, `cohere`, `ollama`
   - Embedding API URL: Auto-populated or custom
   - Embedding Model: e.g., `text-embedding-3-small`
   - Embedding API Key: Required for internet providers
4. *Optional*: Configure **Reranker Model** for improved relevance (e.g., `text-embedding-3-large`)
5. Click **Test Settings** - Tests both LLM and embedding if configured
6. Click **Create** to save

**Important:**
- LLM configuration is **required** - system will not function without it
- Embedding configuration is **optional** - only needed for RAG features
- Without embeddings, "Augmented Chat" mode will be disabled
- You can test and save with only LLM configured (embeddings can be added later)
- If you start filling embedding fields, all required fields must be completed

![image](./img/configure.png)

**Tested Configurations:**
- **LM Studio (local)**: `gpt-oss-20b` for LLM, `nomic-embed-text` for embeddings
- **OpenAI**: `gpt-4o` for LLM, `text-embedding-3-small` for embeddings
- **Ollama (local)**: `llama3` for LLM, `nomic-embed-text` for embeddings

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

# Start API server (accessible at http://localhost:8000 in development)
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

#### Embedding Configuration (Optional - for RAG mode)

```
Embedding Provider: openai
Embedding Provider Type: OpenAI
Embedding API URL: https://api.openai.com/v1/embeddings
Embedding API Key: sk-your-api-key-here
Embedding Model: text-embedding-3-small
Embedding Max Tokens: 8192
Reranker Model: (optional) text-embedding-3-large
Reranker Max Tokens: 8192
```

**Note:** Embedding configuration is optional. If not configured:
- "Augmented Chat" mode will be disabled in mode selector
- All other features (Agent, Timeline, General Chat) work normally
- You can add embedding configuration later

4. Click **Test Settings** (tests LLM, and embedding if configured)
5. Click **Save Configuration**
6. Set as active configuration

### User Management

#### Create Additional Users

```bash
# Via API (development mode)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{

# Via nginx proxy (Docker Compose mode)
curl -k -X POST https://localhost/api/v1/auth/register \
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
# Development mode
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \

# Docker Compose mode (via nginx proxy)
curl -k -X POST https://localhost/api/v1/chat/ask \
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