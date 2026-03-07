#!/bin/sh
# Combined initialization script for OAI
# Handles volume permissions and SSL certificate generation
# Runs once as root, then auto-removes

set -e

echo "========================================="
echo "OAI - System Initialization"
echo "========================================="

# ============================================
# Volume Permissions Setup
# ============================================
echo ""
echo "[1/2] Setting up volume permissions..."

echo "  → /data/investigations (UID 1000:1000)"
mkdir -p /data/investigations
chown -R 1000:1000 /data/investigations
chmod -R 755 /data/investigations

echo "  → /data/postgres (UID 999:999)"
mkdir -p /data/postgres
chown -R 999:999 /data/postgres
chmod -R 700 /data/postgres

echo "  ✓ Volume permissions configured"

# ============================================
# SSL Certificate Generation
# ============================================
echo ""
echo "[2/2] SSL certificate setup..."

if [ -f /certs/server.key ] && [ -f /certs/server.crt ]; then
    echo "  ✓ Existing certificates found:"
    echo "    - /certs/server.key"
    echo "    - /certs/server.crt"
    echo "  Skipping generation."
else
    echo "  → Generating new SSL certificates..."
    
    # Ensure openssl is available
    if ! command -v openssl >/dev/null 2>&1; then
        echo "  → Installing openssl..."
        apk add --no-cache openssl >/dev/null 2>&1
    fi
    
    # Generate 4096-bit RSA private key
    openssl genrsa -out /certs/server.key 4096 2>/dev/null
    
    # Generate self-signed certificate valid for 365 days
    openssl req -new -x509 -sha256 -key /certs/server.key \
        -out /certs/server.crt -days 365 \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1" 2>/dev/null
    
    echo "  ✓ Certificates generated:"
    echo "    - /certs/server.key (4096-bit RSA)"
    echo "    - /certs/server.crt (self-signed, 365 days)"
fi

# Set proper permissions for nginx user (UID 101)
chown -R 101:101 /certs
chmod 755 /certs
chmod 644 /certs/server.crt
chmod 640 /certs/server.key

echo "  ✓ Certificate permissions set for nginx (UID 101)"

# ============================================
# Initialization Complete
# ============================================
echo ""
echo "========================================="
echo "✓ Initialization complete"
echo "========================================="
