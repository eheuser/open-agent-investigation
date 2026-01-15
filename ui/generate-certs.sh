#!/bin/bash

# Script to generate self-signed SSL certificates for HTTPS

CERTS_DIR="./certs"

# Create certs directory if it doesn't exist
if [ ! -d "$CERTS_DIR" ]; then
    echo "Creating certs directory..."
    mkdir -p "$CERTS_DIR"
fi

# Check if certificates already exist
if [ -f "$CERTS_DIR/server.key" ] && [ -f "$CERTS_DIR/server.crt" ]; then
    echo "SSL certificates already exist in $CERTS_DIR"
    echo "If you want to regenerate them, please delete the existing files first."
    exit 0
fi

echo "Generating new RSA private key and self-signed certificate..."

# Generate RSA private key (4096 bits for better security)
openssl genrsa -out "$CERTS_DIR/server.key" 4096

# Generate self-signed certificate valid for 365 days
openssl req -new -x509 -sha256 -key "$CERTS_DIR/server.key" \
    -out "$CERTS_DIR/server.crt" -days 365 \
    -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

# Set appropriate permissions
chmod 600 "$CERTS_DIR/server.key"
chmod 644 "$CERTS_DIR/server.crt"

echo "✓ SSL certificates generated successfully!"
echo "  - Private key: $CERTS_DIR/server.key"
echo "  - Certificate: $CERTS_DIR/server.crt"
echo ""
echo "Note: This is a self-signed certificate. Browsers will show a security warning."
echo "For production, use certificates from a trusted Certificate Authority."
