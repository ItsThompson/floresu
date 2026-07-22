"""The classification map: every MCP wire type, its backend counterpart, and deltas.

This is the single source of truth for the schema-mirror test. Every Pydantic
model the MCP server re-declares in its ``schemas*`` modules appears here, mapped
to the backend request/response type it mirrors, with any intentional lean delta
declared inline. A new MCP wire type that is not classified here fails the
completeness test, and a divergence not covered by a declared delta fails the
mirror test, so the mcp<->backend contract cannot drift silently.

The intentional deltas are the ones the T19/T20/T21 changesets flagged as
deliberate:

- lean read projections relax response fields to optional-with-default so a backend
  field addition never breaks a deserialize (``lean_optional``);
- ``ScopeEditInput.scope`` is required + non-nullable on the agent boundary vs
  optional + nullable for the web boundary: the agent must state copy-on-write
  intent, there is no shared-count prompt (``required_on_mcp``);
- the profile-write union carries a client-side ``kind`` discriminator on the skill
  and identity-variant members that their backend bodies do not (``extra_fields``);
- the MCP ``ScopeEditResult`` omits the web-only ``prompt`` outcome (a union-member
  omission, see :data:`UNION_MIRRORS`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, get_args

from pydantic import BaseModel

from floresu.jobapps import schemas as be_jobapps
from floresu.library import schemas as be_library
from floresu.profile import schemas as be_profile
from floresu.profile.skills import schemas as be_skills
from floresu.profile.variants import schemas as be_variants
from floresu.rendering import schemas as be_rendering
from floresu.resumes import document as be_document
from floresu.resumes import render_schemas as be_render
from floresu.resumes import schemas as be_resumes
from floresu.search import schemas as be_search
from floresu.worklog import schemas as be_worklog
from floresu_mcp import schemas as mcp_worklog
from floresu_mcp import schemas_jobapp as mcp_jobapp
from floresu_mcp import schemas_library as mcp_library
from floresu_mcp import schemas_library_write as mcp_library_write
from floresu_mcp import schemas_profile as mcp_profile
from floresu_mcp import schemas_profile_write as mcp_profile_write
from floresu_mcp import schemas_render as mcp_render
from floresu_mcp import schemas_resume as mcp_resume
from floresu_mcp import schemas_resume_write as mcp_resume_write
from floresu_mcp import schemas_search as mcp_search
from tests.schema_compare import MirrorSpec

# The MCP schema modules the completeness test enumerates every wire type from.
MCP_SCHEMA_MODULES = (
    mcp_worklog,
    mcp_profile,
    mcp_search,
    mcp_library,
    mcp_resume,
    mcp_render,
    mcp_jobapp,
    mcp_profile_write,
    mcp_library_write,
    mcp_resume_write,
)

MIRRORS: dict[type[BaseModel], MirrorSpec] = {
    # --- worklog ---
    mcp_worklog.WorklogEntryInput: MirrorSpec(be_worklog.WorklogWrite),
    mcp_worklog.WorklogEntrySummary: MirrorSpec(
        be_worklog.WorklogSummary,
        lean_optional=frozenset({"description", "tags", "source_ids", "archived_at"}),
    ),
    mcp_worklog.WorklogEntryRecord: MirrorSpec(
        be_worklog.WorklogRecord,
        lean_optional=frozenset({"description", "tags", "source_ids", "archived_at", "bullet_ids"}),
    ),
    mcp_worklog.Tag: MirrorSpec(be_worklog.TagRead),
    # --- profile: sources ---
    mcp_profile.RoleDetail: MirrorSpec(be_profile.RoleDetail),
    mcp_profile.ProjectDetail: MirrorSpec(be_profile.ProjectDetail),
    mcp_profile.CertificationDetail: MirrorSpec(be_profile.CertificationDetail),
    mcp_profile.EducationDetail: MirrorSpec(be_profile.EducationDetail),
    mcp_profile.SourceSummary: MirrorSpec(
        be_profile.SourceSummary,
        lean_optional=frozenset({"date_start", "date_end", "summary", "archived_at"}),
    ),
    mcp_profile.SourceRecord: MirrorSpec(
        be_profile.SourceRecord,
        lean_optional=frozenset({"date_start", "date_end", "summary", "archived_at"}),
    ),
    # --- profile: skills + identity variants ---
    mcp_profile.SkillRead: MirrorSpec(
        be_skills.SkillRead, lean_optional=frozenset({"archived_at"})
    ),
    mcp_profile.VariantContact: MirrorSpec(be_variants.VariantContact),
    mcp_profile.VariantLink: MirrorSpec(be_variants.VariantLink),
    mcp_profile.IdentityVariantRead: MirrorSpec(
        be_variants.IdentityVariantRead, lean_optional=frozenset({"archived_at"})
    ),
    # --- search ---
    mcp_search.DateRange: MirrorSpec(be_search.DateRange),
    mcp_search.SearchFilters: MirrorSpec(be_search.SearchFilters),
    mcp_search.RankedHit: MirrorSpec(be_search.RankedHit),
    mcp_search.SearchSourceNode: MirrorSpec(be_search.SearchSourceNode),
    mcp_search.SearchWorklogNode: MirrorSpec(be_search.SearchWorklogNode),
    mcp_search.SearchBulletNode: MirrorSpec(be_search.SearchBulletNode),
    mcp_search.SearchGraph: MirrorSpec(be_search.SearchGraph),
    mcp_search.SearchNotice: MirrorSpec(be_search.SearchNotice),
    mcp_search.SearchResult: MirrorSpec(be_search.SearchResult),
    # --- library ---
    mcp_library.BulletpointRecord: MirrorSpec(
        be_library.BulletpointRecord, lean_optional=frozenset({"archived_at"})
    ),
    # --- resume document (shared read + write nested shapes) ---
    mcp_resume.IdentitySnapshotContact: MirrorSpec(be_document.IdentitySnapshotContact),
    mcp_resume.IdentitySnapshotLink: MirrorSpec(be_document.IdentitySnapshotLink),
    mcp_resume.IdentitySnapshot: MirrorSpec(be_document.IdentitySnapshot),
    mcp_resume.ResumeHeader: MirrorSpec(be_document.ResumeHeader),
    mcp_resume.LocalItemSourceRefs: MirrorSpec(be_document.LocalItemSourceRefs),
    mcp_resume.LibraryRefItem: MirrorSpec(be_document.LibraryRefItem),
    mcp_resume.LocalItem: MirrorSpec(be_document.LocalItem),
    mcp_resume.ResumeSection: MirrorSpec(be_document.ResumeSection),
    mcp_resume.ResumeDocument: MirrorSpec(be_document.ResumeDocument),
    mcp_resume.ResumeSummary: MirrorSpec(
        be_resumes.ResumeSummary,
        lean_optional=frozenset({"job_application_id", "forked_from_resume_id", "archived_at"}),
    ),
    mcp_resume.ResumeRecord: MirrorSpec(
        be_resumes.ResumeRecord,
        lean_optional=frozenset({"job_application_id", "forked_from_resume_id", "archived_at"}),
    ),
    # --- rendering ---
    mcp_render.TemplateInfo: MirrorSpec(be_rendering.TemplateInfo),
    # --- job applications ---
    mcp_jobapp.JobApplicationCreateInput: MirrorSpec(be_jobapps.JobApplicationCreate),
    mcp_jobapp.JobApplicationUpdateInput: MirrorSpec(be_jobapps.JobApplicationUpdate),
    mcp_jobapp.JobApplicationSummary: MirrorSpec(
        be_jobapps.JobApplicationSummary, lean_optional=frozenset({"linked_resume_id"})
    ),
    # --- profile writes ---
    mcp_profile_write._SourceWriteBase: MirrorSpec(be_profile._SourceWriteBase),
    mcp_profile_write.RoleWriteInput: MirrorSpec(be_profile.RoleWrite),
    mcp_profile_write.ProjectWriteInput: MirrorSpec(be_profile.ProjectWrite),
    mcp_profile_write.CertificationWriteInput: MirrorSpec(be_profile.CertificationWrite),
    mcp_profile_write.EducationWriteInput: MirrorSpec(be_profile.EducationWrite),
    mcp_profile_write.SkillWriteInput: MirrorSpec(
        be_skills.SkillWrite, extra_fields=frozenset({"kind"})
    ),
    mcp_profile_write.VariantContactInput: MirrorSpec(be_variants.VariantContact),
    mcp_profile_write.VariantLinkInput: MirrorSpec(be_variants.VariantLink),
    mcp_profile_write.IdentityVariantWriteInput: MirrorSpec(
        be_variants.IdentityVariantWrite, extra_fields=frozenset({"kind"})
    ),
    # --- library writes ---
    mcp_library_write.BulletpointInput: MirrorSpec(be_library.BulletpointWrite),
    mcp_library_write.ScopeEditInput: MirrorSpec(
        be_resumes.ScopeEditRequest, required_on_mcp=frozenset({"scope"})
    ),
    mcp_library_write.EditedEverywhereResult: MirrorSpec(be_resumes.EditedEverywhereResult),
    mcp_library_write.ForkedThisResumeResult: MirrorSpec(be_resumes.ForkedThisResumeResult),
    # --- resume writes ---
    mcp_resume_write.BlankSource: MirrorSpec(be_resumes.BlankSource),
    mcp_resume_write.FromResumeSource: MirrorSpec(be_resumes.FromResumeSource),
    mcp_resume_write.DuplicateSource: MirrorSpec(be_resumes.DuplicateSource),
    mcp_resume_write.ResumeCreateInput: MirrorSpec(be_resumes.ResumeCreateRequest),
    mcp_resume_write.ResumeUpdateInput: MirrorSpec(be_resumes.ResumeUpdate),
    mcp_resume_write.LibraryRefItemInput: MirrorSpec(be_resumes.LibraryRefItemInput),
    mcp_resume_write.LocalItemInput: MirrorSpec(be_resumes.LocalItemInput),
    mcp_resume_write.AddItemInput: MirrorSpec(be_resumes.AddItemRequest),
    mcp_resume_write.ResumeReorderInput: MirrorSpec(be_resumes.ResumeReorderRequest),
    mcp_resume_write.FinalizeResult: MirrorSpec(be_resumes.FinalizeResult),
    mcp_resume_write.RenderReference: MirrorSpec(be_render.ExportResult),
}


def backend_for(mcp_model: type[BaseModel]) -> type[BaseModel] | None:
    """The declared backend counterpart of an MCP model (for nested-model matching)."""
    spec = MIRRORS.get(mcp_model)
    return spec.backend if spec is not None else None


@dataclass(frozen=True)
class UnionMirror:
    """A discriminated-union output the tool returns directly, plus its member deltas.

    The union alias is not a model, so it is checked on its own: every MCP member
    must map (via :data:`MIRRORS`) to a distinct backend member, and ``backend_only``
    names the backend members the lean MCP union intentionally omits.
    """

    name: str
    mcp: Any
    backend: Any
    backend_only: frozenset[type[BaseModel]] = field(default_factory=frozenset)
    note: str = ""


def union_members(alias: Any) -> tuple[type[BaseModel], ...]:
    """The concrete model members of a (possibly ``Annotated``) discriminated union."""
    inner = alias
    while hasattr(inner, "__metadata__"):
        inner = get_args(inner)[0]
    return tuple(m for m in get_args(inner) if isinstance(m, type) and issubclass(m, BaseModel))


UNION_MIRRORS: tuple[UnionMirror, ...] = (
    UnionMirror(
        name="ScopeEditResult",
        mcp=mcp_library_write.ScopeEditResult,
        backend=be_resumes.ScopeEditResult,
        backend_only=frozenset({be_resumes.ScopePromptResult}),
        note="the agent never receives the web-only 'prompt' outcome (an omitted scope "
        "is a validation error before the call), so the MCP union omits ScopePromptResult",
    ),
)
