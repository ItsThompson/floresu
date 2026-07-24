"""Observability: @track_failures counts only unexpected 5xx faults; combined
/metrics exposure; SQLAlchemy pool instrumentation."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
import structlog
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from floresu.core.app_factory import create_app
from floresu.core.db import _QUERY_START_KEY, _query_name, instrument_pool
from floresu.core.errors import ErrorCode, FloresuError, NotFound
from floresu.core.observability import FLORESU_REGISTRY, track_failures
from floresu.core.settings import AppSettings

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

MakeSettings = Callable[..., AppSettings]


class _ServerFaultError(FloresuError):
    # An ExpectedError whose status is 5xx: a genuine operational fault that IS
    # counted, unlike a 4xx domain outcome.
    status = 500
    title = "Server fault"
    default_code = ErrorCode.INTERNAL


@track_failures("sample")
class _Sample:
    """A stand-in service exercising the decorator's public/private + error rules."""

    async def succeeds(self) -> str:
        return "ok"

    async def raises_domain(self) -> None:
        raise NotFound("not here")

    async def raises_unexpected(self) -> None:
        raise RuntimeError("boom")

    async def raises_server_fault(self) -> None:
        raise _ServerFaultError("downstream unreachable")

    async def _private_unexpected(self) -> None:  # not wrapped: underscore-prefixed
        raise RuntimeError("boom")


class _GuardedError(Exception):
    """An exception that rejects attribute setting.

    Exercises the marker-suppression path: the decorator's attempt to stamp the
    ``_floresu_failure_logged`` marker raises, but that failure is swallowed so the
    ORIGINAL error still propagates (the worst case is a duplicate log line).
    """

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("attributes are frozen")


@track_failures("nested_inner")
class _NestedInner:
    async def boom(self) -> None:
        raise RuntimeError("nested boom")


@track_failures("nested_outer")
class _NestedOuter:
    """A tracked method that delegates to another tracked service's method."""

    def __init__(self, inner: _NestedInner) -> None:
        self._inner = inner

    async def run(self) -> None:
        await self._inner.boom()


@track_failures("kinds")
class _MethodKinds:
    """Only the public ``async def`` is wrapped; sync/static/class are skipped."""

    async def async_boom(self) -> None:
        raise RuntimeError("async boom")

    def sync_boom(self) -> None:
        raise RuntimeError("sync boom")

    @staticmethod
    def static_boom() -> None:
        raise RuntimeError("static boom")

    @classmethod
    def class_boom(cls) -> None:
        raise RuntimeError("class boom")


@track_failures("guarded")
class _GuardedSample:
    async def boom(self) -> None:
        raise _GuardedError("frozen")


def _failures_for(service: str, method: str) -> float:
    value = FLORESU_REGISTRY.get_sample_value(
        "service_method_failures_total", {"service": service, "method": method}
    )
    return value or 0.0


def _failures(method: str) -> float:
    return _failures_for("sample", method)


def _error_logs(cap: structlog.testing.CapturingLogger) -> list[structlog.testing.CapturedCall]:
    return [call for call in cap.calls if call.method_name == "error"]


def _capture_failure_log(monkeypatch: pytest.MonkeyPatch) -> structlog.testing.CapturingLogger:
    """Swap the module failure logger for a capturing one (mirrors test_errors)."""
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.core.observability._log", cap)
    return cap


async def test_unexpected_error_is_counted_and_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capture_failure_log(monkeypatch)
    before = _failures("raises_unexpected")

    with pytest.raises(RuntimeError):
        await _Sample().raises_unexpected()

    assert _failures("raises_unexpected") == before + 1
    logs = _error_logs(cap)
    assert len(logs) == 1
    assert logs[0].args == ("service_method_failed",)
    assert logs[0].kwargs["service"] == "sample"
    assert logs[0].kwargs["method"] == "raises_unexpected"
    assert isinstance(logs[0].kwargs["exc_info"], RuntimeError)


async def test_domain_4xx_is_neither_counted_nor_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capture_failure_log(monkeypatch)
    before = _failures("raises_domain")

    with pytest.raises(NotFound):
        await _Sample().raises_domain()

    # A model-recoverable 4xx domain error is an expected outcome, not a failure.
    assert _failures("raises_domain") == before
    assert _error_logs(cap) == []


async def test_expected_error_at_or_above_500_is_counted_and_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = _capture_failure_log(monkeypatch)
    before = _failures("raises_server_fault")

    with pytest.raises(_ServerFaultError):
        await _Sample().raises_server_fault()

    # Classification is by HTTP status, not exception type: a 5xx ExpectedError
    # is a real fault and IS both counted and logged.
    assert _failures("raises_server_fault") == before + 1
    logs = _error_logs(cap)
    assert len(logs) == 1
    assert logs[0].kwargs["method"] == "raises_server_fault"
    assert isinstance(logs[0].kwargs["exc_info"], _ServerFaultError)


async def test_nested_tracked_calls_log_once_but_count_per_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = _capture_failure_log(monkeypatch)
    inner_before = _failures_for("nested_inner", "boom")
    outer_before = _failures_for("nested_outer", "run")

    with pytest.raises(RuntimeError):
        await _NestedOuter(_NestedInner()).run()

    # Each tracked method increments its own {service, method} series...
    assert _failures_for("nested_inner", "boom") == inner_before + 1
    assert _failures_for("nested_outer", "run") == outer_before + 1
    # ...but the shared exception is logged exactly once, by the innermost frame.
    logs = _error_logs(cap)
    assert len(logs) == 1
    assert logs[0].kwargs["service"] == "nested_inner"
    assert logs[0].kwargs["method"] == "boom"


async def test_only_public_async_methods_are_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capture_failure_log(monkeypatch)
    sample = _MethodKinds()
    async_before = _failures_for("kinds", "async_boom")

    with pytest.raises(RuntimeError):
        await sample.async_boom()

    # The public async method is wrapped: counted and logged.
    assert _failures_for("kinds", "async_boom") == async_before + 1
    assert len(_error_logs(cap)) == 1

    # Sync, static, and class methods are left unwrapped: never counted or logged.
    with pytest.raises(RuntimeError):
        sample.sync_boom()
    with pytest.raises(RuntimeError):
        _MethodKinds.static_boom()
    with pytest.raises(RuntimeError):
        _MethodKinds.class_boom()

    assert _failures_for("kinds", "sync_boom") == 0.0
    assert _failures_for("kinds", "static_boom") == 0.0
    assert _failures_for("kinds", "class_boom") == 0.0
    assert len(_error_logs(cap)) == 1  # unchanged: only async_boom logged


async def test_marker_set_failure_is_suppressed_and_original_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = _capture_failure_log(monkeypatch)
    before = _failures_for("guarded", "boom")

    # Stamping the marker raises TypeError; the decorator suppresses it so the
    # ORIGINAL _GuardedError propagates unmasked and the failure is still logged.
    with pytest.raises(_GuardedError):
        await _GuardedSample().boom()

    assert _failures_for("guarded", "boom") == before + 1
    logs = _error_logs(cap)
    assert len(logs) == 1
    assert isinstance(logs[0].kwargs["exc_info"], _GuardedError)


async def test_success_is_transparent_and_uncounted() -> None:
    before = _failures("succeeds")
    assert await _Sample().succeeds() == "ok"
    assert _failures("succeeds") == before


def test_decorator_preserves_public_method_identity() -> None:
    assert _Sample.succeeds.__name__ == "succeeds"


async def test_private_methods_are_left_unwrapped() -> None:
    before = _failures("_private_unexpected")
    with pytest.raises(RuntimeError):
        await _Sample()._private_unexpected()
    assert _failures("_private_unexpected") == before


# --- combined /metrics exposure ---------------------------------------------


def test_metrics_endpoint_serves_http_and_custom_families(make_settings: MakeSettings) -> None:
    client = TestClient(create_app(make_settings()))
    client.get("/healthz")  # generate one HTTP sample

    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert "service_method_failures_total" in body
    assert "db_query_duration_seconds" in body
    assert "active_connections" in body


# --- DB pool instrumentation -------------------------------------------------


def _query_count(query_name: str) -> float:
    value = FLORESU_REGISTRY.get_sample_value(
        "db_query_duration_seconds_count", {"query_name": query_name}
    )
    return value or 0.0


def _make_instrumented_sqlite() -> Engine:
    """A real in-memory SQLite engine with the pool events attached.

    ``instrument_pool`` only touches ``engine.sync_engine``; a stand-in carrying
    the real sync engine there lets the pool/cursor events fire on genuine query
    execution without needing an async driver.
    """
    sync_engine = create_engine("sqlite://")
    instrument_pool(SimpleNamespace(sync_engine=sync_engine))  # type: ignore[arg-type]
    return sync_engine


def test_query_execution_records_duration_by_verb() -> None:
    engine = _make_instrumented_sqlite()
    before = _query_count("select")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert _query_count("select") == before + 1


def _active_connections() -> float:
    value = FLORESU_REGISTRY.get_sample_value("active_connections")
    return value or 0.0


def test_active_connections_returns_to_baseline_after_checkin() -> None:
    engine = _make_instrumented_sqlite()
    baseline = _active_connections()
    with engine.connect() as conn:
        assert _active_connections() == baseline + 1
        conn.execute(text("SELECT 1"))
    assert _active_connections() == baseline


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT 1", "select"),
        ("  insert into t values (1)", "insert"),
        ("UPDATE t SET x = 1", "update"),
        ("delete from t", "delete"),
        ("WITH cte AS (SELECT 1) SELECT * FROM cte", "other"),
        ("", "other"),
    ],
)
def test_query_name_collapses_to_a_bounded_verb(statement: str, expected: str) -> None:
    assert _query_name(statement) == expected


def test_raising_statement_pops_its_start_time() -> None:
    """A statement that raises self-cleans via ``handle_error``: because
    ``after_cursor_execute`` never fires on error, the pushed start-time would leak
    into ``conn.info`` for the connection's whole life without the listener. A
    unique violation is the motivating case (a normal, non-invalidating error)."""
    engine = _make_instrumented_sqlite()
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO t (id) VALUES (1)"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO t (id) VALUES (1)"))
        assert conn.info.get(_QUERY_START_KEY) == []
