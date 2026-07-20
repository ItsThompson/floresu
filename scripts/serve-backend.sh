#!/usr/bin/env bash
# Run both backend ASGI apps in one container/process group.
#
# The external app (internet-facing, :8000) and the internal app (app-net only,
# :8001) are separate uvicorn processes over the same shared core. This script
# starts both and exits (killing both) as soon as either one exits, so a crash of
# either app fails the container rather than silently running degraded.
#
# Migrations are NOT run here: `alembic upgrade head` is an explicit pre-traffic
# deploy step, never at app startup.
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
EXTERNAL_PORT="${EXTERNAL_PORT:-8000}"
INTERNAL_PORT="${INTERNAL_PORT:-8001}"

uvicorn floresu.api.main:app --host "$HOST" --port "$EXTERNAL_PORT" &
external_pid=$!
uvicorn floresu.api_internal.main:app --host "$HOST" --port "$INTERNAL_PORT" &
internal_pid=$!

# Take both down on exit or signal.
trap 'kill "$external_pid" "$internal_pid" 2>/dev/null || true' EXIT INT TERM

# Exit as soon as either app exits, so a crash of either fails the container
# rather than running degraded. Polling keeps this portable across bash versions
# (`wait -n` needs bash 4+).
while kill -0 "$external_pid" 2>/dev/null && kill -0 "$internal_pid" 2>/dev/null; do
    sleep 1
done
