# ============================================================
# Calseta AI — Multi-stage Dockerfile
#
# Targets:
#   dev  — local development with hot reload and dev deps
#   prod — production image, no dev tools, non-root user
#
# Build prod:   docker build --target prod -t calseta-api .
# ============================================================

# ============================================================
# Base: shared system dependencies
# ============================================================
FROM python:3.12-slim AS base

WORKDIR /app

# libpq-dev: needed by asyncpg build
# gcc: C compiler for native extensions
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Dev: installs all deps including dev; editable install for
# hot reload of source changes via mounted volume
# ============================================================
FROM base AS dev

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Source copied last — in dev, the volume mount overrides this
COPY . .

# ============================================================
# Prod: production-only deps, no dev tools, non-root user
# ============================================================
FROM base AS prod

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application source
COPY app/ app/

# Copy Alembic config if present (optional — only needed for
# containers that run migrations)
COPY alembic.ini* ./
COPY alembic/ alembic/ 2>/dev/null || true

# Run as non-root
RUN useradd --system --no-create-home --shell /bin/false calseta
USER calseta
