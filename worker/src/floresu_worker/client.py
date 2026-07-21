"""Thin client of the backend internal API (:8001) for the embed hop.

The worker reads an item's embeddable text and writes its vector back over the
internal app. This client owns the one security-critical invariant of that hop:
**every** request carries the resolved ``X-User-ID`` (the item owner) plus the
worker ``X-Actor`` plus the shared ``X-Internal-Api-Token``, applied last so a
caller cannot override them. No agent bearer exists on this path (the worker is a
system side channel), so none is ever forwarded.

The named methods mirror the three internal embed routes op-for-op. The
``httpx.AsyncClient`` is injected (bound to the backend internal base URL) so
tests substitute a mock transport without a live backend. A transport failure
propagates so the arq job retries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from floresu_worker.config import (
    ACTOR_HEADER,
    EMBED_PATH,
    INTERNAL_API_TOKEN_HEADER,
    USER_ID_HEADER,
    WORKER_ACTOR,
)
from floresu_worker.schemas import EmbedItemContent, VectorWrite

if TYPE_CHECKING:
    from pydantic import SecretStr

# Bound so a hung internal call cannot pin a worker job indefinitely.
_DEFAULT_TIMEOUT_SECONDS = 10.0


class InternalApiClient:
    """Reads item content and writes vectors back over the internal embed routes."""

    def __init__(self, http_client: httpx.AsyncClient, *, api_token: SecretStr) -> None:
        self._http = http_client
        self._api_token = api_token

    def _headers(self, user_id: int) -> dict[str, str]:
        """The trusted identity + actor + shared-secret headers for one call."""
        return {
            USER_ID_HEADER: str(user_id),
            ACTOR_HEADER: WORKER_ACTOR,
            INTERNAL_API_TOKEN_HEADER: self._api_token.get_secret_value(),
        }

    async def get_item(self, user_id: int, kind: str, item_id: int) -> EmbedItemContent | None:
        """Read an item's embeddable content, or ``None`` if it no longer exists."""
        response = await self._http.get(
            f"{EMBED_PATH}/{kind}/{item_id}", headers=self._headers(user_id)
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return EmbedItemContent.model_validate(response.json())

    async def put_vector(self, user_id: int, kind: str, item_id: int, write: VectorWrite) -> str:
        """Write the vector back; returns the backend's applied/skipped status."""
        response = await self._http.put(
            f"{EMBED_PATH}/{kind}/{item_id}",
            headers=self._headers(user_id),
            json=write.model_dump(),
        )
        response.raise_for_status()
        status = response.json()["status"]
        return str(status)

    async def delete_vector(self, user_id: int, kind: str, item_id: int) -> None:
        """Remove an item's vector (idempotent; a missing vector is a no-op).

        A ``POST .../purge`` rather than a ``DELETE``: the internal app exposes no
        DELETE routes (permanent delete is web-human-only), so the worker's vector
        removal rides a POST.
        """
        response = await self._http.post(
            f"{EMBED_PATH}/{kind}/{item_id}/purge", headers=self._headers(user_id)
        )
        response.raise_for_status()


def create_internal_http_client(base_url: str) -> httpx.AsyncClient:
    """Build the ``httpx.AsyncClient`` bound to the backend internal base URL."""
    return httpx.AsyncClient(base_url=base_url, timeout=_DEFAULT_TIMEOUT_SECONDS)
