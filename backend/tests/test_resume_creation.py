"""Unit tests for resume creation: the contract check, seeding, and the link guard.

``validate_creation_contract`` is pure and tested directly. ``seed_document`` and
``require_free_job_application`` take an injected repository, so they are driven
sociably over the shared in-memory :class:`InMemoryResumeRepository` fake (the true
external boundary, Postgres, is the only substitution) and asserted on their
returned document/title/provenance and the errors they raise.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog

from floresu.core.errors import Conflict, Validation
from floresu.rendering.config import DEFAULT_TEMPLATE_ID
from floresu.rendering.registry import list_templates, resolve_template
from floresu.resumes.config import DEFAULT_TITLE
from floresu.resumes.creation import (
    JOB_APPLICATION_TAKEN_MESSAGE,
    require_free_job_application,
    seed_document,
    validate_creation_contract,
)
from floresu.resumes.document import LibraryRefItem, LocalItem
from floresu.resumes.models import Resume, ResumeKind, ResumeStatus
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION
from tests.resumes_fakes import InMemoryResumeRepository, build_create_request


def _source_document() -> dict[str, Any]:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "template_id": "source-template",
        "header": {"identity_variant_id": 5},
        "sections": [
            {
                "id": "sec-1",
                "kind": "work",
                "title": "Experience",
                "item_order": ["a", "b"],
                "items": {
                    "a": {"id": "a", "kind": "library_ref", "bullet_id": 10},
                    "b": {"id": "b", "kind": "local", "text": "Did a thing."},
                },
            }
        ],
    }


def _source_resume(*, user_id: int = 1, title: str = "Source resume") -> Resume:
    return Resume(
        user_id=user_id,
        kind=ResumeKind.LIVING,
        status=ResumeStatus.DRAFT,
        title=title,
        schema_version=CURRENT_SCHEMA_VERSION,
        revision=1,
        document=_source_document(),
    )


def _application_resume(*, job_application_id: int, user_id: int = 1) -> Resume:
    return Resume(
        user_id=user_id,
        kind=ResumeKind.APPLICATION,
        status=ResumeStatus.DRAFT,
        title="Application",
        schema_version=CURRENT_SCHEMA_VERSION,
        revision=1,
        document={},
        job_application_id=job_application_id,
    )


# --- validate_creation_contract (pure) ---------------------------------------


def test_validate_creation_contract_requires_a_job_application_for_an_application() -> None:
    with pytest.raises(Validation):
        validate_creation_contract(build_create_request(kind="application"))


def test_validate_creation_contract_forbids_a_job_application_on_a_living_resume() -> None:
    with pytest.raises(Validation):
        validate_creation_contract(build_create_request(job_application_id=7))


def test_validate_creation_contract_accepts_a_valid_application() -> None:
    validate_creation_contract(build_create_request(kind="application", job_application_id=7))


def test_validate_creation_contract_accepts_a_valid_living_resume() -> None:
    validate_creation_contract(build_create_request())


# --- seed_document -----------------------------------------------------------


async def test_seed_document_for_a_blank_source_yields_an_empty_document() -> None:
    repo = InMemoryResumeRepository()
    document, title, source_id = await seed_document(repo, 1, build_create_request())
    assert document.sections == []
    assert document.schema_version == CURRENT_SCHEMA_VERSION
    assert document.template_id == DEFAULT_TEMPLATE_ID
    assert title == DEFAULT_TITLE
    assert source_id is None


async def test_seed_document_for_a_blank_source_uses_a_registered_template_id() -> None:
    # The blank default must match what GET /resumes/templates lists, so the editor
    # selector value is a valid option with no re-select. list_templates() is the same
    # registry call the endpoint returns. No-fallback behavior is covered by the test
    # below.
    repo = InMemoryResumeRepository()
    document, _title, _source_id = await seed_document(repo, 1, build_create_request())
    assert document.template_id in [info.id for info in list_templates()]


async def test_a_fresh_blank_resume_resolves_without_a_template_fallback_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = InMemoryResumeRepository()
    document, _title, _source_id = await seed_document(repo, 1, build_create_request())
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.rendering.registry._log", cap)
    resolve_template(document.template_id)
    fallbacks = [call for call in cap.calls if call.args == ("template_fallback",)]
    assert fallbacks == []


async def test_seed_document_for_a_blank_source_honors_title_and_template_overrides() -> None:
    repo = InMemoryResumeRepository()
    request = build_create_request(title="My CV", template_id="modern")
    document, title, source_id = await seed_document(repo, 1, request)
    assert document.template_id == "modern"
    assert title == "My CV"
    assert source_id is None


async def test_seed_document_from_a_resume_copies_content_and_records_provenance() -> None:
    repo = InMemoryResumeRepository()
    source = repo.seed(_source_resume(title="Source resume"))
    request = build_create_request(source={"mode": "from_resume", "from_resume_id": source.id})
    document, title, source_id = await seed_document(repo, 1, request)
    section = document.sections[0]
    # References stay references; inline text stays inline (a faithful copy).
    ref_item = section.items["a"]
    local_item = section.items["b"]
    assert isinstance(ref_item, LibraryRefItem)
    assert ref_item.bullet_id == 10
    assert isinstance(local_item, LocalItem)
    assert local_item.text == "Did a thing."
    # Template and header are copied from the source; title defaults to the source's.
    assert document.template_id == "source-template"
    assert document.header.identity_variant_id == 5
    assert title == "Source resume"
    assert source_id == source.id


async def test_seed_document_duplicate_copies_content_and_records_provenance() -> None:
    repo = InMemoryResumeRepository()
    source = repo.seed(_source_resume())
    request = build_create_request(source={"mode": "duplicate", "duplicate_id": source.id})
    document, _title, source_id = await seed_document(repo, 1, request)
    assert document.sections[0].item_order == ["a", "b"]
    assert source_id == source.id


async def test_seed_document_honors_a_title_override_over_the_source_title() -> None:
    repo = InMemoryResumeRepository()
    source = repo.seed(_source_resume(title="Source resume"))
    request = build_create_request(
        title="Renamed", source={"mode": "from_resume", "from_resume_id": source.id}
    )
    _document, title, _source_id = await seed_document(repo, 1, request)
    assert title == "Renamed"


async def test_seed_document_honors_a_template_override_over_the_source_template() -> None:
    repo = InMemoryResumeRepository()
    source = repo.seed(_source_resume())
    request = build_create_request(
        template_id="modern", source={"mode": "from_resume", "from_resume_id": source.id}
    )
    document, _title, _source_id = await seed_document(repo, 1, request)
    assert document.template_id == "modern"


async def test_seed_document_from_a_missing_source_is_rejected() -> None:
    repo = InMemoryResumeRepository()
    request = build_create_request(source={"mode": "from_resume", "from_resume_id": 999})
    with pytest.raises(Validation):
        await seed_document(repo, 1, request)


async def test_seed_document_cannot_seed_from_another_users_resume() -> None:
    repo = InMemoryResumeRepository()
    source = repo.seed(_source_resume(user_id=2))
    request = build_create_request(source={"mode": "from_resume", "from_resume_id": source.id})
    # pk=1 does not own the source, so it is scoped out and reads as not found.
    with pytest.raises(Validation):
        await seed_document(repo, 1, request)


# --- require_free_job_application --------------------------------------------


async def test_require_free_job_application_passes_for_an_owned_unlinked_application() -> None:
    repo = InMemoryResumeRepository()
    repo.own_job_application(1, 7)
    await require_free_job_application(repo, 1, 7)


async def test_require_free_job_application_rejects_an_unowned_application() -> None:
    repo = InMemoryResumeRepository()
    with pytest.raises(Validation):
        await require_free_job_application(repo, 1, 7)


async def test_require_free_job_application_rejects_an_already_linked_application() -> None:
    repo = InMemoryResumeRepository()
    repo.own_job_application(1, 7)
    repo.seed(_application_resume(job_application_id=7))
    with pytest.raises(Conflict) as caught:
        await require_free_job_application(repo, 1, 7)
    assert str(caught.value) == JOB_APPLICATION_TAKEN_MESSAGE
