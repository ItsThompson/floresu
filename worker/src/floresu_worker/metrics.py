"""The worker's Prometheus metrics: job outcomes and queue depth.

Two families on a dedicated registry:

- ``embed_jobs_completed_total{status}`` (counter): one increment per finished
  job, labeled by outcome (``applied`` / ``superseded`` / ``idempotent`` /
  ``archived`` / ``missing`` / ``purged`` / ``failed``), so a rising failure rate
  or a stuck backlog is alertable.
- ``embed_queue_depth`` (gauge): the current depth of the embed queue, sampled
  after each job, so a growing backlog is visible.

The worker ships as its own image, so it owns its registry and exposition rather
than importing the backend's. :func:`start_metrics_server` exposes ``/metrics`` on
the given port for Prometheus to scrape.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, start_http_server

WORKER_REGISTRY = CollectorRegistry()

EMBED_JOBS_COMPLETED = Counter(
    "embed_jobs_completed_total",
    "Embed/purge jobs the worker finished, by outcome status.",
    labelnames=("status",),
    registry=WORKER_REGISTRY,
)

EMBED_QUEUE_DEPTH = Gauge(
    "embed_queue_depth",
    "Current depth of the embed job queue, sampled after each job.",
    registry=WORKER_REGISTRY,
)


def record_job_completed(status: str) -> None:
    """Count one finished job under its outcome status."""
    EMBED_JOBS_COMPLETED.labels(status=status).inc()


def set_queue_depth(depth: int) -> None:
    """Record the current embed queue depth."""
    EMBED_QUEUE_DEPTH.set(depth)


def start_metrics_server(port: int) -> None:  # pragma: no cover - process wiring
    """Expose the worker's metrics registry on ``/metrics`` for Prometheus."""
    start_http_server(port, registry=WORKER_REGISTRY)
