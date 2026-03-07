#!/bin/bash
# Helper script to clean up init container after startup
# Run this after 'docker compose up -d' to remove the completed init container

echo "Cleaning up init container..."
docker rm oai-init 2>/dev/null && echo "✓ Removed oai-init container" || echo "✓ Init container already removed"
