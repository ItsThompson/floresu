"""Account-registration notifications: delivery, isolation, and log safety."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import pytest
import structlog
from pydantic import SecretStr
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.testing import capture_logs

from floresu.accounts.notifications import (
    BestEffortEventPublisher,
    DiscordUserRegisteredHandler,
    NullEventPublisher,
    UserRegistered,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping

    LogRecord = MutableMapping[str, object]

_WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/secret-token-abcdefXYZ"
_WEBHOOK_SECRET = SecretStr(_WEBHOOK)


@pytest.fixture(autouse=True)
def _isolate_contextvars() -> Iterator[None]:
    clear_contextvars()
    yield
    clear_contextvars()


def _responding_transport(status: int) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.MockTransport(handler), seen


def _raising_transport(exc: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def _publisher(transport: httpx.MockTransport) -> BestEffortEventPublisher:
    return BestEffortEventPublisher(
        [DiscordUserRegisteredHandler(_WEBHOOK_SECRET, transport=transport)]
    )


def _event(email: str = "ada@example.com", user_id: int = 1) -> UserRegistered:
    return UserRegistered(user_id=user_id, email=email)


async def test_posts_the_email_as_discord_content() -> None:
    transport, seen = _responding_transport(204)
    publisher = _publisher(transport)

    publisher.publish(_event())
    await publisher.aclose()

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == _WEBHOOK
    assert json.loads(request.content) == {"content": "🎉 New user registered: ada@example.com"}


async def test_204_response_logs_no_failure_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, _ = _responding_transport(204)
    publisher = _publisher(transport)

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("floresu.accounts.notifications._log", structlog.get_logger())
        publisher.publish(_event())
        await publisher.aclose()

    assert not _failures(logs)


@pytest.mark.parametrize(
    ("exc", "expected_type"),
    [
        (httpx.ConnectError("unreachable"), "ConnectError"),
        (httpx.ReadTimeout("timed out"), "ReadTimeout"),
    ],
)
async def test_transport_errors_are_swallowed_and_logged_without_the_url(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected_type: str
) -> None:
    publisher = _publisher(_raising_transport(exc))

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("floresu.accounts.notifications._log", structlog.get_logger())
        publisher.publish(_event())
        await publisher.aclose()

    failures = _failures(logs)
    assert len(failures) == 1
    record = failures[0]
    assert record["event_type"] == "UserRegistered"
    assert record["handler"] == "DiscordUserRegisteredHandler"
    assert record["error_type"] == expected_type
    assert record["status"] is None
    _assert_log_safe(record)


@pytest.mark.parametrize("status", [429, 500])
async def test_error_status_is_swallowed_and_logged_with_the_status(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    transport, _ = _responding_transport(status)
    publisher = _publisher(transport)

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("floresu.accounts.notifications._log", structlog.get_logger())
        publisher.publish(_event())
        await publisher.aclose()

    failures = _failures(logs)
    assert len(failures) == 1
    record = failures[0]
    assert record["event_type"] == "UserRegistered"
    assert record["handler"] == "DiscordUserRegisteredHandler"
    assert record["error_type"] == "HTTPStatusError"
    assert record["status"] == status
    _assert_log_safe(record)


async def test_failure_record_carries_the_correlation_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = _publisher(_raising_transport(httpx.ConnectError("unreachable")))

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("floresu.accounts.notifications._log", structlog.get_logger())
        bind_contextvars(request_id="corr-signup-1")
        publisher.publish(_event())
        await publisher.aclose()

    assert _failures(logs)[0]["request_id"] == "corr-signup-1"


async def test_failure_record_carries_the_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = _publisher(_raising_transport(httpx.ConnectError("unreachable")))

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("floresu.accounts.notifications._log", structlog.get_logger())
        publisher.publish(_event(user_id=42))
        await publisher.aclose()

    assert _failures(logs)[0]["user_id"] == 42


async def test_aclose_awaits_delivery_completion() -> None:
    transport, seen = _responding_transport(204)
    publisher = _publisher(transport)

    publisher.publish(_event())
    await publisher.aclose()

    assert len(seen) == 1
    await publisher.aclose()
    assert len(seen) == 1


async def test_null_publisher_schedules_no_task_and_does_no_io() -> None:
    publisher = NullEventPublisher()

    before = len(asyncio.all_tasks())
    publisher.publish(_event())

    assert len(asyncio.all_tasks()) == before
    await publisher.aclose()


def _failures(logs: list[LogRecord]) -> list[LogRecord]:
    return [entry for entry in logs if entry.get("event") == "event_delivery_failed"]


def _assert_log_safe(record: LogRecord) -> None:
    assert "exc_info" not in record
    assert "exception" not in record
    rendered = json.dumps(record, default=repr)
    assert _WEBHOOK not in rendered
    assert "secret-token" not in rendered
    assert "discord.com" not in rendered
