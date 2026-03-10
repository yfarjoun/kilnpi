# Default: list available recipes
default:
    @just --list

# --- Dev ---

# Run backend dev server (auto-reload)
dev-backend:
    uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Run frontend dev server
dev-frontend:
    cd frontend && npm run dev

# --- Lint & Test ---

# Run all checks (lint + test)
check: lint test

# Run ruff linter and formatter check
lint:
    uv run ruff check .
    uv run ruff format --check .
    cd frontend && npm run lint

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix .
    uv run ruff format .

# Run mypy type checking
typecheck:
    uv run mypy backend/

# Run backend tests
test *args='':
    uv run pytest {{ args }}

# --- Build ---

# Build frontend for production
build:
    cd frontend && npm run build

# Install all dependencies (backend + frontend)
install:
    uv sync --extra dev
    cd frontend && npm ci

# --- Deploy ---

# Build frontend for production (output lands in frontend/dist/, served live)
deploy-frontend:
    cd frontend && npm run build
    @echo "Done. Refresh the browser to pick up changes."

# Pull latest code, rebuild frontend, restart service
deploy:
    git pull
    cd frontend && npm run build
    systemctl --user restart kilnpi.service
    @echo "Done."

# Restart the service
restart:
    systemctl --user restart kilnpi.service

# Show service status
status:
    systemctl --user status kilnpi.service

# Tail service logs
logs:
    journalctl --user -u kilnpi.service -f

# --- CI (mirrors GitHub Actions) ---

# Run the full CI pipeline locally
ci: install
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy backend/
    uv run pytest --tb=short
    cd frontend && npm run lint
    cd frontend && npm run build
