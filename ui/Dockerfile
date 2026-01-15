FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

# Generate SSL certificates if they don't exist
RUN apk add --no-cache openssl && \
    mkdir -p certs && \
    if [ ! -f certs/server.key ] || [ ! -f certs/server.crt ]; then \
      echo "Generating SSL certificates..."; \
      openssl genrsa -out certs/server.key 4096 && \
      openssl req -new -x509 -sha256 -key certs/server.key \
        -out certs/server.crt -days 365 \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"; \
    else \
      echo "Using existing SSL certificates"; \
    fi

RUN npm run build

FROM nginx:alpine
# Replace default config with our proxy-aware version
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy SSL certificates
RUN mkdir -p /etc/nginx/ssl
COPY --from=builder /app/certs/server.crt /etc/nginx/ssl/server.crt
COPY --from=builder /app/certs/server.key /etc/nginx/ssl/server.key

# Set proper permissions for SSL certificates
RUN chmod 644 /etc/nginx/ssl/server.crt && \
    chmod 600 /etc/nginx/ssl/server.key

EXPOSE 443
CMD ["nginx", "-g", "daemon off;"]
