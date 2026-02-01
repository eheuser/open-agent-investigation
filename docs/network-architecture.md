# Network Architecture

This document explains the network configuration and port mappings for Open Agent Investigation.

## Overview

Open Agent Investigation uses an **nginx reverse proxy** architecture where all external traffic flows through a single HTTPS endpoint. The API is NOT directly accessible from outside the Docker network.

## Port Mappings

### Production (Docker Compose)

| Service | Internal Port | External Port | Protocol | Access |
|---------|---------------|---------------|----------|--------|
| nginx (UI) | 443 | 443 | HTTPS | Public |
| API | 8000 | - | HTTP | Internal only |
| PostgreSQL | 5432 | 5432 | TCP | Public (dev only) |

**External Access**:
- **UI**: `https://localhost` (port 443)
- **API Docs**: `https://localhost/api/docs` (proxied through nginx)
- **WebSocket**: `wss://localhost/api/v1/chat/ws/{id}` (proxied through nginx)

**Internal Docker Network**:
- API accessible at `http://api:8000` (service name resolution)
- Database accessible at `postgresql://db:5432`

### Development Mode

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| Vite Dev Server | 5173 | HTTP | http://localhost:5173 |
| API | 8000 | HTTP | http://localhost:8000 |
| PostgreSQL | 5432 | TCP | localhost:5432 |

**Direct Access** (no nginx):
- **UI**: `http://localhost:5173` (Vite dev server)
- **API Docs**: `http://localhost:8000/docs`
- **WebSocket**: `ws://localhost:8000/api/v1/chat/ws/{id}`

## nginx Configuration

The nginx reverse proxy (`ui/nginx.conf`) handles:

1. **Static File Serving**: Serves React UI from `/usr/share/nginx/html`
2. **API Proxying**: Forwards `/api/*` requests to `api:8000`
3. **WebSocket Proxying**: Upgrades connections for `/api/v1/chat/ws/*`
4. **SSL/TLS Termination**: Handles HTTPS with self-signed certificates

### Proxy Rules

```nginx
# API requests
location /api/ {
    set $upstream api:8000;
    proxy_pass http://$upstream;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}

# WebSocket connections
location /api/v1/chat/ws/ {
    set $upstream api:8000;
    proxy_pass http://$upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "Upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

## Why This Architecture?

### Benefits

1. **Single Entry Point**: All traffic flows through port 443 (HTTPS)
2. **SSL/TLS Termination**: nginx handles certificates, API stays simple
3. **Security**: API not directly exposed to network
4. **Simplified Deployment**: No CORS issues, consistent URLs
5. **Load Balancing**: Can scale API containers behind nginx
6. **Static File Optimization**: nginx serves UI files efficiently

### Trade-offs

1. **Additional Layer**: Adds nginx as dependency
2. **Debugging**: Harder to test API directly (must go through proxy)
3. **Port Conflicts**: Port 443 must be available

## Testing Connectivity

### Docker Compose Mode

```bash
# Test UI (should return HTML)
curl -k https://localhost

# Test API health endpoint
curl -k https://localhost/api/health

# Test API docs (should return OpenAPI JSON)
curl -k https://localhost/api/openapi.json

# Test WebSocket (requires wscat)
npm install -g wscat
wscat -c "wss://localhost/api/v1/chat/ws/{investigation_id}?token={jwt_token}" --no-check
```

### Development Mode

```bash
# Test UI (Vite dev server)
curl http://localhost:5173

# Test API health endpoint
curl http://localhost:8000/health

# Test API docs
curl http://localhost:8000/openapi.json

# Test WebSocket
wscat -c "ws://localhost:8000/api/v1/chat/ws/{investigation_id}?token={jwt_token}"
```

## Troubleshooting

### "Connection Refused" on Port 8000

**Cause**: API is not exposed on port 8000 in Docker Compose mode.

**Solution**: Use nginx proxy at `https://localhost/api/` instead.

### "SSL Certificate Error"

**Cause**: Using self-signed certificate.

**Solution**: Accept certificate in browser or use `-k` flag with curl:
```bash
curl -k https://localhost/api/health
```

### "502 Bad Gateway"

**Cause**: nginx can't reach API container.

**Diagnosis**:
```bash
# Check if API is running
docker compose ps api

# Check API logs
docker compose logs api

# Check nginx logs
docker compose logs ui
```

**Solution**:
```bash
# Restart API
docker compose restart api

# Rebuild if code changed
docker compose build api
docker compose up -d api
```

### WebSocket Connection Failed

**Cause**: WebSocket upgrade not working through proxy.

**Diagnosis**:
```bash
# Check nginx WebSocket config
docker compose exec ui cat /etc/nginx/nginx.conf | grep -A 10 "ws/"

# Check nginx error logs
docker compose logs ui | grep error
```

**Solution**: Verify nginx.conf has correct WebSocket proxy settings (see above).

## Environment Variables

### UI (.env.local)

```bash
# Docker Compose mode
VITE_API_URL=https://localhost
VITE_WS_URL=wss://localhost

# Development mode
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

### API (docker-compose.yml)

```yaml
environment:
  DATABASE_URL: postgresql+asyncpg://postgres:example@db/open_agent_inv
  API_HOST: api  # Docker service name
  API_PORT: 8000  # Internal port
```

### Worker (docker-compose.yml)

```yaml
environment:
  DATABASE_URL: postgresql+asyncpg://postgres:example@db/open_agent_inv
  API_HOST: api  # For WebSocket callbacks
  API_PORT: 8000  # Internal port
```

## Production Deployment

For production deployments, replace self-signed certificates with real SSL certificates:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/nginx/ssl/fullchain.pem;  # Let's Encrypt
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    
    # ... rest of config
}
```

Or use a load balancer (AWS ALB, nginx Ingress, Traefik) for SSL termination.

## Further Reading

- [Getting Started Guide](getting-started.md) - Installation and setup
- [Architecture Overview](architecture.md) - System design
- [API Documentation](../api/README.md) - API reference
- [UI Documentation](../ui/README.md) - Frontend reference

---

**Questions?** Open an issue on GitHub or check the main [README](../README.md).
