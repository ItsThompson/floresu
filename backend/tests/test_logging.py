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


def test_per_request_line_carries_both_component_service_and_app() -> None:
    # A component logger binds ``service``; the correlation middleware binds
    # ``app`` into contextvars. merge_contextvars (first in the chain) keeps both:
    # its setdefault leaves the already-present component ``service`` untouched and
    # adds ``app`` from the contextvars, so neither shadows the other.
    component = get_logger("floresu-search")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-1", app="floresu-external")
    try:
        event_dict = {**component._context, "event": "search_started"}
        merged = structlog.contextvars.merge_contextvars(None, "info", event_dict)
    finally:
        structlog.contextvars.clear_contextvars()
    assert merged["service"] == "floresu-search"
    assert merged["app"] == "floresu-external"
    assert merged["request_id"] == "req-1"
