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

# A received signal (e.g. `docker stop` -> SIGTERM) is a graceful shutdown, not a
# failure: take both apps down and remember we were asked to stop.
terminating=0
trap 'terminating=1; kill "$external_pid" "$internal_pid" 2>/dev/null || true' INT TERM

# Wait until either app exits. Polling keeps this portable across bash versions
# (`wait -n` needs bash 4+); `sleep || true` keeps an interrupted sleep (on a
# trapped signal) from tripping `set -e`.
while kill -0 "$external_pid" 2>/dev/null && kill -0 "$internal_pid" 2>/dev/null; do
    sleep 1 || true
done

kill "$external_pid" "$internal_pid" 2>/dev/null || true
# Reap both so neither lingers after this script returns (outside a container,
# where PID-1 exit would otherwise tear them down).
wait "$external_pid" "$internal_pid" 2>/dev/null || true

# An app that exited on its own (not via a stop signal) means the process group
# is degraded: fail non-zero so the orchestrator restarts the container instead
# of treating it as a clean stop.
if [ "$terminating" -eq 1 ]; then
    exit 0
fi
echo "serve-backend: an app exited unexpectedly; failing so the container restarts" >&2
exit 1
