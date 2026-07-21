"""End-to-end contract tests for the resume render surface on both app shapes.

Drives the real render router and service through ``TestClient`` with in-memory
doubles for Postgres, R2, and Typst. Asserts the template list, that preview returns
a streamed ``application/pdf`` and never persists, that export returns the object key
and a download URL and persists to the fake store, that the trusted-header boundary
carries the named-agent actor into the published RENDER event, and that the static
``/resumes/templates`` route is matched ahead of the resumes ``/{resume_id}`` route.
No database, R2, or Typst binary is required.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import ActorType, resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.events import WriteEvent
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.rendering.module import RenderModule
from floresu.resumes.cow import EditChannel
from floresu.resumes.render_router import create_resume_render_router
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.router import create_resumes_router
from floresu.resumes.service import ResumeService
from tests.rendering_fakes import (
    FakeTypstCompiler,
    InMemoryIdentityResolver,
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
    identity_resolver = InMemoryIdentityResolver()
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    store = FakeObjectStore()
    publisher, captured = capturing_publisher()

    def render_provider(request: Request) -> ResumeRenderService:
        return ResumeRenderService(
            cast("AsyncSession", FakeSession()),
            render_repo,
            InMemoryBulletTextResolver(),
            identity_resolver,
            module,
            store,
            request.app.state.events,
        )

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

    render_router = create_resume_render_router(render_provider, identity=identity, actor=actor)
    resumes_router = create_resumes_router(
        resume_provider, identity=identity, actor=actor, channel=channel
    )
    # Mount order mirrors the apps: render before resumes, so /resumes/templates wins.
    app = create_app(
        settings,
        routers=[render_router, resumes_router],
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


def test_list_templates_is_matched_ahead_of_the_resume_detail_route(
    make_settings: MakeSettings,
) -> None:
    client, _repo, _captured = _client(make_settings, internal=False)

    response = client.get("/resumes/templates")

    assert response.status_code == 200
    ids = [entry["id"] for entry in response.json()]
    assert "classic" in ids


def test_preview_streams_a_pdf_and_never_persists(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=False)
    repo.seed_resume(resume_row(resume_id=1, user_id=1, document=build_resolved_document()))

    response = client.post("/resumes/1/preview", json={})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.7 fake"
    assert captured == []


def test_preview_missing_resume_is_a_problem_json_404(make_settings: MakeSettings) -> None:
    client, _repo, _captured = _client(make_settings, internal=False)

    response = client.post("/resumes/999/preview", json={})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "NOT_FOUND"


def test_export_persists_and_returns_the_key_and_download_url(make_settings: MakeSettings) -> None:
    client, repo, _captured = _client(make_settings, internal=False)
    document = build_resolved_document()
    repo.seed_resume(resume_row(resume_id=7, user_id=1, document=document))
    repo.seed_revision(revision_row(resume_id=7, revision_no=2, document=document))

    response = client.post("/resumes/7/export")

    assert response.status_code == 200
    body = response.json()
    assert body["object_key"] == "u/1/r/7/rev/2.pdf"
    assert body["revision"] == 2
    assert body["download_url"].endswith("u/1/r/7/rev/2.pdf?signed=1")
    assert repo.pdf_keys[(7, 2)] == "u/1/r/7/rev/2.pdf"


def test_internal_export_records_the_named_agent_actor(make_settings: MakeSettings) -> None:
    client, repo, captured = _client(make_settings, internal=True)
    document = build_resolved_document()
    repo.seed_resume(resume_row(resume_id=7, user_id=1, document=document))
    repo.seed_revision(revision_row(resume_id=7, revision_no=1, document=document))

    response = client.post("/resumes/7/export", headers=_headers(internal=True))

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0].actor.type is ActorType.AGENT
    assert captured[0].actor.label == "claude"


def test_internal_surface_denies_without_the_token(make_settings: MakeSettings) -> None:
    client, _repo, _captured = _client(make_settings, internal=True)

    response = client.get("/resumes/templates")

    assert response.status_code == 401
