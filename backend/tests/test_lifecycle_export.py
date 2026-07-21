"""Unit tests for the pure export assembler.

``build_archive`` is pure, so it is tested with detached ORM instances and no
database: pass rows and edge maps in, assert the serializable archive out. Covers
the per-entity serialization (dates as ISO strings, absent values null), the four
source-subtype detail shapes, and the edge grouping.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from floresu.library.models import Bulletpoint
from floresu.lifecycle.export import ExportInput, build_archive
from floresu.profile.models import Certification, Education, Project, Role, Source, SourceKind
from floresu.profile.skills.models import Skill
from floresu.profile.variants.models import IdentityVariant
from floresu.resumes.models import (
    JobApplication,
    JobApplicationStatus,
    Resume,
    ResumeKind,
    ResumeStatus,
)
from floresu.worklog.models import Tag, WorklogEntry
from tests.lifecycle_fakes import build_account

_NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _worklog(id_: int, title: str) -> WorklogEntry:
    entry = WorklogEntry(
        user_id=1, title=title, entry_date=date(2026, 1, 2), description="d", content_hash="h"
    )
    entry.id = id_
    entry.created_at = _NOW
    entry.archived_at = None
    return entry


def _source(id_: int, kind: SourceKind, label: str) -> Source:
    source = Source(user_id=1, kind=kind, display_label=label, sort_order=0)
    source.id = id_
    source.date_start = date(2020, 1, 1)
    source.date_end = None
    source.summary = "s"
    source.archived_at = None
    return source


def _bullet(id_: int, text: str) -> Bulletpoint:
    bullet = Bulletpoint(user_id=1, text=text, content_hash="h")
    bullet.id = id_
    bullet.created_at = _NOW
    bullet.archived_at = None
    return bullet


def _base_input(**overrides: object) -> ExportInput:
    defaults: dict[str, object] = {
        "account": build_account(1, email="owner@example.com"),
        "worklog": [],
        "worklog_tags": {},
        "worklog_sources": {},
        "sources": [],
        "source_details": {},
        "bullets": [],
        "bullet_sources": {},
        "bullet_worklogs": {},
        "skills": [],
        "variants": [],
        "tags": [],
        "resumes": [],
        "job_applications": [],
    }
    defaults.update(overrides)
    return ExportInput(**defaults)  # type: ignore[arg-type]


def test_empty_archive_carries_every_section_and_metadata() -> None:
    archive = build_archive(_base_input(), exported_at=_NOW)
    assert archive["schema_version"] == 1
    assert archive["exported_at"] == "2026-03-01T12:00:00+00:00"
    assert archive["account"] == {
        "email": "owner@example.com",
        "created_at": None,
        "has_completed_onboarding": True,
    }
    for section in (
        "worklog_entries",
        "sources",
        "bulletpoints",
        "skills",
        "identity_variants",
        "tags",
        "resumes",
        "job_applications",
    ):
        assert archive[section] == []


def test_worklog_entry_carries_its_tags_and_source_ids() -> None:
    archive = build_archive(
        _base_input(
            worklog=[_worklog(5, "Shipped search")],
            worklog_tags={5: ["api", "python"]},
            worklog_sources={5: [10]},
        ),
        exported_at=_NOW,
    )
    entry = archive["worklog_entries"][0]
    assert entry["id"] == 5
    assert entry["title"] == "Shipped search"
    assert entry["entry_date"] == "2026-01-02"
    assert entry["tags"] == ["api", "python"]
    assert entry["source_ids"] == [10]


def test_each_source_subtype_serializes_its_detail() -> None:
    role = Role(
        source_id=1, kind=SourceKind.ROLE, company="Acme", job_title="Staff", location="NYC"
    )
    role.title_aliases = ["SDE III"]
    project = Project(source_id=2, kind=SourceKind.PROJECT)
    project.links = ["https://example.com"]
    cert = Certification(
        source_id=3, kind=SourceKind.CERTIFICATION, issuer="AWS", credential_id="X"
    )
    edu = Education(
        source_id=4, kind=SourceKind.EDUCATION, institution="MIT", degree="BS", field="CS"
    )
    archive = build_archive(
        _base_input(
            sources=[
                _source(1, SourceKind.ROLE, "Acme"),
                _source(2, SourceKind.PROJECT, "Proj"),
                _source(3, SourceKind.CERTIFICATION, "Cert"),
                _source(4, SourceKind.EDUCATION, "Edu"),
            ],
            source_details={1: role, 2: project, 3: cert, 4: edu},
        ),
        exported_at=_NOW,
    )
    details = {s["id"]: s["detail"] for s in archive["sources"]}
    assert details[1] == {
        "company": "Acme",
        "job_title": "Staff",
        "title_aliases": ["SDE III"],
        "location": "NYC",
    }
    assert details[2] == {"links": ["https://example.com"]}
    assert details[3] == {"issuer": "AWS", "credential_id": "X"}
    assert details[4] == {"institution": "MIT", "degree": "BS", "field": "CS"}


def test_a_source_without_a_resolved_detail_is_skipped() -> None:
    # A base row whose subtype detail did not resolve is omitted rather than
    # exported half-formed (the composite FK guarantees one in production).
    archive = build_archive(
        _base_input(sources=[_source(1, SourceKind.ROLE, "Orphan")], source_details={}),
        exported_at=_NOW,
    )
    assert archive["sources"] == []


def test_bullet_carries_its_provenance_edges() -> None:
    archive = build_archive(
        _base_input(
            bullets=[_bullet(3, "Led migration")],
            bullet_sources={3: [1]},
            bullet_worklogs={3: [5, 6]},
        ),
        exported_at=_NOW,
    )
    bullet = archive["bulletpoints"][0]
    assert bullet["source_ids"] == [1]
    assert bullet["worklog_ids"] == [5, 6]


def test_skills_variants_tags_and_documents_are_included() -> None:
    skill = Skill(user_id=1, name="Python", sort_order=0)
    skill.id = 1
    skill.archived_at = None
    variant = IdentityVariant(
        user_id=1,
        label="Personal",
        full_name="Ada",
        contact={"email": "ada@example.com"},
        links=[{"label": "site", "url": "https://ada.dev"}],
        is_default=True,
    )
    variant.id = 1
    variant.archived_at = None
    tag = Tag(user_id=1, label="api")
    tag.id = 1
    resume = Resume(
        user_id=1,
        kind=ResumeKind.LIVING,
        status=ResumeStatus.DRAFT,
        title="Backend",
        schema_version=1,
        revision=1,
        document={"sections": []},
    )
    resume.id = 1
    resume.job_application_id = None
    resume.archived_at = None
    resume.created_at = _NOW
    application = JobApplication(
        user_id=1, company="Acme", role_title="Backend", status=JobApplicationStatus.ADDED
    )
    application.id = 1
    application.created_at = _NOW

    archive = build_archive(
        _base_input(
            skills=[skill],
            variants=[variant],
            tags=[tag],
            resumes=[resume],
            job_applications=[application],
        ),
        exported_at=_NOW,
    )
    assert archive["skills"][0]["name"] == "Python"
    assert archive["identity_variants"][0]["contact"] == {"email": "ada@example.com"}
    assert archive["tags"][0] == {"id": 1, "label": "api"}
    assert archive["resumes"][0]["document"] == {"sections": []}
    assert archive["resumes"][0]["kind"] == "living"
    assert archive["job_applications"][0]["company"] == "Acme"
