"""Lean job-application wire schemas (re-declared, not imported).

A job application pairs a company and role title with (at most) one application
resume; its status is the P0 finalize trigger. :class:`JobApplicationSummary` is
the read/list shape (the scalar columns plus the id of the 1:1 linked resume).
:class:`JobApplicationCreateInput` starts an application at ``added`` (company +
role title only); :class:`JobApplicationUpdateInput` is a partial write that can
change the company/role title and/or set the status: setting ``submitted`` is the
finalize trigger the backend acts on (rejected with a recoverable error when no
resume is linked). The status and the resume link are server-owned and never
accepted on a write. The cross-package contract tests (Ticket 22) keep the mirror
honest.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobApplicationStatus(StrEnum):
    """A job application is ``added`` then ``submitted`` (submit finalizes its resume)."""

    ADDED = "added"
    SUBMITTED = "submitted"


class JobApplicationCreateInput(BaseModel):
    """Create an application: a company and role title; the status starts ``added``."""

    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)


class JobApplicationUpdateInput(BaseModel):
    """A partial write: change the company/role title and/or set the status.

    At least one field must be present. Setting ``status`` to ``submitted`` is the
    finalize trigger the backend acts on; the company/role title are plain edits.
    """

    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(default=None, min_length=1)
    role_title: str | None = Field(default=None, min_length=1)
    status: JobApplicationStatus | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> JobApplicationUpdateInput:
        if self.company is None and self.role_title is None and self.status is None:
            raise ValueError("an update must change company, role_title, and/or status")
        return self


class JobApplicationSummary(BaseModel):
    """List/read projection: the scalar columns plus the 1:1 linked resume id."""

    model_config = ConfigDict(extra="ignore")

    id: int
    company: str
    role_title: str
    status: JobApplicationStatus
    linked_resume_id: int | None = None
    created_at: datetime
    updated_at: datetime
