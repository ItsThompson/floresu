"""HTTP adapter for search, mounted on both apps with per-boundary identity.

A thin handler: it resolves the caller's ``user_id`` through the injected identity
dependency and calls the one :class:`SearchService` method. The external app
injects the human cookie identity; the internal app injects the trusted-header
identity. Search is read-only (no actor, no write event), so both boundaries share
the same handler and the service holds all retrieval, fusion, and graph logic.

The route is ``POST /search`` (a query with a filter body is a POST, not a GET),
mapped by the MCP ``search_experience`` tool to this internal route (section 07).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.search.schemas import SearchQuery, SearchResult
from floresu.search.service import SearchService

Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
SearchServiceProvider = Callable[..., Any]

SEARCH_PATH = "/search"


def create_search_router(
    service_provider: SearchServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the /search router, injecting the service and the per-app identity."""
    router = APIRouter(prefix=SEARCH_PATH, tags=["search"])

    @router.post("")
    async def search(
        body: SearchQuery,
        user_id: str = Depends(identity),
        service: SearchService = Depends(service_provider),
    ) -> SearchResult:
        return await service.search(user_id, body)

    return router
