"""The embedding provider: a narrow interface with one P0 implementation.

The provider is the only external AI dependency, kept behind a small interface so
it is swappable and faked in tests. It is constructed once at the composition root
and injected into the synchronous fast-path (backend) and, as a mirror, into the
worker; a fake is injected in tests so no test ever calls OpenAI.

The P0 implementation calls OpenAI's embeddings endpoint over an injected
``httpx.AsyncClient`` (bound to the API base with the bearer set), so tests can
substitute a mock transport and the client's lifecycle is owned by the caller.
The dimension is pinned to the column at migration time; the provider asserts its
own dimension so a provider/column mismatch fails loudly rather than writing a
wrong-width vector.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL

if TYPE_CHECKING:
    import httpx


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns texts into vectors. One vector per input, in input order."""

    @property
    def model(self) -> str:
        """The model identifier stored as each vector's provenance."""
        ...

    @property
    def dimension(self) -> int:
        """The output vector width; must match the ``embeddings.vector`` column."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input in the same order."""
        ...


# OpenAI's embeddings endpoint, relative to the API base URL the client is bound to.
_EMBEDDINGS_PATH = "/v1/embeddings"


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
        column width. Raises for a non-2xx response so the caller (the worker's
        retry, or the fast-path's best-effort guard) handles a provider outage.
        """
        if not texts:
            return []
        response = await self._http.post(
            _EMBEDDINGS_PATH,
            json={"model": self._model, "input": texts, "dimensions": self._dimension},
        )
        response.raise_for_status()
        payload = response.json()
        # OpenAI returns ``data`` sorted by ``index``; sort defensively so the
        # returned order matches the input order regardless of server ordering.
        rows = sorted(payload["data"], key=lambda row: row["index"])
        return [row["embedding"] for row in rows]
