# LLM Configuration Guide

This guide covers both automated (file-based) and manual (UI-based) LLM configuration for Open Agent Investigation.

## Table of Contents

- [Overview](#overview)
- [Automated Configuration](#automated-configuration)
- [Manual UI Configuration](#manual-ui-configuration)
- [Provider-Specific Examples](#provider-specific-examples)
- [Embedding Configuration](#embedding-configuration)
- [Advanced Parameters](#advanced-parameters)
- [Troubleshooting](#troubleshooting)

---

## Overview

Open Agent Investigation requires an LLM provider to function. You can configure this in two ways:

1. **Automated (Recommended for Production)**: Use a `.llm_config.env` file that is applied on container startup
2. **Manual (Recommended for Development)**: Configure via the Settings page in the UI

Both methods configure the same underlying settings and can be used interchangeably.

---

## Automated Configuration

### Quick Start

```bash
# 1. Copy the example configuration file
cp .llm_config.env.example .llm_config.env

# 2. Edit with your provider settings
nano .llm_config.env

# 3. Start the system (config applied automatically)
docker compose up -d
```

### Configuration File Structure

The `.llm_config.env` file uses standard environment variable syntax:

```bash
# Basic LLM Configuration
LLM_PROVIDER_NAME=openai
LLM_API_ENDPOINT=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-your-api-key-here
LLM_MODEL_NAME=gpt-4o-mini
LLM_MAX_CONTEXT_LENGTH=128000
LLM_TEMPERATURE=0.70

# Embedding Configuration (Optional - for RAG)
EMBEDDING_PROVIDER=openai
EMBEDDING_API_URL=https://api.openai.com/v1/embeddings
EMBEDDING_API_KEY=sk-your-api-key-here
EMBEDDING_MODEL_NAME=text-embedding-3-small
```

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| `LLM_PROVIDER_NAME` | Provider identifier | `openai`, `ollama`, `azure`, `anthropic` |
| `LLM_API_ENDPOINT` | Full API URL | `https://api.openai.com/v1/chat/completions` |
| `LLM_MODEL_NAME` | Model to use | `gpt-4o-mini`, `llama3.1:70b` |

### Optional Fields

| Field | Default | Description |
|-------|---------|-------------|
| `LLM_API_KEY` | (none) | API key (not required for local Ollama) |
| `LLM_MAX_CONTEXT_LENGTH` | 8192 | Maximum tokens per request |
| `LLM_TEMPERATURE` | 0.70 | Sampling temperature (0.0-2.0) |
| `LLM_TOP_P` | (none) | Nucleus sampling (0.0-1.0) |
| `LLM_TOP_K` | (none) | Top-k sampling (integer) |
| `LLM_MIN_P` | (none) | Min-p sampling (0.0-1.0) |
| `LLM_TIMEOUT` | 300 | Request timeout (seconds) |
| `LLM_ALLOW_CONCURRENT` | false | Enable parallel LLM calls |

### How It Works

1. On container startup, the API container checks for `/app/.llm_config.env`
2. If found, the `apply_llm_config.py` script parses the file
3. Configuration is applied to the admin user's active LLM config
4. If a config already exists, it is updated (not duplicated)
5. The API server starts normally after configuration is applied

### Security Best Practices

**DO:**
- ✅ Keep `.llm_config.env` secret (it's in `.gitignore` by default)
- ✅ Use environment-specific files (`.llm_config.prod.env`, `.llm_config.dev.env`)
- ✅ Rotate API keys regularly
- ✅ Use read-only file permissions: `chmod 400 .llm_config.env`

**DON'T:**
- ❌ Commit `.llm_config.env` to version control
- ❌ Share the file in public channels
- ❌ Use production API keys in development environments

### Updating Configuration

To update the configuration:

```bash
# 1. Edit the file
nano .llm_config.env

# 2. Restart the API container
docker compose restart api

# Configuration is reapplied on startup
```

---

## Manual UI Configuration

### First-Time Setup

1. Navigate to `https://localhost` and login with default credentials:
   - Username: `admin`
   - Password: `admin123`

2. You will be automatically redirected to the Settings page

3. Fill in the LLM configuration form:
   - **Provider Name**: Identifier for your provider (e.g., `openai`)
   - **API Endpoint**: Full URL to the chat completions endpoint
   - **API Key**: Your provider's API key (optional for local models)
   - **Model Name**: Model identifier (e.g., `gpt-4o-mini`)
   - **Max Context Length**: Token limit for your model
   - **Temperature**: Sampling temperature (0.0 = deterministic, 2.0 = creative)

4. (Optional) Configure embedding settings for RAG/semantic search

5. Click **Save Configuration**

### Updating Configuration

1. Navigate to Settings → LLM Configuration
2. Modify any fields
3. Click **Save Configuration**
4. Changes take effect immediately

### Multiple Configurations

You can create multiple LLM configurations and switch between them:

1. Create a new configuration (Settings → Add New Configuration)
2. Only one configuration can be active at a time
3. Toggle the "Active" switch to change the active configuration

---

## Provider-Specific Examples

### OpenAI

```bash
LLM_PROVIDER_NAME=openai
LLM_API_ENDPOINT=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-proj-...your-key-here
LLM_MODEL_NAME=gpt-4o-mini
LLM_MAX_CONTEXT_LENGTH=128000
LLM_TEMPERATURE=0.70

# Embedding configuration
EMBEDDING_PROVIDER=openai
EMBEDDING_API_URL=https://api.openai.com/v1/embeddings
EMBEDDING_API_KEY=sk-proj-...your-key-here
EMBEDDING_MODEL_NAME=text-embedding-3-small
EMBEDDING_MAX_CONTEXT_LENGTH=8192
RERANKER_MODEL_NAME=text-embedding-3-large
```

**Notes:**
- API key starts with `sk-proj-` (project keys) or `sk-` (legacy keys)
- Context lengths: `gpt-4o-mini` = 128k, `gpt-4o` = 128k, `o1` = 200k
- Embedding models: `text-embedding-3-small` (1536 dims), `text-embedding-3-large` (3072 dims)

### Ollama (Local)

```bash
LLM_PROVIDER_NAME=ollama
LLM_API_ENDPOINT=http://localhost:11434/v1/chat/completions
LLM_API_KEY=  # Leave empty for local Ollama
LLM_MODEL_NAME=llama3.1:70b
LLM_MAX_CONTEXT_LENGTH=32768
LLM_TEMPERATURE=0.70

# Embedding configuration (local)
EMBEDDING_PROVIDER=ollama
EMBEDDING_API_URL=http://localhost:11434/api/embeddings
EMBEDDING_API_KEY=  # Leave empty
EMBEDDING_MODEL_NAME=nomic-embed-text
EMBEDDING_MAX_CONTEXT_LENGTH=8192
```

**Notes:**
- Ollama must be running on the host: `ollama serve`
- Use `host.docker.internal` instead of `localhost` on macOS/Windows
- Pull models first: `ollama pull llama3.1:70b`, `ollama pull nomic-embed-text`
- Context lengths vary by model (check with `ollama show <model>`)

### Azure OpenAI

```bash
LLM_PROVIDER_NAME=azure
LLM_API_ENDPOINT=https://<resource-name>.openai.azure.com/openai/deployments/<deployment-name>/chat/completions?api-version=2024-02-15-preview
LLM_API_KEY=your-azure-api-key
LLM_MODEL_NAME=gpt-4o-mini  # Your deployment name
LLM_MAX_CONTEXT_LENGTH=128000
LLM_TEMPERATURE=0.70

# Embedding configuration
EMBEDDING_PROVIDER=azure
EMBEDDING_API_URL=https://<resource-name>.openai.azure.com/openai/deployments/<embedding-deployment>/embeddings?api-version=2024-02-15-preview
EMBEDDING_API_KEY=your-azure-api-key
EMBEDDING_MODEL_NAME=text-embedding-3-small
```

**Notes:**
- Replace `<resource-name>` with your Azure resource name
- Replace `<deployment-name>` with your model deployment name
- API version may change (check Azure docs)
- API key is found in Azure Portal → Keys and Endpoint

### Anthropic Claude

```bash
LLM_PROVIDER_NAME=anthropic
LLM_API_ENDPOINT=https://api.anthropic.com/v1/messages
LLM_API_KEY=sk-ant-...your-key-here
LLM_MODEL_NAME=claude-3-5-sonnet-20241022
LLM_MAX_CONTEXT_LENGTH=200000
LLM_TEMPERATURE=0.70

# Note: Anthropic does not provide embeddings
# Use OpenAI or another provider for embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_API_URL=https://api.openai.com/v1/embeddings
EMBEDDING_API_KEY=sk-...separate-key-here
EMBEDDING_MODEL_NAME=text-embedding-3-small
```

**Notes:**
- API key starts with `sk-ant-`
- Context lengths: Claude 3.5 Sonnet = 200k tokens
- Anthropic does not offer embedding models (use OpenAI/Cohere/Ollama)

### Custom Provider

```bash
LLM_PROVIDER_NAME=custom
LLM_API_ENDPOINT=https://your-custom-endpoint.com/v1/chat/completions
LLM_API_KEY=your-custom-api-key
LLM_MODEL_NAME=your-model-name
LLM_MAX_CONTEXT_LENGTH=8192
LLM_TEMPERATURE=0.70
```

**Notes:**
- Endpoint must be OpenAI-compatible (same request/response format)
- Examples: LM Studio, LocalAI, vLLM, text-generation-webui
- Test compatibility with `curl` before configuring

---

## Embedding Configuration

Embeddings enable semantic search and RAG (Retrieval-Augmented Generation) features. This is **optional** but recommended for large investigations.

### Why Use Embeddings?

- **Semantic Search**: Find events by meaning, not just keywords
- **Better Recall**: Retrieve relevant events even with different wording
- **Reranking**: Improve result quality with two-stage retrieval

### Configuration

```bash
# Embedding provider (required for RAG)
EMBEDDING_PROVIDER=openai

# Embedding API endpoint
EMBEDDING_API_URL=https://api.openai.com/v1/embeddings

# API key (can be same as LLM_API_KEY for OpenAI)
EMBEDDING_API_KEY=sk-your-api-key-here

# Model for initial embedding generation
EMBEDDING_MODEL_NAME=text-embedding-3-small
EMBEDDING_MAX_CONTEXT_LENGTH=8192

# Optional: Reranker model for improved relevance
RERANKER_MODEL_NAME=text-embedding-3-large
RERANKER_MAX_CONTEXT_LENGTH=8192

# Enable concurrent embedding calls (faster but higher cost/rate limits)
EMBEDDING_ALLOW_CONCURRENT=false
```

### Embedding Model Selection

| Provider | Model | Dimensions | Cost (per 1M tokens) | Use Case |
|----------|-------|------------|----------------------|----------|
| OpenAI | `text-embedding-3-small` | 1536 | $0.02 | General use (recommended) |
| OpenAI | `text-embedding-3-large` | 3072 | $0.13 | High accuracy, reranking |
| Cohere | `embed-english-v3.0` | 1024 | $0.10 | English-only investigations |
| Ollama | `nomic-embed-text` | 768 | Free | Local/offline use |
| Ollama | `mxbai-embed-large` | 1024 | Free | Better accuracy (local) |

### Reranking

Reranking is a two-stage retrieval process:

1. **Stage 1**: Use a fast, cheap model to retrieve top 100 candidates
2. **Stage 2**: Use a more expensive model to rerank top 20 results

**When to use reranking:**
- ✅ Large investigations (>1M events)
- ✅ Complex queries requiring high precision
- ✅ Budget allows for higher API costs

**When to skip reranking:**
- ❌ Small investigations (<100k events)
- ❌ Simple keyword queries
- ❌ Cost-sensitive deployments

---

## Advanced Parameters

### Temperature

Controls randomness in LLM responses:

- `0.0` - Deterministic (same answer every time)
- `0.7` - Balanced (recommended for investigations)
- `1.0` - Creative
- `2.0` - Very creative (not recommended)

**Recommendation**: Use `0.7` for investigations (good balance of consistency and flexibility)

### Top-p (Nucleus Sampling)

Limits token selection to the smallest set with cumulative probability ≥ top-p:

- `0.9` - Conservative (recommended)
- `0.95` - Moderate
- `1.0` - No filtering

**Recommendation**: Use `0.9` or leave unset (provider default)

### Top-k Sampling

Limits token selection to the top-k most probable tokens:

- `40` - Conservative
- `50` - Moderate (recommended)
- `100` - Permissive

**Recommendation**: Leave unset unless provider requires it (Ollama, some custom models)

### Min-p Sampling

Minimum probability threshold for token inclusion:

- `0.05` - Recommended for most use cases
- `0.1` - More conservative

**Recommendation**: Leave unset unless using custom models

### Timeout

Maximum time to wait for LLM response:

- `300` - Default (5 minutes)
- `600` - For slow models or complex queries
- `60` - For fast models with strict SLAs

**Recommendation**: Use default unless experiencing timeouts

### Concurrent Calls

Enable parallel LLM requests for faster processing:

```bash
LLM_ALLOW_CONCURRENT=true
EMBEDDING_ALLOW_CONCURRENT=true
```

**Pros:**
- ✅ Faster processing (2-5x speedup)
- ✅ Better resource utilization

**Cons:**
- ❌ Higher API costs (more tokens processed)
- ❌ Risk of hitting rate limits
- ❌ Harder to debug (parallel execution)

**Recommendation**: Enable only if you have high rate limits and need speed

---

## Troubleshooting

### Configuration Not Applied

**Symptom**: Settings page still shows "No configuration found" after restart

**Solutions:**
1. Check file location: `docker compose exec api ls -la /app/.llm_config.env`
2. Check file permissions: `chmod 644 .llm_config.env`
3. Check logs: `docker compose logs api | grep "LLM configuration"`
4. Verify syntax: No spaces around `=`, no trailing spaces

### API Key Invalid

**Symptom**: "Invalid API key" error in logs

**Solutions:**
1. Verify API key is correct (no extra spaces/newlines)
2. Check key has not expired
3. Verify key has correct permissions (OpenAI: project keys need "Write" access)
4. Test key manually: `curl -H "Authorization: Bearer $API_KEY" ...`

### Model Not Found

**Symptom**: "Model not found" or "404" error

**Solutions:**
1. Verify model name is correct (case-sensitive)
2. For Azure: Use deployment name, not model name
3. For Ollama: Pull model first (`ollama pull <model>`)
4. Check provider documentation for available models

### Timeout Errors

**Symptom**: Requests timing out after 5 minutes

**Solutions:**
1. Increase timeout: `LLM_TIMEOUT=600`
2. Reduce context length: `LLM_MAX_CONTEXT_LENGTH=32768`
3. Use a faster model (e.g., `gpt-4o-mini` instead of `o1`)
4. Check network connectivity to provider

### Rate Limit Errors

**Symptom**: "Rate limit exceeded" errors

**Solutions:**
1. Disable concurrent calls: `LLM_ALLOW_CONCURRENT=false`
2. Reduce worker count: `NUM_WORKERS=4` in docker-compose.yml
3. Upgrade API tier with provider
4. Add retry logic (built-in for most providers)

### Embedding Errors

**Symptom**: Semantic search not working, embedding jobs failing

**Solutions:**
1. Verify embedding configuration is complete
2. Check embedding API key is valid
3. Verify model name is correct
4. Check embedding model context length matches data
5. Review logs: `docker compose logs embedding-worker`

### Connection Refused (Ollama)

**Symptom**: "Connection refused" when using local Ollama

**Solutions:**
1. Use `host.docker.internal` instead of `localhost` on macOS/Windows
2. On Linux, use `--network host` or expose Ollama on `0.0.0.0`
3. Verify Ollama is running: `ollama list`
4. Test connectivity: `docker compose exec api curl http://host.docker.internal:11434/api/tags`

---

## Further Reading

- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference)
- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Azure OpenAI Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- [Anthropic API Documentation](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- [Getting Started Guide](getting-started.md)
- [Architecture Documentation](architecture.md)

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../README.md).
