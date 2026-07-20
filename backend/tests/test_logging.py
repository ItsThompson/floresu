"""structlog configuration: level mapping, dev vs prod renderer, service binding."""

from __future__ import annotations

import structlog

from floresu.core.logging import _build_processors, get_logger


def test_dev_uses_console_renderer_and_prod_uses_json() -> None:
    dev_last = _build_processors(is_dev=True)[-1]
    prod_last = _build_processors(is_dev=False)[-1]
    assert isinstance(dev_last, structlog.dev.ConsoleRenderer)
    assert isinstance(prod_last, structlog.processors.JSONRenderer)


def test_merge_contextvars_is_first_so_request_id_reaches_every_line() -> None:
    # Correlation binds request_id into contextvars; merge_contextvars must run
    # first for that binding to appear on every subsequent log line.
    assert _build_processors(is_dev=False)[0] is structlog.contextvars.merge_contextvars


def test_get_logger_binds_the_service_field() -> None:
    logger = get_logger("floresu-external")
    # The bound service travels on the logger's context.
    assert logger._context["service"] == "floresu-external"
