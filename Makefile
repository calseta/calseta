.PHONY: dev test lint typecheck migrate ci build help

# Default target
help:
	@echo "Calseta AI — available targets:"
	@echo "  dev        Start all services with docker compose (hot reload)"
	@echo "  test       Run pytest test suite"
	@echo "  lint       Run ruff linter"
	@echo "  typecheck  Run mypy type checker"
	@echo "  migrate    Apply pending Alembic migrations"
	@echo "  ci         Run lint + typecheck + test (same as GitHub Actions)"
	@echo "  build      Build production Docker image"

dev:
	docker compose up

test:
	pytest tests/ -v; STATUS=$$?; [ $$STATUS -eq 5 ] && exit 0 || exit $$STATUS

lint:
	ruff check app/ tests/

typecheck:
	mypy app/

migrate:
	alembic upgrade head

# Runs the same sequence as GitHub Actions CI
ci: lint typecheck test

build:
	docker build --target prod -t calseta .
