# syntax=docker/dockerfile:1

# =============================================================================
# Floresu MCP resource-server image.
#
# OAuth 2.1 Resource Server (PRM + bearer validation) and thin client of the
# backend internal API (:8001). Single ASGI app on :9000. Built from the mcp/
# package context; floresu is a set of SEPARATE uv projects (no workspace), so
# the build installs straight from mcp/uv.lock and NO backend source ever enters
# this image (the MCP<->backend firewall holds by construction).
#
# /metrics, /healthz and /readyz are NOT tunnel-exposed: only PRM + the /mcp
# transport are public (mcp.floresu.app). /metrics is scraped in-network
# (app-net); the tunnel ingress allow-list (deployments/cloudflare/config.yml)
# enforces this.
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Deps layer (cached across source-only changes): lockfile + manifest only.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Source layer: install the mcp package itself.
COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system --gid 999 floresu \
    && useradd --system --uid 999 --gid 999 --home-dir /app floresu

WORKDIR /app
COPY --from=builder --chown=floresu:floresu /app /app

# venv console scripts + interpreter on PATH (uvicorn, python). The interpreter
# backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

USER floresu
EXPOSE 9000

# Container healthcheck: the RS is ready when its JWKS-reachability readiness
# check passes. Compose refines the timing; this keeps the image self-describing.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:9000/readyz', timeout=3)"]

# The `floresu-mcp` console script boots uvicorn on the settings host/port
# (0.0.0.0:9000).
CMD ["floresu-mcp"]
