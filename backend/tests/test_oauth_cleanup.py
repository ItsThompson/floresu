"""Unit tests for the stale-client cleanup loop and its lifespan wiring.

The DB-backed sweep itself is exercised end to end in the migration integration
test; here the loop/scheduling behavior is tested with a stub sweep so no Docker
is needed.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from floresu.core.db import create_database
from floresu.oauth.cleanup import (
    run_cleanup_loop,
    start_stale_client_cleanup,
    stop_stale_client_cleanup,
)
from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset

_URL = "postgresql+asyncpg://floresu:floresu@localhost:5432/floresu"
_TINY = timedelta(seconds=0.001)


async def test_run_cleanup_loop_runs_the_sweep_until_cancelled() -> None:
    runs = 0

    async def sweep() -> int:
        nonlocal runs
        runs += 1
        return 0

    task = asyncio.create_task(run_cleanup_loop(sweep, interval=_TINY))
    while runs < 3:
        await asyncio.sleep(_TINY.total_seconds())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runs >= 3


async def test_run_cleanup_loop_survives_a_failing_sweep() -> None:
    calls = 0

    async def flaky_sweep() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient DB error")
        return 0

    task = asyncio.create_task(run_cleanup_loop(flaky_sweep, interval=_TINY))
    # The first sweep raises; the loop must keep going and call sweep again.
    while calls < 2:
        await asyncio.sleep(_TINY.total_seconds())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls >= 2


async def test_start_is_disabled_by_a_non_positive_interval() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    database = create_database(_URL)
    try:
        task = start_stale_client_cleanup(
            database.sessionmaker,
            config,
            codec,
            interval=timedelta(0),
            max_age=timedelta(days=30),
        )
        assert task is None
    finally:
        await database.engine.dispose()


async def test_stop_is_a_noop_when_the_reaper_was_disabled() -> None:
    # Awaiting stop on a None task (reaper disabled) must not raise.
    await stop_stale_client_cleanup(None)


async def test_start_creates_a_task_that_stop_cancels() -> None:
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))
    database = create_database(_URL)
    try:
        # A long interval so the sweep stays asleep (never touches the DB) until
        # stop cancels it mid-sleep.
        task = start_stale_client_cleanup(
            database.sessionmaker,
            config,
            codec,
            interval=timedelta(hours=1),
            max_age=timedelta(days=30),
        )
        assert task is not None
        await stop_stale_client_cleanup(task)
        assert task.cancelled()
    finally:
        await database.engine.dispose()
