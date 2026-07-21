"""Prometheus HTTP metrics for the MCP resource server.

Metric names and labels follow the same stable convention as the backend so
alert rules and dashboards drop in across both images:

- ``http_requests_total{method,path,status}`` (counter)
- ``http_request_duration_seconds{method,path}`` (histogram)

``path`` is the matched route template to bound label cardinality; untemplated
paths group to ``none``. ``/metrics`` is excluded from its own counters.

The app owns a private ``CollectorRegistry`` for its HTTP families; ``/metrics``
serves that registry concatenated with the injected domain registry (the
MCP tool-invocation counter, :mod:`floresu_mcp.tool_metrics`), so one scrape sees
the whole picture. The two registries hold disjoint metric names, so
concatenation is a valid single exposition response.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI

# An instrumentation function receives one request's Info and records to a metric.
Instrumentation = Callable[[Info], None]

METRICS_ENDPOINT = "/metrics"


def _requests_total(registry: CollectorRegistry) -> Instrumentation:
    metric = Counter(
        "http_requests_total",
        "Total number of HTTP requests by method, matched route template, and status.",
        labelnames=("method", "path", "status"),
        registry=registry,
    )

    def instrumentation(info: Info) -> None:
        metric.labels(
            method=info.method,
            path=info.modified_handler,
            status=info.modified_status,
        ).inc()

    return instrumentation


def _request_duration(registry: CollectorRegistry) -> Instrumentation:
    metric = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds by method and matched route template.",
        labelnames=("method", "path"),
        registry=registry,
    )

    def instrumentation(info: Info) -> None:
        metric.labels(
            method=info.method,
            path=info.modified_handler,
        ).observe(info.modified_duration)

    return instrumentation


def _expose_combined(
    app: FastAPI, http_registry: CollectorRegistry, domain_registry: CollectorRegistry
) -> None:
    """Serve ``/metrics`` as the app's private HTTP registry followed by the
    injected domain registry (MCP tool metrics)."""

    @app.get(METRICS_ENDPOINT, include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(http_registry) + generate_latest(domain_registry)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


def instrument(app: FastAPI, domain_registry: CollectorRegistry) -> CollectorRegistry:
    """Wire request metrics and expose ``/metrics`` on ``app``.

    ``domain_registry`` holds the MCP tool-invocation counter and is exposed
    alongside the private HTTP registry. Returns the app's private HTTP registry
    (useful for tests).
    """
    registry = CollectorRegistry()
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_group_untemplated=True,
        excluded_handlers=[METRICS_ENDPOINT],
        registry=registry,
    )
    instrumentator.add(_requests_total(registry))
    instrumentator.add(_request_duration(registry))
    instrumentator.instrument(app)
    _expose_combined(app, registry, domain_registry)
    return registry
