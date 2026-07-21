"""structlog configuration for the embedding worker.

Configured once per process. In development, logs render as a human-readable
console stream; everywhere else as JSON. The ``service`` field is bound per
logger via :func:`get_logger`. Mirrors the backend's ``floresu.core.logging`` in
shape; the worker ships as a separate image, so it owns its own copy rather than
importing across the boundary.
"""

from __future__ import annotations

import logging
from typing import cast

import structlog

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_configured = False


def _renderer(*, is_dev: bool) -> structlog.types.Processor:
    if is_dev:
        return structlog.dev.ConsoleRenderer()
    return structlog.processors.JSONRenderer()


def configure_logging(*, environment: str, log_level: str) -> None:
    """Configure structlog once per process. Subsequent calls are no-ops."""
    global _configured
    if _configured:
        return
    level = _LEVELS.get(log_level.lower(), logging.INFO)
    is_dev = environment.lower() == "development"
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            _renderer(is_dev=is_dev),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(service: str) -> structlog.stdlib.BoundLogger:
    """Return a logger with the ``service`` field bound onto every line."""
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger().bind(service=service))
