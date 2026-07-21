"""The arq embed jobs: embed one item, or purge one item's vector.

One item per job, never the whole corpus. Both jobs are thin: they call the
backend internal API to read the item and write (or delete) its vector, embedding
in between via the injected provider. The content-hash gate is applied twice: the
worker skips the provider call for a job the item has already moved past (read
returns the current hash), and the backend re-gates authoritatively on write-back
(so a race between read and write is dropped, not applied). Archived or missing
items have their vector removed and are never embedded.

Every job records its outcome on ``embed_jobs_completed_total{status}`` and samples
``embed_queue_depth`` afterward. A transport or provider failure is counted as
``failed`` and re-raised so arq retries it; the item stays lexically searchable
meanwhile.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from floresu_worker.client import InternalApiClient
from floresu_worker.config import EMBED_QUEUE_NAME
from floresu_worker.logging import get_logger
from floresu_worker.metrics import record_job_completed, set_queue_depth
from floresu_worker.provider import EmbeddingProvider
from floresu_worker.schemas import VectorWrite

_log = get_logger("floresu-worker")

# Outcome statuses for a purge and a worker-side failure (the embed outcomes come
# from the backend's ``EmbedOutcome``).
_STATUS_PURGED = "purged"
_STATUS_MISSING = "missing"
_STATUS_ARCHIVED = "archived"
_STATUS_SUPERSEDED = "superseded"
_STATUS_FAILED = "failed"


async def embed_item(
    ctx: dict[str, Any], user_id: int, kind: str, item_id: int, content_hash: str
) -> str:
    """Embed one item, content-hash gated; skip/remove if superseded/archived/gone."""
    return await _guarded(ctx, _embed(ctx, user_id, kind, item_id, content_hash))


async def purge_item(ctx: dict[str, Any], user_id: int, kind: str, item_id: int) -> str:
    """Remove one item's vector (archived or deleted); idempotent."""
    return await _guarded(ctx, _purge(ctx, user_id, kind, item_id))


async def _embed(
    ctx: dict[str, Any], user_id: int, kind: str, item_id: int, content_hash: str
) -> str:
    client: InternalApiClient = ctx["client"]
    provider: EmbeddingProvider = ctx["provider"]
    item = await client.get_item(user_id, kind, item_id)
    if item is None:
        await client.delete_vector(user_id, kind, item_id)
        return _STATUS_MISSING
    if item.archived:
        await client.delete_vector(user_id, kind, item_id)
        return _STATUS_ARCHIVED
    if item.content_hash != content_hash:
        # The item's content moved past this job before it ran; drop it.
        return _STATUS_SUPERSEDED
    vectors = await provider.embed([item.text])
    write = VectorWrite(content_hash=item.content_hash, vector=vectors[0], model=provider.model)
    return await client.put_vector(user_id, kind, item_id, write)


async def _purge(ctx: dict[str, Any], user_id: int, kind: str, item_id: int) -> str:
    client: InternalApiClient = ctx["client"]
    await client.delete_vector(user_id, kind, item_id)
    return _STATUS_PURGED


async def _guarded(ctx: dict[str, Any], work: Awaitable[str]) -> str:
    """Run a job's work, recording its outcome and sampling the queue depth.

    A failure is counted as ``failed`` and re-raised so arq retries the job.
    """
    try:
        status = await work
    except Exception:
        record_job_completed(_STATUS_FAILED)
        await _sample_queue_depth(ctx)
        raise
    record_job_completed(status)
    await _sample_queue_depth(ctx)
    return status


async def _sample_queue_depth(ctx: dict[str, Any]) -> None:
    """Sample the current embed queue depth into the gauge (best-effort)."""
    try:
        depth = await ctx["redis"].zcard(EMBED_QUEUE_NAME)
        set_queue_depth(int(depth))
    except Exception as exc:  # a sampling hiccup must not fail or retry the job
        _log.warning("embed_queue_depth_sample_failed", error=str(exc))
