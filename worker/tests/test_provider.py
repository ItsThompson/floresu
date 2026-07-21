"""Unit test for the worker's OpenAI provider over a mock transport (no live call)."""

from __future__ import annotations

import json

import httpx

from floresu_worker.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from floresu_worker.provider import OpenAIEmbeddingProvider


def _provider(
    handler: httpx.MockTransport, *, dimension: int = EMBEDDING_DIMENSION
) -> OpenAIEmbeddingProvider:
    client = httpx.AsyncClient(base_url="https://api.openai.test", transport=handler)
    return OpenAIEmbeddingProvider(client, dimension=dimension)


async def test_embed_posts_batch_and_returns_vectors_in_order() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2.0]},
                    {"index": 0, "embedding": [1.0]},
                ]
            },
        )

    # A test-sized dimension so the mock's 1-wide vectors pass the width guard.
    vectors = await _provider(httpx.MockTransport(handler), dimension=1).embed(["a", "b"])

    assert vectors == [[1.0], [2.0]]
    body = json.loads(captured[0].content)
    assert body["model"] == EMBEDDING_MODEL
    assert body["input"] == ["a", "b"]
    assert body["dimensions"] == 1


async def test_embed_raises_on_a_wrong_width_vector() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})

    provider = _provider(httpx.MockTransport(handler), dimension=1536)
    try:
        await provider.embed(["x"])
    except ValueError:
        return
    raise AssertionError("expected a ValueError for a wrong-width vector")


async def test_embed_empty_batch_makes_no_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("no request for an empty batch")

    assert await _provider(httpx.MockTransport(handler)).embed([]) == []


async def test_provider_exposes_pinned_model_and_dimension() -> None:
    provider = _provider(httpx.MockTransport(lambda _r: httpx.Response(200, json={"data": []})))
    assert provider.model == EMBEDDING_MODEL
    assert provider.dimension == EMBEDDING_DIMENSION
