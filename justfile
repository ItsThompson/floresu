# Floresu developer task runner.
# Run `just --list` to see every recipe.

# Python packages that share the same uv + ruff + mypy + pytest toolchain.
python_packages := "backend worker mcp"

# Show available recipes.
default:
    @just --list

# --- local dev services ---

# The production-shaped base file (docker-compose.yml) is expose-only and sources
# the Prometheus scrape/alert configs from the environment (never a bind mount,
# for box-less deploy parity). Populate those from the committed files so the
# base file parses locally, and layer the dev overlay for host-published
# Postgres/Redis. `dev` is the base+dev compose prefix every local recipe uses.
export FLORESU_PROMETHEUS_CONFIG := `cat deployments/prometheus/prometheus.yml`
export FLORESU_PROMETHEUS_ALERTS := `cat deployments/prometheus/alerts.yml`

dev := "docker compose -f docker-compose.yml -f docker-compose.dev.yml"

# Start local Postgres (pgvector) + Redis, host-published for the inner loop.
up:
    {{dev}} up -d postgres redis

# Stop local dev services.
down:
    {{dev}} down

# Bring up the FULL stack locally (built images + dev env + host-published data).
up-dev:
    {{dev}} up -d --build

# --- backend apps ---

# Run the external app (:8000) with autoreload for the host inner loop.
dev-api:
    cd backend && uv run uvicorn floresu.api.main:app --reload --port 8000

# Run the internal app (:8001) with autoreload for the host inner loop.
dev-api-internal:
    cd backend && uv run uvicorn floresu.api_internal.main:app --reload --port 8001

# Run both backend apps together (as the container does).
serve-backend:
    cd backend && uv run ../scripts/serve-backend.sh

# Apply all migrations to the database in DATABASE_URL (defaults to dev compose).
migrate:
    cd backend && uv run alembic upgrade head

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
    echo "== vitest frontend =="
    (cd frontend && npm run test)

# Build the frontend static bundle.
build-frontend:
    cd frontend && npm run build

# Regenerate the OpenAPI -> TypeScript client from the live FastAPI schema.
# Exports the external app's OpenAPI document, then runs openapi-typescript. CI
# runs this and `git diff --exit-code` to fail on a stale committed client. Run
# after any change to the external REST surface.
codegen:
    cd backend && LOG_LEVEL=critical uv run python -c "import json; from floresu.api.main import app; print(json.dumps(app.openapi(), indent=2))" > ../frontend/openapi.json
    cd frontend && npm run codegen

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

# --- deploy / ops (see deployments/README.md) ---

# Run the deploy.sh test harness (pure-bash; no daemon or VPS needed).
test-deploy:
    bash scripts/tests/deploy_test.sh

# Validate every Compose layer parses: base, base+dev, and the full deploy shape
# (base+tunnel+deploy under the tunnels profile). Dummy secrets prove the
# overlays parse; they are never used at rest.
compose-config:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose -f docker-compose.yml config -q
    {{dev}} config -q
    export FLORESU_OAUTH_PRIVATE_KEY=dummy FLORESU_CLOUDFLARED_CREDENTIALS=dummy
    export FLORESU_ALERTMANAGER_CONFIG=dummy FLORESU_CLOUDFLARED_INGRESS=dummy
    export POSTGRES_PASSWORD=dummy SESSION_JWT_SECRET=dummy INTERNAL_API_TOKEN=dummy
    export GF_SECURITY_ADMIN_PASSWORD=dummy
    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml \
        --profile tunnels config -q
    echo "all compose layers valid"

# Print the deploy phase plan against a server WITHOUT executing (dry-run). Needs
# the deploy secret env vars set (see scripts/deploy.sh); dummy values are fine
# for a dry-run. Example: just deploy-dry-run 203.0.113.10
deploy-dry-run server-ip:
    DRY_RUN=1 ./scripts/deploy.sh {{server-ip}}
