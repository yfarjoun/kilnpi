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

# Deploy frontend to Pi (build + rsync + restart)
deploy-frontend host='kilnpi':
    cd frontend && npm run build
    @echo "Deploying to {{ host }}:~/kilnpi/frontend/dist ..."
    rsync -avz --delete frontend/dist/ {{ host }}:~/kilnpi/frontend/dist/
    ssh {{ host }} "systemctl --user restart kilnpi.service"
    @echo "Done."

# Deploy everything: git pull on Pi + rebuild frontend + restart
deploy host='kilnpi':
    cd frontend && npm run build
    rsync -avz --delete frontend/dist/ {{ host }}:~/kilnpi/frontend/dist/
    ssh {{ host }} "cd ~/kilnpi && git pull && systemctl --user restart kilnpi.service"
    @echo "Done."

# Restart the service on the Pi
restart host='kilnpi':
    ssh {{ host }} "systemctl --user restart kilnpi.service"

# Show service status on the Pi
status host='kilnpi':
    ssh {{ host }} "systemctl --user status kilnpi.service"

# Tail service logs on the Pi
logs host='kilnpi':
    ssh {{ host }} "journalctl --user -u kilnpi.service -f"

# --- CI (mirrors GitHub Actions) ---

# Run the full CI pipeline locally
ci: install
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy backend/
    uv run pytest --tb=short
    cd frontend && npm run lint
    cd frontend && npm run build
