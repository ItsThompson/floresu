"""End-to-end contract tests for the job-application routes on both app shapes.

Drives the real jobapps router and service through ``TestClient`` with an in-memory
repository and a recording finalizer (the finalize routine has its own tests). Asserts
create-at-added, the list/get read shapes, the PATCH field edit, the PATCH submit
trigger (which finalizes the linked resume), and the recoverable rejection when there
is no linked resume, on both the external cookie boundary and the internal trusted
boundary. No database is required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.core.settings import AppSettings
from floresu.jobapps.router import create_jobapps_router
from floresu.jobapps.service import JobApplicationService
from floresu.resumes.models import JobApplicationStatus
from tests.jobapps_fakes import (
    FIXED_NOW,
    InMemoryJobApplicationRepository,
    RecordingFinalizer,
    build_application,
)
from tests.resumes_fakes import FakeSession, capturing_publisher

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "claude",
}


def _client(
    make_settings: MakeSettings, *, internal: bool
) -> tuple[TestClient, InMemoryJobApplicationRepository, RecordingFinalizer]:
    repo = InMemoryJobApplicationRepository()
    finalizer = RecordingFinalizer(repo)
    publisher, _captured = capturing_publisher()

    def provider(_request: Request) -> JobApplicationService:
        return JobApplicationService(
            FakeSession(),  # type: ignore[arg-type]
            repo,
            publisher,
            finalizer,
            clock=lambda: FIXED_NOW,
        )

    identity: Callable[..., Any]
    actor: Callable[..., Any]
    if internal:
        identity, actor = require_internal_user, resolve_internal_actor
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        identity, actor = require_user, resolve_web_actor
        settings = make_settings(service="floresu-external", environment="development")

    router = create_jobapps_router(provider, identity=identity, actor=actor)
    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return client, repo, finalizer


def _headers(*, internal: bool) -> dict[str, str]:
    return _INTERNAL_HEADERS if internal else {}


def test_create_returns_201_at_added(make_settings: MakeSettings) -> None:
    client, _repo, _finalizer = _client(make_settings, internal=False)

    response = client.post(
        "/job-applications", json={"company": "Initech", "role_title": "Backend Engineer"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "added"
    assert body["company"] == "Initech"
    assert body["linked_resume_id"] is None


def test_list_and_get_expose_the_linked_resume(make_settings: MakeSettings) -> None:
    client, repo, _finalizer = _client(make_settings, internal=False)
    application = repo.seed(build_application(company="Globex"))
    repo.link_resume(application.id, resume_id=31)

    listed = client.get("/job-applications")
    assert listed.status_code == 200
    assert listed.json()[0]["linked_resume_id"] == 31

    fetched = client.get(f"/job-applications/{application.id}")
    assert fetched.status_code == 200
    assert fetched.json()["linked_resume_id"] == 31


def test_get_unknown_is_a_problem_json_404(make_settings: MakeSettings) -> None:
    client, _repo, _finalizer = _client(make_settings, internal=False)

    response = client.get("/job-applications/999")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "NOT_FOUND"


def test_patch_edits_company_without_finalizing(make_settings: MakeSettings) -> None:
    client, repo, finalizer = _client(make_settings, internal=False)
    application = repo.seed(build_application(company="Old"))

    response = client.patch(f"/job-applications/{application.id}", json={"company": "New"})

    assert response.status_code == 200
    assert response.json()["company"] == "New"
    assert finalizer.calls == []


def test_patch_submit_finalizes_the_linked_resume(make_settings: MakeSettings) -> None:
    client, repo, finalizer = _client(make_settings, internal=True)
    application = repo.seed(build_application())
    repo.link_resume(application.id, resume_id=77)

    response = client.patch(
        f"/job-applications/{application.id}",
        json={"status": "submitted"},
        headers=_headers(internal=True),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert finalizer.calls == [("1", 77)]
    assert application.status is JobApplicationStatus.SUBMITTED


def test_patch_submit_without_linked_resume_is_a_409(make_settings: MakeSettings) -> None:
    client, repo, finalizer = _client(make_settings, internal=False)
    application = repo.seed(build_application())

    response = client.patch(f"/job-applications/{application.id}", json={"status": "submitted"})

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert finalizer.calls == []
    assert application.status is JobApplicationStatus.ADDED


def test_internal_boundary_rejects_a_missing_token(make_settings: MakeSettings) -> None:
    client, _repo, _finalizer = _client(make_settings, internal=True)

    response = client.get("/job-applications")  # no internal headers

    assert response.status_code == 401
