# syntax=docker/dockerfile:1

# =============================================================================
# Floresu backend image (also the RENDER image).
#
# One image serves BOTH ASGI apps: the external app (:8000, internet-facing via
# the tunnel) and the internal app (:8001, app-net, token-gated). Built from the
# REPO-ROOT context (docker-compose backend.build.context: .) so the build can
# reach scripts/serve-backend.sh, the shared serve glue that runs both apps in
# one process group. The runtime layout mirrors the package (/app/src,
# /app/alembic, /app/alembic.ini) so `alembic upgrade head` and the uvicorn
# module paths resolve.
#
# floresu is a set of SEPARATE uv projects (no workspace), so the build installs
# straight from backend/uv.lock: no sibling package source ever enters this
# image (the backend<->mcp firewall holds by construction).
#
# The Typst binary is bundled here (spec §12: "the Typst binary is bundled in
# the render image"): resume PDF rendering runs synchronously in the backend
# process, so typst must be on PATH.
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

# uv: fast, lockfile-driven installs. Pinned; review with the base image.
COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Deps layer: the lockfile + manifest are all uv needs to resolve and install the
# locked third-party set. Kept before the source COPY so it caches across
# source-only changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Bundle the Typst binary (musl static build runs on slim). Pinned; review with
# the base image. The x86_64 triple matches the CI builders and the x86_64 VPS.
ARG TYPST_VERSION=0.15.0
ARG TYPST_TARGET=x86_64-unknown-linux-musl
ADD https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${TYPST_TARGET}.tar.xz /tmp/typst.tar.xz
RUN apt-get update && apt-get install -y --no-install-recommends xz-utils \
    && tar -xJf /tmp/typst.tar.xz -C /tmp \
    && mv /tmp/typst-${TYPST_TARGET}/typst /usr/local/bin/typst \
    && chmod +x /usr/local/bin/typst \
    && rm -rf /var/lib/apt/lists/* /tmp/typst.tar.xz /tmp/typst-${TYPST_TARGET}

# Source layer: install the backend package itself (deps already resolved above).
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# The serve glue (repo-root script) runs both apps in one process group and takes
# the container down if either app exits.
COPY scripts/serve-backend.sh /app/scripts/serve-backend.sh

# The Typst templates the render path reads. The backend IS the render image, so
# the templates ship in it (populated by the rendering slice under templates/).
COPY templates/ /app/templates/

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root runtime user (defense-in-depth). Explicit uid/gid so the OAuth signing
# key Compose secret can be materialized 0400-owned by this user (see
# docker-compose.tunnel.yml FLORESU_BACKEND_UID/GID).
RUN groupadd --system --gid 999 floresu \
    && useradd --system --uid 999 --gid 999 --home-dir /app floresu

WORKDIR /app
COPY --from=builder --chown=floresu:floresu /app /app
COPY --from=builder /usr/local/bin/typst /usr/local/bin/typst

# venv console scripts + interpreter on PATH (uvicorn, alembic, python). The
# interpreter backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/scripts/serve-backend.sh

USER floresu
EXPOSE 8000 8001

# Container healthcheck: BOTH apps must be ready. urlopen raises on a 503
# (not-ready) or a refused connection, both -> unhealthy. Compose refines the
# timing (start_period for DB readiness); this keeps the image self-describing.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/readyz', timeout=3); u.urlopen('http://127.0.0.1:8001/readyz', timeout=3)"]

CMD ["/app/scripts/serve-backend.sh"]
