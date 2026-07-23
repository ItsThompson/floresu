"""End-to-end contract tests for the copy-on-write and promote surface on both apps.

Drives the real router, service, and write-event seam through ``TestClient`` with
the in-memory resume and library repositories substituted for Postgres. Asserts the
scope-resolution HTTP contract: the web boundary prompts only for a shared bullet
and otherwise edits everywhere or forks a copy; the agent (internal) boundary
requires an explicit scope; and promote swaps a local item to a canonical
reference. No database is required.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from fastapi import Request
from fastapi.testclient import TestClient

from floresu.core.actor import ActorType, resolve_internal_actor, resolve_web_actor
from floresu.core.app_factory import create_app
from floresu.core.errors import build_exception_handlers
from floresu.core.events import WriteEvent
from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER
from floresu.core.identity import SESSION_COOKIE_NAME, require_internal_user, require_user
from floresu.library.hashing import compute_content_hash
from floresu.library.models import Bulletpoint
from floresu.resumes.cow import EditChannel
from floresu.resumes.router import create_resumes_router
from floresu.resumes.service import ResumeService
from tests.library_fakes import InMemoryLibraryRepository
from tests.resumes_fakes import (
    InMemoryResumeRepository,
    LibraryRepoTextResolver,
    build_bullet_writer,
)
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.settings import AppSettings

MakeSettings = Callable[..., "AppSettings"]

_INTERNAL_TOKEN = "internal-secret"
_INTERNAL_HEADERS = {
    INTERNAL_API_TOKEN_HEADER: _INTERNAL_TOKEN,
    USER_ID_HEADER: "1",
    ACTOR_HEADER: "claude",
}
_CREATE_BLANK = {"kind": "living", "source": {"mode": "blank"}}


class _Bench:
    def __init__(
        self,
        client: TestClient,
        library_repo: InMemoryLibraryRepository,
        captured: list[WriteEvent],
        *,
        internal: bool,
    ) -> None:
        self.client = client
        self.library_repo = library_repo
        self.captured = captured
        self._headers = _INTERNAL_HEADERS if internal else {}

    def seed_bullet(self, text: str, *, user_id: int = 1) -> int:
        bullet = Bulletpoint(user_id=user_id, text=text, content_hash=compute_content_hash(text))
        asyncio.run(self.library_repo.add(bullet))
        return bullet.id

    def create_resume(self) -> int:
        created = self.client.post("/resumes", json=_CREATE_BLANK, headers=self._headers)
        assert created.status_code == 201, created.text
        return cast("int", created.json()["id"])

    def put_section(self, resume_id: int, section: dict[str, object], *, if_match: int) -> None:
        body = {
            "title": "Backend Engineer",
            "template_id": "default",
            "header": {},
            "sections": [section],
        }
        response = self.client.put(
            f"/resumes/{resume_id}",
            json=body,
            headers={**self._headers, "If-Match": str(if_match)},
        )
        assert response.status_code == 200, response.text

    def resume_referencing(self, bullet_id: int, *, item_id: str = "a") -> int:
        resume_id = self.create_resume()
        self.put_section(
            resume_id,
            {
                "id": "sec-work",
                "kind": "work",
                "title": "Experience",
                "item_order": [item_id],
                "items": {item_id: {"id": item_id, "kind": "library_ref", "bullet_id": bullet_id}},
            },
            if_match=1,
        )
        return resume_id

    def resume_with_local_item(self, *, text: str, item_id: str = "a") -> int:
        resume_id = self.create_resume()
        self.put_section(
            resume_id,
            {
                "id": "sec-work",
                "kind": "work",
                "title": "Experience",
                "item_order": [item_id],
                "items": {item_id: {"id": item_id, "kind": "local", "text": text}},
            },
            if_match=1,
        )
        return resume_id


def _bench(make_settings: MakeSettings, *, internal: bool = False) -> _Bench:
    resume_repo = InMemoryResumeRepository()
    library_repo = InMemoryLibraryRepository()
    publisher = CapturingWriteEventPublisher()
    captured = publisher.captured

    def provider(request: Request) -> ResumeService:
        session = cast("AsyncSession", FakeSession())
        return ResumeService(
            session,
            resume_repo,
            LibraryRepoTextResolver(library_repo),
            request.app.state.events,
            build_bullet_writer(session, request.app.state.events, library_repo=library_repo),
        )

    if internal:
        router = create_resumes_router(
            provider,
            identity=require_internal_user,
            actor=resolve_internal_actor,
            channel=EditChannel.MCP,
        )
        settings = make_settings(service="floresu-internal", internal_api_token=_INTERNAL_TOKEN)
    else:
        router = create_resumes_router(
            provider, identity=require_user, actor=resolve_web_actor, channel=EditChannel.WEB
        )
        settings = make_settings(service="floresu-external", environment="development")

    app = create_app(settings, routers=[router], exception_handlers=build_exception_handlers())
    app.state.events = publisher

    async def verify(_cookie: str) -> str:
        return "1"

    app.state.session_verifier = verify
    client = TestClient(app)
    if not internal:
        client.cookies.set(SESSION_COOKIE_NAME, "session-token")
    return _Bench(client, library_repo, captured, internal=internal)


def test_web_unshared_bullet_edits_everywhere(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings)
    bullet_id = bench.seed_bullet("Cut latency 40%.")
    bench.resume_referencing(bullet_id)

    response = bench.client.post(
        "/resumes/bullet-edit",
        json={
            "bullet_id": bullet_id,
            "new_text": "Cut latency 70%.",
            "if_match_bullet_revision": 1,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "edited_everywhere"
    assert body["bullet"]["text"] == "Cut latency 70%."
    assert body["bullet"]["revision"] == 2


def test_web_shared_bullet_returns_a_prompt(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings)
    bullet_id = bench.seed_bullet("Shared framing.")
    bench.resume_referencing(bullet_id, item_id="a")
    bench.resume_referencing(bullet_id, item_id="b")

    response = bench.client.post(
        "/resumes/bullet-edit", json={"bullet_id": bullet_id, "new_text": "Reframed."}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "prompt"
    assert body["used_in_count"] == 2


def test_web_this_resume_forks_a_local_copy(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings)
    bullet_id = bench.seed_bullet("Shared framing.")
    resume_id = bench.resume_referencing(bullet_id)

    response = bench.client.post(
        "/resumes/bullet-edit",
        json={
            "bullet_id": bullet_id,
            "new_text": "Only here.",
            "scope": "this_resume",
            "resume_id": resume_id,
            "if_match_resume_revision": 2,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "forked_this_resume"
    item = body["resume"]["document"]["sections"][0]["items"]["a"]
    assert item["kind"] == "local"
    assert item["text"] == "Only here."
    assert item["forked_from_bullet_id"] == bullet_id


def test_promote_swaps_the_item_to_a_reference(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings)
    resume_id = bench.resume_with_local_item(text="Inline framing.")

    response = bench.client.post(f"/resumes/{resume_id}/items/a/promote", headers={"If-Match": "2"})
    assert response.status_code == 200, response.text
    item = response.json()["document"]["sections"][0]["items"]["a"]
    assert item["kind"] == "library_ref"
    assert isinstance(item["bullet_id"], int)


def test_promote_requires_if_match(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings)
    resume_id = bench.resume_with_local_item(text="Inline framing.")

    response = bench.client.post(f"/resumes/{resume_id}/items/a/promote")
    assert response.status_code == 422


def test_mcp_edit_without_scope_is_a_422(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings, internal=True)
    bullet_id = bench.seed_bullet("Framing.")
    bench.resume_referencing(bullet_id)

    response = bench.client.post(
        "/resumes/bullet-edit",
        json={"bullet_id": bullet_id, "new_text": "Agent edit."},
        headers=_INTERNAL_HEADERS,
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_mcp_explicit_everywhere_attributes_the_named_agent(make_settings: MakeSettings) -> None:
    bench = _bench(make_settings, internal=True)
    bullet_id = bench.seed_bullet("Framing.")
    bench.resume_referencing(bullet_id)

    response = bench.client.post(
        "/resumes/bullet-edit",
        json={
            "bullet_id": bullet_id,
            "new_text": "Agent framing.",
            "scope": "everywhere",
            "if_match_bullet_revision": 1,
        },
        headers=_INTERNAL_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "edited_everywhere"
    edit_event = [e for e in bench.captured if e.entity_type == "bullet"][-1]
    assert edit_event.actor.type is ActorType.AGENT
    assert edit_event.actor.label == "claude"
