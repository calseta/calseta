.PHONY: dev dev-up dev-logs logs test lint typecheck migrate ci build help ui-install ui-dev ui-build

# Inline script to apply procrastinate's schema (stored procedures + tables)
define APPLY_PROCRASTINATE_SCHEMA
import asyncio
from app.queue.registry import procrastinate_app
async def _apply():
    async with procrastinate_app.open_async():
        await procrastinate_app.schema_manager.apply_schema_async()
asyncio.run(_apply())
endef
export APPLY_PROCRASTINATE_SCHEMA

# Default target
help:
	@echo "Calseta AI — available targets:"
	@echo "  dev        Start services: build, migrate, then docker compose up"
	@echo "  dev-up     Start services without running migrations (faster restart)"
	@echo "  test       Run pytest test suite"
	@echo "  lint       Run ruff linter"
	@echo "  typecheck  Run mypy type checker"
	@echo "  migrate    Apply pending Alembic migrations (requires running db)"
	@echo "  ci         Run lint + typecheck + test (same as GitHub Actions)"
	@echo "  dev-logs   Start all services + Dozzle log viewer (http://localhost:9999)"
	@echo "  logs       Open Dozzle log viewer in browser"
	@echo "  build      Build production Docker image"
	@echo "  ui-install Install UI dependencies"
	@echo "  ui-dev     Start UI dev server (port 5173, proxies API to 8000)"
	@echo "  ui-build   Build UI for production"

# Full startup: build, wait for DB, migrate, then start all services
dev:
	docker compose up -d db
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	docker compose run --rm api alembic upgrade head
	docker compose run --rm api python -c "$$APPLY_PROCRASTINATE_SCHEMA"
	docker compose up

# Quick restart (skip migration — useful after code changes)
dev-up:
	docker compose up

# Full startup + Dozzle log viewer (http://localhost:9999)
dev-logs:
	docker compose --profile dev-tools up -d db dozzle
	@echo "Waiting for PostgreSQL to be ready..."
	@until docker compose exec db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	docker compose run --rm api alembic upgrade head
	docker compose run --rm api python -c "$$APPLY_PROCRASTINATE_SCHEMA"
	docker compose --profile dev-tools up

# Open Dozzle in browser (macOS)
logs:
	@open http://localhost:9999 2>/dev/null || echo "Dozzle: http://localhost:9999"

test:
	pytest tests/ -v; STATUS=$$?; [ $$STATUS -eq 5 ] && exit 0 || exit $$STATUS

lint:
	ruff check app/ tests/

typecheck:
	mypy app/ tests/

# Run inside docker: docker compose run --rm api alembic upgrade head
migrate:
	alembic upgrade head

# Runs the same sequence as GitHub Actions CI
ci: lint typecheck test

build:
	docker build --target prod -t calseta .

# UI targets
ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build
