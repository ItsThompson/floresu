"""Internal-client tests: the RS -> backend internal hop.

The security-critical invariant: every call carries the resolved ``X-User-ID``,
the named-agent ``X-Actor``, and the shared ``X-Internal-Api-Token``; the agent's
bearer token is never forwarded; and a caller cannot override the trusted headers
(they are applied last). Uses httpx's ``MockTransport`` to capture the outgoing
request without a live backend.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
import structlog
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import SecretStr

from floresu_mcp.client import InternalApiClient
from floresu_mcp.config import (
    ACTOR_HEADER,
    INTERNAL_API_TOKEN_HEADER,
    REQUEST_ID_HEADER,
    USER_ID_HEADER,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_API_TOKEN = "shared-internal-token"


def _client_with_capture() -> tuple[InternalApiClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[])

    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(handler))
    return InternalApiClient(http, api_token=SecretStr(_API_TOKEN)), captured


async def test_worklog_create_sends_trusted_identity_and_actor_headers() -> None:
    client, captured = _client_with_capture()
    body = {"title": "Shipped the auth boundary", "entry_date": "2026-07-20"}

    await client.worklog_create("user-42", "agent-7", body)

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/worklog"
    assert request.headers[USER_ID_HEADER] == "user-42"
    assert request.headers[ACTOR_HEADER] == "agent-7"
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == _API_TOKEN
    assert json.loads(request.content) == body


async def test_worklog_list_sends_the_include_archived_switch() -> None:
    client, captured = _client_with_capture()

    await client.worklog_list("user-42", "agent-7", include_archived=True)

    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/worklog"
    assert request.url.params.get("include_archived") == "true"
    assert request.headers[USER_ID_HEADER] == "user-42"
    assert request.headers[ACTOR_HEADER] == "agent-7"


async def test_no_bearer_token_is_forwarded_downstream() -> None:
    # The client API takes a resolved user_id + actor, never a token: the agent
    # bearer is exchanged for X-User-ID and cannot leak to the internal app.
    client, captured = _client_with_capture()

    await client.worklog_list("user-42", "agent-7")

    request = captured[0]
    assert "authorization" not in {name.lower() for name in request.headers}


async def test_extra_headers_cannot_override_the_trusted_identity() -> None:
    # A caller-supplied header must never spoof the resolved user, the actor, or
    # the shared secret: the trusted set is applied last.
    client, captured = _client_with_capture()

    await client._request(
        "GET",
        "/worklog",
        user_id="user-42",
        actor="agent-7",
        extra_headers={
            USER_ID_HEADER: "user-evil",
            ACTOR_HEADER: "agent-evil",
            INTERNAL_API_TOKEN_HEADER: "forged",
        },
    )

    request = captured[0]
    assert request.headers[USER_ID_HEADER] == "user-42"
    assert request.headers[ACTOR_HEADER] == "agent-7"
    assert request.headers[INTERNAL_API_TOKEN_HEADER] == _API_TOKEN


async def test_request_forwards_the_bound_request_id() -> None:
    # The correlation id bound for the agent action rides to the backend as
    # X-Request-ID so the hop is traceable end to end.
    client, captured = _client_with_capture()

    structlog.contextvars.bind_contextvars(request_id="corr-abc-123")
    try:
        await client.worklog_list("user-42", "agent-7")
    finally:
        structlog.contextvars.clear_contextvars()

    assert captured[0].headers[REQUEST_ID_HEADER] == "corr-abc-123"


async def test_request_omits_x_request_id_when_none_is_bound() -> None:
    client, captured = _client_with_capture()

    await client.worklog_list("user-42", "agent-7")

    assert REQUEST_ID_HEADER not in captured[0].headers


def _client_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> InternalApiClient:
    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(handler))
    return InternalApiClient(http, api_token=SecretStr(_API_TOKEN))


async def test_connect_error_is_translated_to_a_structured_tool_error() -> None:
    def unreachable(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_transport(unreachable)
    with pytest.raises(ToolError) as excinfo:
        await client.worklog_list("user-42", "agent-7")
    assert "backend_unavailable" in str(excinfo.value)


async def test_timeout_is_translated_to_a_structured_tool_error() -> None:
    def times_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client_with_transport(times_out)
    body = {"title": "x", "entry_date": "2026-07-20"}
    with pytest.raises(ToolError) as excinfo:
        await client.worklog_create("user-42", "agent-7", body)
    assert "backend_unavailable" in str(excinfo.value)


async def test_error_status_response_passes_through_untranslated() -> None:
    # A backend that ANSWERS with a >=400 status is not a transport failure: the
    # response passes through unchanged for raise_for_problem to map.
    def five_hundred(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "INTERNAL"})

    client = _client_with_transport(five_hundred)
    response = await client.worklog_list("user-42", "agent-7")
    assert response.status_code == 500
