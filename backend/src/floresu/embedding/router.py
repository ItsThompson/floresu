"""Internal-only HTTP adapter for the embedding pipeline (the worker's hop).

The arq worker reads an item's embeddable text and writes its vector back over
these three routes on the internal app; they are never mounted on the external
app (a browser never embeds). Thin handlers: each resolves the trusted-header
``user_id`` and calls exactly one :class:`EmbeddingService` method. The gate,
provider call, and transaction all live in the service.

``kind`` is the corpus discriminator (``worklog | bullet | source``); FastAPI
validates it against the enum. ``user_id`` arrives as the trusted ``X-User-ID``
string and is handed to the service, which casts it to the bigint PK at its own
method boundary (a router performs no identity casting).
Purge is a ``POST .../purge``, not a ``DELETE``: the internal (agent-facing) app
exposes no DELETE routes, so the worker's vector removal rides a POST.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response

from floresu.core.errors import NotFound
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.schemas import CorpusItem, StoreResult, VectorWrite
from floresu.embedding.service import EmbeddingService

Identity = Callable[..., Any]  # resolves the trusted-header user_id (str)
EmbeddingServiceProvider = Callable[..., Any]

EMBED_PATH = "/embed/items"


def create_embedding_router(
    service_provider: EmbeddingServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the internal /embed/items router, injecting the service and identity."""
    router = APIRouter(prefix=EMBED_PATH, tags=["embedding"])

    @router.get("/{kind}/{item_id}")
    async def read_item(
        kind: EmbedItemKind,
        item_id: int,
        user_id: str = Depends(identity),
        service: EmbeddingService = Depends(service_provider),
    ) -> CorpusItem:
        item = await service.resolve_item(user_id, kind, item_id)
        if item is None:
            raise NotFound(f"No {kind.value} with id {item_id}.")
        return item

    @router.put("/{kind}/{item_id}")
    async def store_vector(
        kind: EmbedItemKind,
        item_id: int,
        body: VectorWrite,
        user_id: str = Depends(identity),
        service: EmbeddingService = Depends(service_provider),
    ) -> StoreResult:
        outcome = await service.store_vector(
            user_id, kind, item_id, body.content_hash, body.vector, body.model
        )
        return StoreResult(status=outcome)

    @router.post("/{kind}/{item_id}/purge", status_code=204)
    async def purge_vector(
        kind: EmbedItemKind,
        item_id: int,
        user_id: str = Depends(identity),
        service: EmbeddingService = Depends(service_provider),
    ) -> Response:
        await service.delete_vector(user_id, kind, item_id)
        return Response(status_code=204)

    return router
