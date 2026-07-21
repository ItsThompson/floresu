"""In-memory test doubles for the worker's embed jobs.

The tasks run over a fake internal-API client, a fake provider, and a fake Redis
(for the queue-depth sample), so no test touches a live backend, OpenAI, or Redis.
"""

from __future__ import annotations

from floresu_worker.schemas import EmbedItemContent, VectorWrite


class FakeInternalClient:
    """Records calls and returns seeded item content and a canned store status."""

    def __init__(
        self, *, item: EmbedItemContent | None = None, put_status: str = "applied"
    ) -> None:
        self._item = item
        self._put_status = put_status
        self.gets: list[tuple[int, str, int]] = []
        self.puts: list[tuple[int, str, int, VectorWrite]] = []
        self.deletes: list[tuple[int, str, int]] = []

    async def get_item(self, user_id: int, kind: str, item_id: int) -> EmbedItemContent | None:
        self.gets.append((user_id, kind, item_id))
        return self._item

    async def put_vector(self, user_id: int, kind: str, item_id: int, write: VectorWrite) -> str:
        self.puts.append((user_id, kind, item_id, write))
        return self._put_status

    async def delete_vector(self, user_id: int, kind: str, item_id: int) -> None:
        self.deletes.append((user_id, kind, item_id))


class FailingClient(FakeInternalClient):
    """A client whose read raises, to exercise the job's failure path."""

    async def get_item(self, user_id: int, kind: str, item_id: int) -> EmbedItemContent | None:
        raise RuntimeError("backend unreachable")


class FakeProvider:
    """A provider returning a fixed-width vector and recording its calls."""

    def __init__(self, *, model: str = "fake-model", dimension: int = 4) -> None:
        self._model = model
        self._dimension = dimension
        self.calls: list[list[str]] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[1.0] * self._dimension for _ in texts]


class FakeRedis:
    """A stand-in for the arq Redis exposing the queue-depth read."""

    def __init__(self, depth: int = 0) -> None:
        self._depth = depth
        self.zcard_calls: list[str] = []

    async def zcard(self, name: str) -> int:
        self.zcard_calls.append(name)
        return self._depth
