"""End-to-end contract tests for the web-only lifecycle surface.

Drives the real router, service, and write-event seam through ``TestClient`` with
in-memory repositories substituted for Postgres. Asserts the ``DELETE`` +
confirmation contract, the deletion receipt, RFC 9457 problem+json on the failure
paths, the export download, and account deletion on the external (cookie)
boundary. Cascade correctness against real FKs lives in the integration suite; the
absence of every route from the internal app lives in the boundary test.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.accounts.config import build_cookie_config
from floresu.core.actor import ActorType, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.events import WriteEvent
from floresu.core.identity import SESSION_COOKIE_NAME, require_user
from floresu.core.settings import AppSettings
from floresu.lifecycle.router import create_lifecycle_router
from floresu.lifecycle.service import LifecycleService
from tests.embedding_fakes import InMemoryEmbeddingRepository
from tests.lifecycle_fakes import (
    FakeSession,
    InMemoryExportRepository,
    InMemoryLifecycleRepository,
    build_account,
    capturing_publisher,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MakeSettings = Callable[..., AppSettings]


def _client(
    make_settings: MakeSettings,
    *,
    repo: InMemoryLifecycleRepository | None = None,
    export_repo: InMemoryExportRepository | None = None,
    embeddings: InMemoryEmbeddingRepository | None = None,
) -> tuple[TestClient, InMemoryEmbeddingRepository, list[WriteEvent]]:
    repo = repo or InMemoryLifecycleRepository()
    export_repo = export_repo or InMemoryExportRepository(account=build_account(1))
    embeddings = embeddings or InMemoryEmbeddingRepository()
    publisher, captured = capturing_publisher()

    def provider(request: Request) -> LifecycleService:
        return LifecycleService(
            cast("AsyncSession", FakeSession()), repo, export_repo, embeddings, publisher
        )

    settings = make_settings(service="floresu-external", environment="development")
    router = create_lifecycle_router(
        provider,
        identity=require_user,
        actor=resolve_web_actor,
        cookie_config=build_cookie_config(settings),
    )
    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())
    app.state.events = publisher

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, embeddings, captured


def test_permanent_delete_worklog_returns_a_receipt_and_purges(
    make_settings: MakeSettings,
) -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_worklog(1, 5, "Shipped search")
    client, _, captured = _client(make_settings, repo=repo)

    response = client.request("DELETE", "/worklog/5", params={"confirm": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"entity_type": "worklog", "entity_id": 5, "embedding_purged": True}
    assert captured[-1].action.value == "delete"
    assert captured[-1].actor.type is ActorType.HUMAN


def test_delete_without_confirmation_is_a_422_problem(make_settings: MakeSettings) -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_worklog(1, 5, "x")
    client, _, _ = _client(make_settings, repo=repo)
    # confirm=false is parsed and rejected by the service with a field-level error.
    rejected = client.request("DELETE", "/worklog/5", params={"confirm": "false"})
    assert rejected.status_code == 422
    assert rejected.headers["content-type"] == "application/problem+json"
    assert "confirm" in (rejected.json().get("fields") or {})
    # confirm omitted is a request-validation 422 (the flag is required).
    missing = client.request("DELETE", "/worklog/5")
    assert missing.status_code == 422


def test_delete_missing_entity_is_a_404_problem(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings)
    response = client.request("DELETE", "/resumes/999", params={"confirm": "true"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_permanent_delete_resume_reports_no_vector_purge(make_settings: MakeSettings) -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_resume(1, 9, "Backend Engineer")
    client, _, _ = _client(make_settings, repo=repo)
    response = client.request("DELETE", "/resumes/9", params={"confirm": "true"})
    assert response.status_code == 200
    assert response.json()["embedding_purged"] is False


def test_unauthenticated_delete_is_rejected(make_settings: MakeSettings) -> None:
    client, _, _ = _client(make_settings)
    client.cookies.clear()
    assert client.request("DELETE", "/worklog/5", params={"confirm": "true"}).status_code == 401


def test_export_streams_a_downloadable_archive(make_settings: MakeSettings) -> None:
    export_repo = InMemoryExportRepository(account=build_account(1, email="owner@example.com"))
    client, _, _ = _client(make_settings, export_repo=export_repo)

    response = client.get("/account/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.json()["account"]["email"] == "owner@example.com"


def test_delete_account_returns_a_receipt_and_clears_cookies(make_settings: MakeSettings) -> None:
    repo = InMemoryLifecycleRepository()
    repo.seed_agents(1, count=3)
    client, _, captured = _client(make_settings, repo=repo)

    response = client.request("DELETE", "/account", params={"confirm": "true"})

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "revoked_agent_count": 3}
    assert 1 not in repo.users
    # Deleting the account signs the human out: the session cookie is expired.
    assert "floresu_session" in response.headers.get("set-cookie", "")
    # Account deletion is not audited (the audit rows cascade away with the account).
    assert captured == []
