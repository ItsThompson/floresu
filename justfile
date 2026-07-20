# Floresu developer task runner.
# Run `just --list` to see every recipe.

# Python packages that share the same uv + ruff + mypy + pytest toolchain.
python_packages := "backend worker mcp"

# Show available recipes.
default:
    @just --list

# --- local dev services ---

# Start local Postgres (pgvector) and Redis.
up:
    docker compose up -d postgres redis

# Stop local dev services.
down:
    docker compose down

# --- install ---

# Install dependencies for every package.
install:
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in {{python_packages}}; do
        echo "== uv sync $pkg =="
        (cd "$pkg" && uv sync)
    done
    echo "== npm install frontend =="
    (cd frontend && npm install)

# --- lint ---

# Lint every package.
lint: lint-python lint-frontend

lint-python:
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in {{python_packages}}; do
        echo "== ruff check $pkg =="
        (cd "$pkg" && uv run ruff check .)
    done

lint-frontend:
    cd frontend && npm run lint

# --- typecheck ---

# Type-check every package.
typecheck: typecheck-python typecheck-frontend

typecheck-python:
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in {{python_packages}}; do
        echo "== mypy --strict $pkg =="
        (cd "$pkg" && uv run mypy --strict)
    done

typecheck-frontend:
    cd frontend && npm run typecheck

# --- test ---

# Run every package's test suite.
test:
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in {{python_packages}}; do
        echo "== pytest $pkg =="
        (cd "$pkg" && uv run pytest)
    done

# Build the frontend static bundle.
build-frontend:
    cd frontend && npm run build

# --- format ---

# Format Python and frontend sources.
fmt:
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in {{python_packages}}; do
        echo "== ruff format $pkg =="
        (cd "$pkg" && uv run ruff format .)
    done
    echo "== prettier frontend =="
    (cd frontend && npm run fmt)
