.PHONY: dev dev-up dev-down test lint typecheck migrate ci build help seed-sandbox lab lab-reset lab-stop docs-openapi docs-openapi-check

# Inline script to apply procrastinate's schema (idempotent — ignores "already exists")
define APPLY_PROCRASTINATE_SCHEMA
import asyncio, sys
from app.queue.registry import procrastinate_app
async def _apply():
    try:
        async with procrastinate_app.open_async():
            await procrastinate_app.schema_manager.apply_schema_async()
    except Exception as e:
        if "already exists" in str(e):
            print("Procrastinate schema already applied — skipping.")
        else:
            raise
asyncio.run(_apply())
endef
export APPLY_PROCRASTINATE_SCHEMA

# Default target
help:
	@echo "Calseta — available targets:"
	@echo "  dev        Start all services (API + worker + MCP + DB + UI)"
	@echo "  dev-up     Restart services without migrations (faster)"
	@echo "  dev-down   Stop all services"
	@echo "  test       Run pytest test suite"
	@echo "  lint       Run ruff linter"
	@echo "  typecheck  Run mypy type checker"
	@echo "  migrate    Apply pending Alembic migrations (requires running db)"
	@echo "  ci         Run lint + typecheck + test (same as GitHub Actions)"
	@echo "  build      Build production Docker image"
	@echo ""
	@echo "Docs:"
	@echo "  docs-openapi       Generate openapi.json and copy to docs repo"
	@echo "  docs-openapi-check Verify openapi.json matches current API surface"
	@echo ""
	@echo "Lab:"
	@echo "  lab        Start fully seeded lab (5 alerts, enriched, full-access key)"
	@echo "  lab-reset  Wipe DB and re-seed lab from scratch"
	@echo "  lab-stop   Stop lab services"

# Full startup: build, wait for DB, migrate, start backend + UI
dev:
	docker compose up -d db
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	docker compose run --rm api alembic upgrade head
	docker compose run --rm api python -c "$$APPLY_PROCRASTINATE_SCHEMA" || true
	@echo "Starting backend services..."
	docker compose up -d api worker mcp
	@echo ""
	@echo "Starting UI dev server..."
	@cd ui && npm install --silent 2>/dev/null && nohup npm run dev > /dev/null 2>&1 &
	@echo ""
	@echo "=== Calseta running ==="
	@echo "  API:  http://localhost:8000"
	@echo "  MCP:  http://localhost:8001"
	@echo "  UI:   http://localhost:5173"
	@echo ""
	@echo "Run 'make dev-down' to stop everything."
	@echo "Run 'docker compose logs -f' to tail logs."

# Quick restart (skip migrations — useful after code changes)
dev-up:
	docker compose up -d api worker mcp db
	@cd ui && nohup npm run dev > /dev/null 2>&1 &

# Stop everything
dev-down:
	docker compose down
	@-pkill -f "vite" 2>/dev/null || true

test:
	pytest tests/ -v --ignore=tests/integration; STATUS=$$?; [ $$STATUS -eq 5 ] && exit 0 || exit $$STATUS

# Integration tests (requires running PostgreSQL via TEST_DATABASE_URL or DATABASE_URL)
test-integration:
	pytest tests/integration/ -v

lint:
	ruff check app/ tests/

typecheck:
	mypy app/ tests/

migrate:
	alembic upgrade head

ci: lint typecheck test

build:
	docker build --target prod -t calseta .

seed-sandbox:
	python -m app.cli.seed_sandbox

# ---------------------------------------------------------------------------
# OpenAPI spec — generate from FastAPI app and sync to docs repo
# ---------------------------------------------------------------------------

# Generate openapi.json from the FastAPI app (no running server needed)
# Writes to file directly to avoid structlog output mixing with JSON on stdout
docs-openapi:
	@python -c "import json, sys, os; os.environ['LOG_LEVEL']='CRITICAL'; from app.main import create_app; f=open('openapi.json','w'); json.dump(create_app().openapi(), f, indent=2); f.write('\n'); f.close()" 2>/dev/null
	@echo "Generated openapi.json"
	@if [ -d "../docs" ]; then cp openapi.json ../docs/openapi.json && echo "Copied to ../docs/openapi.json"; fi

# CI check: fail if openapi.json is stale
docs-openapi-check:
	@python -c "import json, os; os.environ['LOG_LEVEL']='CRITICAL'; from app.main import create_app; f=open('/tmp/openapi-fresh.json','w'); json.dump(create_app().openapi(), f, indent=2); f.write('\n'); f.close()" 2>/dev/null
	@diff openapi.json /tmp/openapi-fresh.json > /dev/null 2>&1 || (echo "openapi.json is stale. Run: make docs-openapi" && exit 1)
	@echo "openapi.json is up to date."

# ---------------------------------------------------------------------------
# Lab environment — fully seeded instance for demos and testing
# ---------------------------------------------------------------------------

# Start lab: DB + migrations + seed + all services + UI
lab:
	@echo "Setting lab environment..."
	@if [ ! -f .env ]; then cp .env.lab.example .env; echo "Created .env from .env.lab.example"; else echo ".env already exists, skipping copy"; fi
	docker compose up -d db
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	docker compose run --rm api alembic upgrade head
	docker compose run --rm api python -c "$$APPLY_PROCRASTINATE_SCHEMA" || true
	docker compose run --rm -e SANDBOX_MODE=true -e ENRICHMENT_MOCK_MODE=true api python -m app.cli.seed_sandbox
	@echo "Starting backend services..."
	docker compose up -d api worker mcp
	@cd ui && npm install --silent 2>/dev/null && nohup npm run dev > /dev/null 2>&1 &
	@echo ""
	@echo "=== Calseta Lab ==="
	@echo "  API:  http://localhost:8000"
	@echo "  MCP:  http://localhost:8001"
	@echo "  UI:   http://localhost:5173"
	@echo ""
	@echo "  Lab API Key: cai_lab_demo_full_access_key_not_for_prod"
	@echo ""
	@echo "  Try: curl -H 'Authorization: Bearer cai_lab_demo_full_access_key_not_for_prod' http://localhost:8000/v1/alerts"
	@echo ""
	@echo "Run 'make lab-stop' to stop everything."
	@echo "Run 'docker compose logs -f' to tail logs."

# Wipe everything and re-seed from scratch
lab-reset:
	docker compose down -v
	$(MAKE) lab

# Stop lab services
lab-stop:
	docker compose down
	@-pkill -f "vite" 2>/dev/null || true
