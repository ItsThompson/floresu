"""The worker's embedding provider: the narrow interface plus the OpenAI P0 impl.

The worker embeds an item's text in its own process (between reading the item and
writing the vector back over the internal API), so it holds the provider directly.
The interface and the OpenAI implementation mirror the backend's
``floresu.embedding.provider``; the two deployables share no code, so each owns a
copy, and a fake is injected in tests so no test calls OpenAI. The model and
dimension are pinned to the backend's ``embeddings`` column: changing them is a
backend migration, not a worker config flip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx

# Pinned to the backend's ``embeddings.vector`` column (see
# ``floresu.embedding.config``). Mirrored here, not configured.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

_EMBEDDINGS_PATH = "/v1/embeddings"


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns texts into vectors. One vector per input, in input order."""

    @property
    def model(self) -> str:
        """The model identifier stored as each vector's provenance."""
        ...

    @property
    def dimension(self) -> int:
        """The output vector width; must match the backend column."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input in the same order."""
        ...


class OpenAIEmbeddingProvider:
    """The P0 provider: OpenAI ``text-embedding-3-small`` (1536 dimensions)."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        model: str = EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self._http = http_client
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch via OpenAI, preserving input order.

        Requests a fixed output dimension so the vectors always match the pinned
        column width, and raises for a non-2xx response so the arq job retries on a
        provider outage.
        """
        if not texts:
            return []
        response = await self._http.post(
            _EMBEDDINGS_PATH,
            json={"model": self._model, "input": texts, "dimensions": self._dimension},
        )
        response.raise_for_status()
        payload = response.json()
        rows = sorted(payload["data"], key=lambda row: row["index"])
        return [row["embedding"] for row in rows]
