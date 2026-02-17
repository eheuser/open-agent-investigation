FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY . .

RUN npm run build

FROM nginx:alpine
# Replace default config with our proxy-aware version
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# Install openssl for certificate generation
RUN apk add --no-cache openssl bash

# Create entrypoint script for certificate handling
RUN mkdir -p /etc/nginx/ssl && \
    echo '#!/bin/bash' > /docker-entrypoint.sh && \
    echo 'set -e' >> /docker-entrypoint.sh && \
    echo '' >> /docker-entrypoint.sh && \
    echo '# Check if certificates exist in mounted volume' >> /docker-entrypoint.sh && \
    echo 'if [ ! -f /certs/server.key ] || [ ! -f /certs/server.crt ]; then' >> /docker-entrypoint.sh && \
    echo '  echo "SSL certificates not found in /certs, generating new ones..."' >> /docker-entrypoint.sh && \
    echo '  openssl genrsa -out /certs/server.key 4096' >> /docker-entrypoint.sh && \
    echo '  openssl req -new -x509 -sha256 -key /certs/server.key \' >> /docker-entrypoint.sh && \
    echo '    -out /certs/server.crt -days 365 \' >> /docker-entrypoint.sh && \
    echo '    -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=localhost" \' >> /docker-entrypoint.sh && \
    echo '    -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"' >> /docker-entrypoint.sh && \
    echo '  echo "SSL certificates generated successfully"' >> /docker-entrypoint.sh && \
    echo 'else' >> /docker-entrypoint.sh && \
    echo '  echo "Using existing SSL certificates from /certs"' >> /docker-entrypoint.sh && \
    echo 'fi' >> /docker-entrypoint.sh && \
    echo '' >> /docker-entrypoint.sh && \
    echo '# Copy certificates to nginx ssl directory' >> /docker-entrypoint.sh && \
    echo 'cp /certs/server.crt /etc/nginx/ssl/server.crt' >> /docker-entrypoint.sh && \
    echo 'cp /certs/server.key /etc/nginx/ssl/server.key' >> /docker-entrypoint.sh && \
    echo '' >> /docker-entrypoint.sh && \
    echo '# Set proper permissions' >> /docker-entrypoint.sh && \
    echo 'chmod 644 /etc/nginx/ssl/server.crt' >> /docker-entrypoint.sh && \
    echo 'chmod 600 /etc/nginx/ssl/server.key' >> /docker-entrypoint.sh && \
    echo '' >> /docker-entrypoint.sh && \
    echo '# Start nginx' >> /docker-entrypoint.sh && \
    echo 'exec nginx -g "daemon off;"' >> /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh

EXPOSE 443
CMD ["/docker-entrypoint.sh"]
