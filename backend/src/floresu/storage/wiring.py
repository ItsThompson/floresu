"""Compose the R2 object store from settings for the composition roots.

Keeps the aioboto3 session construction and credential wiring out of the
entrypoints. The session is lazy: no network call happens until a ``put`` or
``get_url``, so building it needs no reachable R2 and an unconfigured dev box still
boots (only export exercises the store).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aioboto3

from floresu.storage.config import PRESIGN_TTL_SECONDS
from floresu.storage.store import R2ObjectStore

if TYPE_CHECKING:
    from floresu.core.settings import AppSettings


def build_object_store(settings: AppSettings) -> R2ObjectStore:
    """Build the R2-backed object store from settings (lazy until first use)."""
    return R2ObjectStore(
        aioboto3.Session(),
        bucket=settings.r2_bucket,
        endpoint_url=settings.r2_endpoint_url,
        access_key_id=settings.r2_access_key_id.get_secret_value(),
        secret_access_key=settings.r2_secret_access_key.get_secret_value(),
        presign_ttl_seconds=PRESIGN_TTL_SECONDS,
    )
