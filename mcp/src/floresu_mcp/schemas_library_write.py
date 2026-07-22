"""Lean library-write wire schemas (re-declared, not imported).

The write tools carry two bodies. :class:`BulletpointInput` is the canonical
bullet create body (its text plus the provenance edges it frames).
:class:`ScopeEditInput` is the copy-on-write scope edit: unlike the web boundary
(which prompts when a bullet is shared), the agent MUST state intent, so ``scope``
is required here. The two ``if_match`` revisions guard the record each scope
mutates: the canonical bullet revision for ``everywhere`` and the resume revision
for ``this_resume``.

:data:`ScopeEditResult` is the applied outcome the tool returns. The agent never
receives the web-only ``prompt`` outcome (an omitted scope is a validation error
before the call), so this mirror carries only the two applied outcomes: an
``everywhere`` edit returns the updated canonical bullet, a ``this_resume`` fork
returns the updated resume. The cross-package contract tests (Ticket 22) keep
every mirror honest.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from floresu_mcp.schemas_library import BulletpointRecord
from floresu_mcp.schemas_resume import ResumeRecord


class ResumeEditScope(StrEnum):
    """The intent a scoped bullet edit carries: fork here, or edit the canonical."""

    THIS_RESUME = "this_resume"  # fork a resume-local copy; canonical bullet untouched
    EVERYWHERE = "everywhere"  # edit the canonical bullet; every reference updates


class BulletpointInput(BaseModel):
    """The bullet create body: required text plus the full provenance-edge lists."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    # Sources this bullet frames directly; the backend rejects any id the user
    # does not own, so a bullet can never frame a foreign source.
    source_ids: list[int] = Field(default_factory=list)
    # Worklog entries this bullet frames; ownership-checked by the backend too.
    worklog_ids: list[int] = Field(default_factory=list)


class ScopeEditInput(BaseModel):
    """Edit a canonical bullet a resume item resolves to, with explicit scope.

    ``scope`` is required (the agent states intent; there is no shared-count
    prompt). ``resume_id`` and ``if_match_resume_revision`` are required for a
    ``this_resume`` fork; ``if_match_bullet_revision`` is required for an
    ``everywhere`` edit. Sending a stale revision is a recoverable conflict, not a
    silent overwrite.
    """

    model_config = ConfigDict(extra="forbid")

    bullet_id: int
    new_text: str = Field(min_length=1)
    scope: ResumeEditScope
    # Required when scope is this_resume (the resume to fork the local copy in).
    resume_id: int | None = None
    # Guards the resume (this_resume) / the canonical bullet (everywhere) respectively.
    if_match_resume_revision: int | None = None
    if_match_bullet_revision: int | None = None


class EditedEverywhereResult(BaseModel):
    """The canonical bullet was edited in place; every reference resolves the new text."""

    model_config = ConfigDict(extra="ignore")

    outcome: Literal["edited_everywhere"] = "edited_everywhere"
    bullet: BulletpointRecord


class ForkedThisResumeResult(BaseModel):
    """A resume-local copy was forked; the canonical bullet is unchanged."""

    model_config = ConfigDict(extra="ignore")

    outcome: Literal["forked_this_resume"] = "forked_this_resume"
    resume: ResumeRecord


# The applied scoped-edit outcome the agent receives (never the web-only prompt).
ScopeEditResult = Annotated[
    EditedEverywhereResult | ForkedThisResumeResult, Field(discriminator="outcome")
]
