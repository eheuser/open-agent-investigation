#!/bin/bash
# Entrypoint script for OAI API container
# Applies LLM configuration from .llm_config.env before starting the API

set -e  # Exit on error

echo "========================================="
echo "Open Agent Investigation - API Startup"
echo "========================================="

# Apply LLM configuration if .llm_config.env exists
if [ -f "/app/.llm_config.env" ]; then
    echo "Found .llm_config.env, applying configuration..."
    python /app/scripts/apply_llm_config.py --config-file /app/.llm_config.env
    
    if [ $? -eq 0 ]; then
        echo "✓ LLM configuration applied successfully"
    else
        echo "⚠ Failed to apply LLM configuration (non-fatal)"
    fi
else
    echo "No .llm_config.env found, skipping auto-configuration"
    echo "You will need to configure LLM settings via the UI"
fi

echo "========================================="
echo "Starting API server..."
echo "========================================="

# Execute the main command (passed as arguments to this script)
exec "$@"
