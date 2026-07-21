"""Tests for the worker's internal-API client over a mock transport.

The security-critical invariant: every call carries the resolved ``X-User-ID``,
the worker ``X-Actor``, and the shared ``X-Internal-Api-Token``. A 404 on read
means the item is gone (``None``); other error statuses raise so the job retries.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from floresu_worker.client import InternalApiClient
from floresu_worker.config import (
    ACTOR_HEADER,
    INTERNAL_API_TOKEN_HEADER,
    USER_ID_HEADER,
    WORKER_ACTOR,
)
from floresu_worker.schemas import VectorWrite

_TOKEN = "shared-internal-token"


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[InternalApiClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(wrapped))
    return InternalApiClient(http, api_token=SecretStr(_TOKEN)), captured


async def test_get_item_sends_trusted_headers_and_parses_content() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "t", "content_hash": "h1", "archived": False})

    client, captured = _client(handler)
    item = await client.get_item(42, "worklog", 5)

    assert item is not None
    assert item.text == "t"
    assert item.content_hash == "h1"
    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/embed/items/worklog/5"
    assert request.headers[USER_ID_HEADER] == "42"
    assert request.headers[ACTOR_HEADER] == WORKER_ACTOR
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == _TOKEN


async def test_get_item_returns_none_on_404() -> None:
    client, _captured = _client(lambda _r: httpx.Response(404, json={"detail": "gone"}))
    assert await client.get_item(1, "worklog", 5) is None


async def test_get_item_raises_on_server_error() -> None:
    client, _captured = _client(lambda _r: httpx.Response(503, json={"detail": "down"}))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_item(1, "worklog", 5)


async def test_put_vector_posts_the_payload_and_returns_status() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "applied"})

    client, captured = _client(handler)
    write = VectorWrite(content_hash="h1", vector=[0.1, 0.2], model="m")
    status = await client.put_vector(7, "bullet", 3, write)

    assert status == "applied"
    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/embed/items/bullet/3"
    assert json.loads(request.content) == {
        "content_hash": "h1",
        "vector": [0.1, 0.2],
        "model": "m",
    }
    assert request.headers[USER_ID_HEADER] == "7"


async def test_delete_vector_issues_a_purge_post() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client, captured = _client(handler)
    await client.delete_vector(9, "source", 2)

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/embed/items/source/2/purge"
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == _TOKEN
