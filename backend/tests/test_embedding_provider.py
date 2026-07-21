"""Unit test for the OpenAI embedding provider over a mock transport.

Substitutes httpx's ``MockTransport`` so no live OpenAI call is made: it asserts
the request shape (model, input batch, pinned dimension) and that the response's
vectors are returned in input order regardless of the server's ordering.
"""

from __future__ import annotations

import json

import httpx

from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from floresu.embedding.provider import OpenAIEmbeddingProvider


def _provider(
    handler: httpx.MockTransport, *, dimension: int = EMBEDDING_DIMENSION
) -> OpenAIEmbeddingProvider:
    client = httpx.AsyncClient(base_url="https://api.openai.test", transport=handler)
    return OpenAIEmbeddingProvider(client, dimension=dimension)


async def test_embed_posts_the_batch_and_returns_vectors_in_order() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        # Return rows out of order to prove the provider sorts by index.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2.0, 2.0]},
                    {"index": 0, "embedding": [1.0, 1.0]},
                ]
            },
        )

    # A test-sized dimension so the mock's 2-wide vectors pass the width guard.
    provider = _provider(httpx.MockTransport(handler), dimension=2)
    vectors = await provider.embed(["first", "second"])

    assert vectors == [[1.0, 1.0], [2.0, 2.0]]
    request = captured[0]
    assert request.url.path == "/v1/embeddings"
    body = json.loads(request.content)
    assert body["model"] == EMBEDDING_MODEL
    assert body["input"] == ["first", "second"]
    assert body["dimensions"] == 2


async def test_embed_empty_batch_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("no request expected for an empty batch")

    provider = _provider(httpx.MockTransport(handler))
    assert await provider.embed([]) == []


async def test_provider_exposes_pinned_model_and_dimension() -> None:
    provider = _provider(httpx.MockTransport(lambda _r: httpx.Response(200, json={"data": []})))
    assert provider.model == EMBEDDING_MODEL
    assert provider.dimension == EMBEDDING_DIMENSION


async def test_embed_raises_on_provider_error() -> None:
    provider = _provider(httpx.MockTransport(lambda _r: httpx.Response(500, json={"error": "x"})))
    try:
        await provider.embed(["boom"])
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected an HTTPStatusError for a 5xx provider response")


async def test_embed_raises_on_a_wrong_width_vector() -> None:
    # A provider that ignores the dimensions param must fail loudly, not store a
    # wrong-width vector.
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})

    provider = _provider(httpx.MockTransport(handler), dimension=EMBEDDING_DIMENSION)
    try:
        await provider.embed(["x"])
    except ValueError:
        return
    raise AssertionError("expected a ValueError for a wrong-width vector")
