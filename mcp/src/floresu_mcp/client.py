"""Thin client of the backend internal API (:8001).

Each MCP tool call becomes one HTTP call to the backend internal app over
``app-net``. This client owns the one security-critical invariant of that hop:
**every** request carries the resolved ``X-User-ID`` (the token ``sub``) plus the
named-agent ``X-Actor`` (the token ``client_id``) plus the shared
``X-Internal-Api-Token``, and the agent's OAuth bearer token is **never**
forwarded (confused-deputy defense). The trusted headers are applied **last**, so
a caller-supplied ``extra_headers`` can never override them.

The correlation ``X-Request-ID`` bound for this agent action rides along so the
backend logs share the same id (the MCP -> backend hop is traceable). The named
methods mirror the internal routes op-for-op; the tool layer maps their responses
to lean tool outputs. The ``httpx.AsyncClient`` is injected (bound to the backend
internal base URL) so tests substitute a transport without a live backend.

The read methods below back the read tool surface; each is a single GET (or the
search POST) mirroring one internal route. The write method surface mirroring the
remaining routes lands with the write tools in a later ticket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog
from mcp.server.fastmcp.exceptions import ToolError

from floresu_mcp.config import (
    ACTOR_HEADER,
    INTERNAL_API_TOKEN_HEADER,
    REQUEST_ID_HEADER,
    USER_ID_HEADER,
)

if TYPE_CHECKING:
    from pydantic import SecretStr

    from floresu_mcp.settings import RsSettings

# Bound so a hung internal call cannot pin an MCP worker indefinitely.
_DEFAULT_TIMEOUT_SECONDS = 10.0


class InternalApiClient:
    """Forwards user-scoped calls to the backend internal app."""

    def __init__(self, http_client: httpx.AsyncClient, *, api_token: SecretStr) -> None:
        self._http = http_client
        self._api_token = api_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: str,
        actor: str,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """One internal call scoped to ``user_id`` and attributed to ``actor``.

        The trusted identity + actor + shared-secret headers are applied last, so
        they can never be overridden by ``extra_headers`` and the agent token is
        never propagated (only ``user_id`` + ``actor`` cross this boundary). The
        correlation ``request_id`` bound for this agent action rides along as
        ``X-Request-ID`` so the backend logs share the same id.

        A transport failure (the backend unreachable or timed out) is translated
        into a model-recoverable :class:`ToolError` here, so every named method
        inherits a structured "retry shortly" error instead of an opaque transport
        exception. A backend that answers with a >=400 status still returns a
        ``Response``; that path is handled by
        :func:`floresu_mcp.tool_errors.raise_for_problem`, not this ``except``.
        """
        headers = dict(extra_headers or {})
        # Applied last so a caller cannot override the trust boundary. The agent
        # bearer is never among these: only the resolved identity crosses the hop.
        headers[USER_ID_HEADER] = user_id
        headers[ACTOR_HEADER] = actor
        # Unwrap the SecretStr only here, at the single wire-header use site; the
        # raw value is never logged.
        headers[INTERNAL_API_TOKEN_HEADER] = self._api_token.get_secret_value()
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if request_id is not None:
            headers[REQUEST_ID_HEADER] = str(request_id)
        try:
            return await self._http.request(method, path, json=json, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ToolError(
                "backend_unavailable: the Floresu service is unreachable or timed out; "
                "retry shortly."
            ) from exc

    async def worklog_list(
        self, user_id: str, actor: str, *, include_archived: bool = False
    ) -> httpx.Response:
        """List the user's worklog entries (``GET /worklog``)."""
        return await self._request(
            "GET",
            "/worklog",
            user_id=user_id,
            actor=actor,
            params={"include_archived": include_archived},
        )

    async def worklog_create(self, user_id: str, actor: str, body: Any) -> httpx.Response:
        """Create a worklog entry (``POST /worklog``)."""
        return await self._request("POST", "/worklog", user_id=user_id, actor=actor, json=body)

    async def worklog_get(self, user_id: str, actor: str, worklog_id: int) -> httpx.Response:
        """Get one worklog entry with its sources, tags, and framing bullets
        (``GET /worklog/{id}``)."""
        return await self._request("GET", f"/worklog/{worklog_id}", user_id=user_id, actor=actor)

    async def list_tags(self, user_id: str, actor: str) -> httpx.Response:
        """List the user's existing tag labels for reuse (``GET /worklog/tags``)."""
        return await self._request("GET", "/worklog/tags", user_id=user_id, actor=actor)

    async def sources_list(
        self, user_id: str, actor: str, *, kind: str | None = None, include_archived: bool = False
    ) -> httpx.Response:
        """List profile sources, optionally of one kind (``GET /sources``)."""
        return await self._request(
            "GET",
            "/sources",
            user_id=user_id,
            actor=actor,
            params={"kind": kind, "include_archived": include_archived},
        )

    async def source_get(self, user_id: str, actor: str, source_id: int) -> httpx.Response:
        """Get one profile source with its typed detail (``GET /sources/{id}``)."""
        return await self._request("GET", f"/sources/{source_id}", user_id=user_id, actor=actor)

    async def skills_list(
        self, user_id: str, actor: str, *, include_archived: bool = False
    ) -> httpx.Response:
        """List the user's skills (``GET /skills``)."""
        return await self._request(
            "GET",
            "/skills",
            user_id=user_id,
            actor=actor,
            params={"include_archived": include_archived},
        )

    async def skill_get(self, user_id: str, actor: str, skill_id: int) -> httpx.Response:
        """Get one skill (``GET /skills/{id}``)."""
        return await self._request("GET", f"/skills/{skill_id}", user_id=user_id, actor=actor)

    async def variants_list(
        self, user_id: str, actor: str, *, include_archived: bool = False
    ) -> httpx.Response:
        """List the user's identity variants (``GET /identity-variants``)."""
        return await self._request(
            "GET",
            "/identity-variants",
            user_id=user_id,
            actor=actor,
            params={"include_archived": include_archived},
        )

    async def variant_get(self, user_id: str, actor: str, variant_id: int) -> httpx.Response:
        """Get one identity variant (``GET /identity-variants/{id}``)."""
        return await self._request(
            "GET", f"/identity-variants/{variant_id}", user_id=user_id, actor=actor
        )

    async def bullets_list(
        self, user_id: str, actor: str, *, include_archived: bool = False
    ) -> httpx.Response:
        """List the user's canonical library bulletpoints (``GET /bullets``)."""
        return await self._request(
            "GET",
            "/bullets",
            user_id=user_id,
            actor=actor,
            params={"include_archived": include_archived},
        )

    async def bullet_get(self, user_id: str, actor: str, bullet_id: int) -> httpx.Response:
        """Get one canonical bulletpoint with its provenance edges (``GET /bullets/{id}``)."""
        return await self._request("GET", f"/bullets/{bullet_id}", user_id=user_id, actor=actor)

    async def resumes_list(
        self, user_id: str, actor: str, *, kind: str | None = None, include_archived: bool = False
    ) -> httpx.Response:
        """List the user's living and application resumes (``GET /resumes``)."""
        return await self._request(
            "GET",
            "/resumes",
            user_id=user_id,
            actor=actor,
            params={"kind": kind, "include_archived": include_archived},
        )

    async def resume_get(self, user_id: str, actor: str, resume_id: int) -> httpx.Response:
        """Get one resume with its full document (``GET /resumes/{id}``)."""
        return await self._request("GET", f"/resumes/{resume_id}", user_id=user_id, actor=actor)

    async def list_templates(self, user_id: str, actor: str) -> httpx.Response:
        """List the available global render templates (``GET /resumes/templates``)."""
        return await self._request("GET", "/resumes/templates", user_id=user_id, actor=actor)

    async def search(self, user_id: str, actor: str, body: Any) -> httpx.Response:
        """Run hybrid search over the corpus (``POST /search``)."""
        return await self._request("POST", "/search", user_id=user_id, actor=actor, json=body)


def create_internal_http_client(settings: RsSettings) -> httpx.AsyncClient:
    """Build the ``httpx.AsyncClient`` bound to the backend internal base URL."""
    return httpx.AsyncClient(
        base_url=settings.backend_internal_url,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
    )
