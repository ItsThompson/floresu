"""Wire schemas for job applications: the create/update writes and the read shape.

A job application is a lightweight relational entity pairing a company and role
title with (at most) one application resume; its status is the P0 finalize trigger.
:class:`JobApplicationCreate` starts an application at ``added`` (company + role
title only). :class:`JobApplicationUpdate` is a partial write that can change the
company/role title and/or set the status (setting ``submitted`` finalizes the
linked resume; that consistency lives in the service). :class:`JobApplicationSummary`
is the read/list shape: the scalar columns plus the id of the 1:1 linked resume
(the list shows company, role, linked resume, and the added date) and never accepts
a status or link on a write (both are server-owned).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from floresu.resumes.models import JobApplication, JobApplicationStatus


class JobApplicationCreate(BaseModel):
    """Create an application: a company and role title; the status starts ``added``."""

    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1)
    role_title: str = Field(min_length=1)


class JobApplicationUpdate(BaseModel):
    """A partial write: change the company/role title and/or set the status.

    At least one field must be present. Setting ``status`` to ``submitted`` is the
    finalize trigger the service acts on; the company/role title are plain edits.
    """

    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(default=None, min_length=1)
    role_title: str | None = Field(default=None, min_length=1)
    status: JobApplicationStatus | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> JobApplicationUpdate:
        if self.company is None and self.role_title is None and self.status is None:
            raise ValueError("an update must change company, role_title, and/or status")
        return self


class JobApplicationSummary(BaseModel):
    """List/read projection: the scalar columns plus the 1:1 linked resume id."""

    model_config = ConfigDict(extra="forbid")

    id: int
    company: str
    role_title: str
    status: JobApplicationStatus
    linked_resume_id: int | None
    created_at: datetime
    updated_at: datetime


def to_summary(application: JobApplication, linked_resume_id: int | None) -> JobApplicationSummary:
    """Project a ``job_applications`` row plus its resolved link onto the read shape."""
    return JobApplicationSummary(
        id=application.id,
        company=application.company,
        role_title=application.role_title,
        status=application.status,
        linked_resume_id=linked_resume_id,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )
