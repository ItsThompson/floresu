# syntax=docker/dockerfile:1

# =============================================================================
# Floresu embedding-worker image.
#
# A thin arq worker that drains the Redis embed queue, calls the embedding
# provider, and writes vectors back over the backend internal API (:8001). Built
# from the worker/ package context; floresu is a set of SEPARATE uv projects (no
# workspace), so the build installs straight from worker/uv.lock and no backend
# or mcp source enters this image.
#
# The worker exposes its Prometheus metrics (embed_jobs_completed_total,
# embed_queue_depth) on WORKER_METRICS_PORT (:9100), scraped in-network.
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

# Source layer: install the worker package itself.
COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system --gid 999 floresu \
    && useradd --system --uid 999 --gid 999 --home-dir /app floresu

WORKDIR /app
COPY --from=builder --chown=floresu:floresu /app /app

# venv console scripts + interpreter on PATH (arq, python). The interpreter backs
# the compose healthcheck (`python -c ... urlopen /metrics`).
ENV PATH="/app/.venv/bin:$PATH"

USER floresu
EXPOSE 9100

# Container healthcheck: the worker process is live when its metrics exposition
# server answers on WORKER_METRICS_PORT (:9100). arq itself has no HTTP surface,
# so the metrics endpoint is the liveness signal.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:9100/metrics', timeout=3)"]

# Drain the embed queue. arq loads the WorkerSettings class (functions, queue
# name, Redis DSN, startup/shutdown hooks).
CMD ["arq", "floresu_worker.main.WorkerSettings"]
