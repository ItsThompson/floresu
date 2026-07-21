"""arq worker entrypoint: the ``WorkerSettings`` arq loads to run embed jobs.

Run as ``arq floresu_worker.main.WorkerSettings``. The worker drains the embed
queue on Redis, running :func:`embed_item` / :func:`purge_item` one item at a
time. :func:`startup` builds the process-wide dependencies (the embedding provider
over its own httpx client, and the internal-API client over another) and stashes
them on the arq ``ctx`` the tasks read; :func:`shutdown` closes both clients.

The provider and client are built here (the composition root for the worker
process) and injected via ``ctx`` so the tasks are unit-testable with fakes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from arq.connections import RedisSettings

from floresu_worker.client import InternalApiClient, create_internal_http_client
from floresu_worker.config import EMBED_QUEUE_NAME
from floresu_worker.embed_tasks import embed_item, purge_item
from floresu_worker.logging import configure_logging, get_logger
from floresu_worker.metrics import start_metrics_server
from floresu_worker.provider import OpenAIEmbeddingProvider
from floresu_worker.settings import build_worker_settings

_OPENAI_TIMEOUT_SECONDS = 30.0


async def startup(ctx: dict[str, Any]) -> None:  # pragma: no cover - process wiring
    """Build the provider + internal-API client and stash them on the arq ctx."""
    import httpx

    settings = build_worker_settings()
    configure_logging(environment=settings.environment, log_level=settings.log_level)
    log = get_logger("floresu-worker")

    openai_client = httpx.AsyncClient(
        base_url=settings.openai_base_url,
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=_OPENAI_TIMEOUT_SECONDS,
    )
    internal_http = create_internal_http_client(settings.backend_internal_url)
    ctx["provider"] = OpenAIEmbeddingProvider(openai_client)
    ctx["client"] = InternalApiClient(internal_http, api_token=settings.internal_api_token)
    ctx["_openai_client"] = openai_client
    ctx["_internal_http"] = internal_http

    if settings.worker_metrics_port > 0:
        start_metrics_server(settings.worker_metrics_port)
    log.info("embed_worker_started", queue=EMBED_QUEUE_NAME)


async def shutdown(ctx: dict[str, Any]) -> None:  # pragma: no cover - process wiring
    """Close the provider and internal-API HTTP clients."""
    await ctx["_openai_client"].aclose()
    await ctx["_internal_http"].aclose()


def _redis_settings() -> RedisSettings:  # pragma: no cover - process wiring
    return RedisSettings.from_dsn(build_worker_settings().redis_url)


class WorkerSettings:
    """The arq worker definition (``arq floresu_worker.main.WorkerSettings``)."""

    functions: ClassVar[list[Callable[..., Awaitable[str]]]] = [embed_item, purge_item]
    queue_name: ClassVar[str] = EMBED_QUEUE_NAME
    redis_settings: ClassVar[RedisSettings] = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
