"""Pure assembly of the data-export archive from the account's records.

Turns the raw ORM rows and edge maps the export repository returns into one
JSON-serializable ``dict`` (the downloadable archive). Pure and side-effect free,
so the shape is unit-testable without a database: pass rows in, assert the archive
out. Datetimes and dates are rendered as ISO strings; absent values stay ``null``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.lifecycle.config import EXPORT_SCHEMA_VERSION
from floresu.profile.models import Certification, Education, Project, Role

if TYPE_CHECKING:
    from datetime import date, datetime

    from floresu.accounts.models import User
    from floresu.library.models import Bulletpoint
    from floresu.profile.models import Source, SourceSubtype
    from floresu.profile.skills.models import Skill
    from floresu.profile.variants.models import IdentityVariant
    from floresu.resumes.models import JobApplication, Resume
    from floresu.worklog.models import Tag, WorklogEntry


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _account(user: User) -> dict[str, Any]:
    return {
        "email": user.email,
        "created_at": _iso(user.created_at),
        "has_completed_onboarding": user.has_completed_onboarding,
    }


def _worklog_entry(entry: WorklogEntry, tags: list[str], source_ids: list[int]) -> dict[str, Any]:
    return {
        "id": entry.id,
        "title": entry.title,
        "entry_date": _iso(entry.entry_date),
        "description": entry.description,
        "tags": tags,
        "source_ids": source_ids,
        "archived_at": _iso(entry.archived_at),
        "created_at": _iso(entry.created_at),
    }


def _source_detail(subtype: SourceSubtype) -> dict[str, Any]:
    if isinstance(subtype, Role):
        return {
            "company": subtype.company,
            "job_title": subtype.job_title,
            "title_aliases": list(subtype.title_aliases),
            "location": subtype.location,
        }
    if isinstance(subtype, Project):
        return {"links": list(subtype.links)}
    if isinstance(subtype, Certification):
        return {"issuer": subtype.issuer, "credential_id": subtype.credential_id}
    if isinstance(subtype, Education):
        return {
            "institution": subtype.institution,
            "degree": subtype.degree,
            "field": subtype.field,
        }
    return {}  # pragma: no cover - the four subtypes above are exhaustive


def _source(source: Source, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source.id,
        "kind": source.kind.value,
        "display_label": source.display_label,
        "date_start": _iso(source.date_start),
        "date_end": _iso(source.date_end),
        "summary": source.summary,
        "sort_order": source.sort_order,
        "archived_at": _iso(source.archived_at),
        "detail": detail,
    }


def _bullet(bullet: Bulletpoint, source_ids: list[int], worklog_ids: list[int]) -> dict[str, Any]:
    return {
        "id": bullet.id,
        "text": bullet.text,
        "source_ids": source_ids,
        "worklog_ids": worklog_ids,
        "archived_at": _iso(bullet.archived_at),
        "created_at": _iso(bullet.created_at),
    }


def _skill(skill: Skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "sort_order": skill.sort_order,
        "archived_at": _iso(skill.archived_at),
    }


def _variant(variant: IdentityVariant) -> dict[str, Any]:
    return {
        "id": variant.id,
        "label": variant.label,
        "full_name": variant.full_name,
        "contact": variant.contact,
        "links": variant.links,
        "is_default": variant.is_default,
        "archived_at": _iso(variant.archived_at),
    }


def _resume(resume: Resume) -> dict[str, Any]:
    return {
        "id": resume.id,
        "kind": resume.kind.value,
        "status": resume.status.value,
        "title": resume.title,
        "schema_version": resume.schema_version,
        "revision": resume.revision,
        "document": resume.document,
        "job_application_id": resume.job_application_id,
        "archived_at": _iso(resume.archived_at),
        "created_at": _iso(resume.created_at),
    }


def _job_application(application: JobApplication) -> dict[str, Any]:
    return {
        "id": application.id,
        "company": application.company,
        "role_title": application.role_title,
        "status": application.status.value,
        "created_at": _iso(application.created_at),
    }


class ExportInput:
    """The rows and edge maps the export archive is assembled from."""

    def __init__(
        self,
        *,
        account: User,
        worklog: list[WorklogEntry],
        worklog_tags: dict[int, list[str]],
        worklog_sources: dict[int, list[int]],
        sources: list[Source],
        source_details: dict[int, SourceSubtype],
        bullets: list[Bulletpoint],
        bullet_sources: dict[int, list[int]],
        bullet_worklogs: dict[int, list[int]],
        skills: list[Skill],
        variants: list[IdentityVariant],
        tags: list[Tag],
        resumes: list[Resume],
        job_applications: list[JobApplication],
    ) -> None:
        self.account = account
        self.worklog = worklog
        self.worklog_tags = worklog_tags
        self.worklog_sources = worklog_sources
        self.sources = sources
        self.source_details = source_details
        self.bullets = bullets
        self.bullet_sources = bullet_sources
        self.bullet_worklogs = bullet_worklogs
        self.skills = skills
        self.variants = variants
        self.tags = tags
        self.resumes = resumes
        self.job_applications = job_applications


def build_archive(data: ExportInput, *, exported_at: datetime) -> dict[str, Any]:
    """Assemble the complete, JSON-serializable export archive for one account."""
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": _iso(exported_at),
        "account": _account(data.account),
        "worklog_entries": [
            _worklog_entry(
                entry, data.worklog_tags.get(entry.id, []), data.worklog_sources.get(entry.id, [])
            )
            for entry in data.worklog
        ],
        "sources": [
            _source(source, _source_detail(data.source_details[source.id]))
            for source in data.sources
            if source.id in data.source_details
        ],
        "bulletpoints": [
            _bullet(
                bullet,
                data.bullet_sources.get(bullet.id, []),
                data.bullet_worklogs.get(bullet.id, []),
            )
            for bullet in data.bullets
        ],
        "skills": [_skill(skill) for skill in data.skills],
        "identity_variants": [_variant(variant) for variant in data.variants],
        "tags": [{"id": tag.id, "label": tag.label} for tag in data.tags],
        "resumes": [_resume(resume) for resume in data.resumes],
        "job_applications": [_job_application(app) for app in data.job_applications],
    }
