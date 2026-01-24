.PHONY: help install dev test lint format clean docker-build docker-up docker-down docker-logs

# Default target
help:
	@echo "Open Agent Investigation - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install        Install all dependencies"
	@echo "  make dev            Start development environment"
	@echo ""
	@echo "Testing:"
	@echo "  make test           Run all tests"
	@echo "  make test-backend   Run backend tests only"
	@echo "  make test-frontend  Run frontend tests only"
	@echo "  make coverage       Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           Run all linters"
	@echo "  make format         Format code (black, isort)"
	@echo "  make type-check     Run type checkers"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   Build Docker images"
	@echo "  make docker-up      Start Docker services"
	@echo "  make docker-down    Stop Docker services"
	@echo "  make docker-logs    View Docker logs"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove build artifacts"
	@echo "  make clean-all      Remove all generated files"

# Installation
install:
	@echo "Installing backend dependencies..."
	cd api && pip install -r requirements.txt -r requirements-test-minimal.txt
	@echo "Installing frontend dependencies..."
	cd ui && npm ci
	@echo "Done!"

# Development
dev:
	@echo "Starting development environment..."
	docker compose up -d

# Testing
test:
	@echo "Running all tests..."
	docker compose -f docker-compose.test.yml run --rm test-runner pytest tests/ -v

test-backend:
	@echo "Running backend tests..."
	cd api && pytest tests/ -v

test-frontend:
	@echo "Building frontend (test)..."
	cd ui && npm run build

coverage:
	@echo "Running tests with coverage..."
	docker compose -f docker-compose.test.yml run --rm test-runner \
		pytest tests/ -v --cov=app --cov-report=html --cov-report=term

# Code Quality
lint:
	@echo "Running linters..."
	@echo "Backend:"
	cd api && ruff check app/ tests/
	cd api && black --check app/ tests/
	cd api && isort --check-only app/ tests/
	@echo "Frontend:"
	cd ui && npx tsc --noEmit

format:
	@echo "Formatting code..."
	cd api && black app/ tests/
	cd api && isort app/ tests/
	@echo "Done!"

type-check:
	@echo "Running type checkers..."
	cd api && mypy app/ --ignore-missing-imports
	cd ui && npx tsc --noEmit

# Docker
docker-build:
	@echo "Building Docker images..."
	docker compose build

docker-up:
	@echo "Starting Docker services..."
	docker compose up -d

docker-down:
	@echo "Stopping Docker services..."
	docker compose down

docker-logs:
	@echo "Viewing Docker logs..."
	docker compose logs -f

# Cleanup
clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf api/htmlcov api/coverage.xml api/.coverage
	rm -rf ui/dist ui/node_modules/.cache
	@echo "Done!"

clean-all: clean
	@echo "Removing all generated files..."
	rm -rf ui/node_modules
	rm -rf api/venv api/env
	docker compose down -v
	@echo "Done!"
