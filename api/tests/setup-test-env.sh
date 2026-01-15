#!/bin/bash
# Bash script to set up test environment
# Run this from the api/tests directory

echo "Setting up test environment..."

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "WARNING: Not in a virtual environment!"
    echo "Consider running: python -m venv venv && source venv/bin/activate"
    echo ""
fi

# Install main dependencies
echo "Installing main dependencies..."
cd ..
pip install -r requirements.txt

# Install test dependencies
echo "Installing test dependencies..."
cd tests
pip install -r requirements-test.txt

echo ""
echo "Setup complete!"
echo "You can now run tests with: pytest -v"
