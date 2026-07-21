"""Unit test for the worker's OpenAI provider over a mock transport (no live call)."""

from __future__ import annotations

import json

import httpx

from floresu_worker.provider import EMBEDDING_DIMENSION, EMBEDDING_MODEL, OpenAIEmbeddingProvider


def _provider(handler: httpx.MockTransport) -> OpenAIEmbeddingProvider:
    client = httpx.AsyncClient(base_url="https://api.openai.test", transport=handler)
    return OpenAIEmbeddingProvider(client)


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

    vectors = await _provider(httpx.MockTransport(handler)).embed(["a", "b"])

    assert vectors == [[1.0], [2.0]]
    body = json.loads(captured[0].content)
    assert body["model"] == EMBEDDING_MODEL
    assert body["input"] == ["a", "b"]
    assert body["dimensions"] == EMBEDDING_DIMENSION


async def test_embed_empty_batch_makes_no_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("no request for an empty batch")

    assert await _provider(httpx.MockTransport(handler)).embed([]) == []


async def test_provider_exposes_pinned_model_and_dimension() -> None:
    provider = _provider(httpx.MockTransport(lambda _r: httpx.Response(200, json={"data": []})))
    assert provider.model == EMBEDDING_MODEL
    assert provider.dimension == EMBEDDING_DIMENSION
