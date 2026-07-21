"""End-to-end contract tests for the resume finalize route on both app shapes.

Drives the real finalize router and service through ``TestClient`` with in-memory
doubles for Postgres, R2, and Typst. Asserts finalize returns the frozen artifact
(status finalized, the revision-keyed PDF object key), that a missing resume is a
problem+json 404 and a living resume a 409, and that the trusted-header boundary
carries the named-agent actor. The deep finalize behavior is covered by the service
and integration tests; these pin the HTTP surface on both apps. No database required.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.rendering.module import RenderModule
from floresu.resumes.document import (
    LibraryRefItem,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.finalize_router import create_resume_finalize_router
from floresu.resumes.models import Resume, ResumeKind, ResumeStatus
from tests.jobapps_fakes import FIXED_NOW, InMemoryJobApplicationRepository
from tests.rendering_fakes import FakeTypstCompiler, InMemoryIdentityResolver
from tests.resumes_fakes import (
    FakeSession,
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
    capturing_publisher,
)
from tests.storage_fakes import FakeObjectStore

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "claude",
}
_BULLET_ID = 5


def _draft_resume(resume_id: int, *, kind: ResumeKind = ResumeKind.APPLICATION) -> Resume:
    document = ResumeDocument(
        schema_version=1,
        header=ResumeHeader(),
        template_id="classic",
        sections=[
            ResumeSection(
                id="s-work",
                kind=SectionKind.WORK,
                title="Experience",
                item_order=["i-ref"],
                items={"i-ref": LibraryRefItem(id="i-ref", bullet_id=_BULLET_ID)},
            )
        ],
    )
    return Resume(
        id=resume_id,
        user_id=1,
        kind=kind,
        status=ResumeStatus.DRAFT,
        title="Backend Engineer",
        schema_version=1,
        revision=1,
        document=document.model_dump(mode="json"),
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _client(
    make_settings: MakeSettings, *, internal: bool
) -> tuple[TestClient, InMemoryResumeRepository]:
    repo = InMemoryResumeRepository()
    bullets = InMemoryBulletTextResolver()
    bullets.own_bullet(1, _BULLET_ID, "Shipped the pipeline.")
    identity = InMemoryIdentityResolver()
    store = FakeObjectStore()
    job_apps = InMemoryJobApplicationRepository()
    module = RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl"))
    publisher, _captured = capturing_publisher()

    def provider(_request: Request) -> ResumeFinalizeService:
        return ResumeFinalizeService(
            FakeSession(),  # type: ignore[arg-type]
            repo,
            bullets,
            identity,
            module,
            store,
            job_apps,
            publisher,
            clock=lambda: FIXED_NOW,
        )

    identity_dep: Callable[..., Any]
    actor: Callable[..., Any]
    if internal:
        identity_dep, actor = require_internal_user, resolve_internal_actor
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        identity_dep, actor = require_user, resolve_web_actor
        settings = make_settings(service="floresu-external", environment="development")

    router = create_resume_finalize_router(provider, identity=identity_dep, actor=actor)
    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, repo


def test_finalize_returns_the_frozen_artifact(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    repo.seed(_draft_resume(3))

    response = client.post("/resumes/3/finalize")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finalized"
    assert body["revision_no"] == 2
    assert body["pdf_object_key"] == "u/1/r/3/rev/2.pdf"


def test_finalize_missing_resume_is_a_problem_json_404(make_settings: MakeSettings) -> None:
    client, _repo = _client(make_settings, internal=False)

    response = client.post("/resumes/999/finalize")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "NOT_FOUND"


def test_finalize_of_a_living_resume_is_a_409(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=False)
    repo.seed(_draft_resume(4, kind=ResumeKind.LIVING))

    response = client.post("/resumes/4/finalize")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"


def test_finalize_is_served_on_the_internal_boundary(make_settings: MakeSettings) -> None:
    client, repo = _client(make_settings, internal=True)
    repo.seed(_draft_resume(6))

    response = client.post("/resumes/6/finalize", headers=_INTERNAL_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "finalized"
