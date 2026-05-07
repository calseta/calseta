# ============================================================
# Calseta — Multi-stage Dockerfile
#
# Targets:
#   dev  — local development with hot reload and dev deps
#   prod — production image, no dev tools, non-root user
#
# Build prod:   docker build --target prod -t calseta-api .
# ============================================================

# ============================================================
# UI Build: Node.js stage to build the admin panel
# ============================================================
FROM node:22-alpine AS ui-build

WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ .
RUN npm run build

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

# Claude Code CLI for the `claude_code` LLM provider (subscription billing,
# no API key). Only baked into dev — production deployments configure an API
# provider (anthropic / openai / azure_openai) instead.
#   - bubblewrap + socat: claude CLI's optional sandbox tooling. Without them
#     the CLI prints a "Sandbox disabled" warning on every invocation.
#   - Node 20 LTS: required by @anthropic-ai/claude-code.
# Login state lives at /root/.claude — mounted as a named volume in
# docker-compose.yml so it survives container rebuilds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        bubblewrap \
        socat \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Source copied last — in dev, the volume mount overrides this
COPY . .

# ============================================================
# Prod: production-only deps, no dev tools, non-root user
# ============================================================
FROM base AS prod

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Copy source first — pip install needs the package
COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir .

# Copy Alembic config and migrations (needed for containers that run migrations)
COPY alembic.ini* ./
COPY alembic/ alembic/

# Copy built UI from Node.js stage
COPY --from=ui-build /ui/dist/ ui/dist/

# Run as non-root
RUN useradd --system --no-create-home --shell /bin/false calseta
USER calseta
