"""End-to-end contract tests for the resume revision surface on both app shapes.

Drives the real revision router and service through ``TestClient`` with in-memory
doubles for Postgres and R2. Asserts the published-version list (newest first, empty
when none), that a per-version request returns a download URL and never leaks the R2
object key, that a missing or unpublished revision is a problem+json 404, that the
reads publish no write event, that the trusted-header boundary denies without the
token, and that ``/resumes/{id}/revisions`` resolves to the revision handler even when
the resumes router is mounted first. No database or R2 is required.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.events import WriteEvent
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.resumes.cow import EditChannel
from floresu.resumes.revision_router import create_resume_revision_router
from floresu.resumes.revision_service import ResumeRevisionService
from floresu.resumes.router import create_resumes_router
from floresu.resumes.service import ResumeService
from tests.rendering_fakes import (
    InMemoryRenderRepository,
    build_resolved_document,
    resume_row,
    revision_row,
)
from tests.resumes_fakes import (
    FakeSession,
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
    build_bullet_writer,
    capturing_publisher,
)
from tests.storage_fakes import FakeObjectStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "claude",
}


def _client(
    make_settings: MakeSettings, *, internal: bool
) -> tuple[TestClient, InMemoryRenderRepository, list[WriteEvent]]:
    render_repo = InMemoryRenderRepository()
    store = FakeObjectStore()
    publisher, captured = capturing_publisher()

    def revision_provider(_request: Request) -> ResumeRevisionService:
        return ResumeRevisionService(render_repo, store)

    def resume_provider(request: Request) -> ResumeService:
        session = cast("AsyncSession", FakeSession())
        return ResumeService(
            session,
            InMemoryResumeRepository(),
            InMemoryBulletTextResolver(),
            request.app.state.events,
            build_bullet_writer(session, request.app.state.events),
        )

    identity: Callable[..., Any]
    actor: Callable[..., Any]
    if internal:
        identity, actor = require_internal_user, resolve_internal_actor
        channel = EditChannel.MCP
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        identity, actor = require_user, resolve_web_actor
        channel = EditChannel.WEB
        settings = make_settings(service="floresu-external", environment="development")

    revision_router = create_resume_revision_router(revision_provider, identity=identity)
    resumes_router = create_resumes_router(
        resume_provider, identity=identity, actor=actor, channel=channel
    )
    # Resumes router mounted FIRST, to prove the /revisions suffix resolves to the
    # revision handler regardless of mount order (no collision with /{resume_id}).
    app = create_app(
        settings,
        routers=[resumes_router, revision_router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.events = publisher

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, render_repo, captured


def _headers(*, internal: bool) -> dict[str, str]:
    return _INTERNAL_HEADERS if internal else {}


def _seed_resume(repo: InMemoryRenderRepository, *, resume_id: int, user_id: int = 1) -> None:
    repo.seed_resume(
        resume_row(resume_id=resume_id, user_id=user_id, document=build_resolved_document())
    )


def _seed_published(
    repo: InMemoryRenderRepository, *, resume_id: int, revision_no: int, key: str
) -> None:
    """Seed a published version: a revision whose PDF was stored (``created_at`` set)."""
    repo.seed_revision(
        revision_row(
            resume_id=resume_id,
            revision_no=revision_no,
            document=build_resolved_document(),
            pdf_object_key=key,
            created_at=datetime(2026, 1, revision_no, tzinfo=UTC),
        )
    )


def _seed_snapshot(repo: InMemoryRenderRepository, *, resume_id: int, revision_no: int) -> None:
    """Seed a plain per-save snapshot: a revision with no stored PDF (never listed)."""
    repo.seed_revision(
        revision_row(
            resume_id=resume_id,
            revision_no=revision_no,
            document=build_resolved_document(),
            created_at=datetime(2026, 1, revision_no, tzinfo=UTC),
        )
    )


def test_list_returns_published_versions_newest_first(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7)
    _seed_published(repo, resume_id=7, revision_no=2, key="k2")
    _seed_published(repo, resume_id=7, revision_no=5, key="k5")
    _seed_snapshot(repo, resume_id=7, revision_no=3)  # no PDF: excluded

    response = client.get("/resumes/7/revisions")

    assert response.status_code == 200
    body = response.json()
    assert body["resume_id"] == 7
    assert [version["revision_no"] for version in body["versions"]] == [5, 2]
    assert captured == []  # a read publishes no write event


def test_list_is_empty_when_no_version_is_published(make_settings: MakeSettings) -> None:
    client, repo, _captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7)

    response = client.get("/resumes/7/revisions")

    assert response.status_code == 200
    assert response.json() == {"resume_id": 7, "versions": []}


def test_version_pdf_returns_a_download_url_and_never_leaks_the_object_key(
    make_settings: MakeSettings,
) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7)
    _seed_published(repo, resume_id=7, revision_no=4, key="u/1/r/7/rev/4.pdf")

    response = client.get("/resumes/7/revisions/4/pdf")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "resume_id": 7,
        "revision_no": 4,
        "download_url": "https://fake-r2.local/u/1/r/7/rev/4.pdf?signed=1",
    }
    assert "object_key" not in body
    assert captured == []


def test_version_pdf_missing_revision_is_a_problem_json_404(make_settings: MakeSettings) -> None:
    client, repo, _captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7)

    response = client.get("/resumes/7/revisions/99/pdf")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "NOT_FOUND"


def test_version_pdf_unpublished_revision_is_a_404(make_settings: MakeSettings) -> None:
    client, repo, _captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7)
    _seed_snapshot(repo, resume_id=7, revision_no=1)  # exists but no stored PDF

    response = client.get("/resumes/7/revisions/1/pdf")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_another_accounts_resume_is_a_404_with_no_existence_leak(
    make_settings: MakeSettings,
) -> None:
    client, repo, _captured = _client(make_settings, internal=False)
    _seed_resume(repo, resume_id=7, user_id=2)  # owned by another account
    _seed_published(repo, resume_id=7, revision_no=1, key="k")

    listing = client.get("/resumes/7/revisions")
    pdf = client.get("/resumes/7/revisions/1/pdf")

    assert listing.status_code == 404
    assert pdf.status_code == 404


def test_internal_boundary_lists_over_the_trusted_header(make_settings: MakeSettings) -> None:
    client, repo, _captured = _client(make_settings, internal=True)
    _seed_resume(repo, resume_id=7)
    _seed_published(repo, resume_id=7, revision_no=1, key="k")

    response = client.get("/resumes/7/revisions", headers=_headers(internal=True))

    assert response.status_code == 200
    assert [version["revision_no"] for version in response.json()["versions"]] == [1]


def test_internal_surface_denies_without_the_token(make_settings: MakeSettings) -> None:
    client, _repo, _captured = _client(make_settings, internal=True)

    response = client.get("/resumes/7/revisions")

    assert response.status_code == 401
