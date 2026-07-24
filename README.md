# Floresu

Floresu is a career tracker that stores a user's professional history and exposes it to the user's own AI agent over MCP.

## Layout

| Path | Role |
|------|------|
| `backend/` | Shared application core plus the external (`:8000`) and internal (`:8001`) HTTP adapters. Python + FastAPI + SQLAlchemy 2 async. |
| `worker/` | arq worker for incremental embedding jobs. Python. |
| `mcp/` | Agent-facing MCP server (FastMCP), a thin HTTP client of the internal API. Python. |
| `frontend/` | Human web client. Vite + React + TypeScript, Tailwind v4, shadcn/ui. |
| `contract/` | Dev/test-only cross-package drift guards (schema mirror, header constants). |
| `templates/` | Typst resume templates and shared partials. |
| `deployments/` | Operational overlays: Cloudflare Tunnel, Prometheus, Alertmanager, Grafana. |
| `e2e/` | Playwright full-stack tests. |
| `scripts/` | Deploy and operational scripts. |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for the Python packages
- [Node.js](https://nodejs.org/) 22+ for the frontend
- [just](https://github.com/casey/just) for task running
- [Docker](https://docs.docker.com/) with Compose for local services

## Common tasks

```sh
just up          # start local Postgres (pgvector) and Redis
just install     # install every package's dependencies
just lint        # ruff (Python) + oxlint (frontend)
just typecheck   # mypy --strict (Python) + tsc (frontend)
just test        # pytest (backend, worker, mcp)
just fmt         # format Python and frontend sources
just --list      # show every recipe
```

Each Python package is independently installable so it can build into its own
image. From any of `backend/`, `worker/`, or `mcp/`:

```sh
uv sync          # install dependencies into the package's virtualenv
uv run pytest    # run the package test suite
```
