#!/usr/bin/env bash
# Container healthcheck: both backend apps must be live.
#
# Probes the liveness endpoint of the external (:8000) and internal (:8001) apps.
# Exits non-zero if either is unreachable, so a container running only one app is
# reported unhealthy. Uses liveness (/healthz), not readiness (/readyz): readiness
# reflects Postgres connectivity and is orchestrated separately.
set -euo pipefail

EXTERNAL_PORT="${EXTERNAL_PORT:-8000}"
INTERNAL_PORT="${INTERNAL_PORT:-8001}"

for port in "$EXTERNAL_PORT" "$INTERNAL_PORT"; do
    curl -fsS "http://localhost:${port}/healthz" >/dev/null
done
