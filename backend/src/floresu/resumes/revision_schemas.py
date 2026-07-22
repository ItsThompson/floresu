"""Wire schemas for the resume revision-history surface: published versions + URL.

A published version is a revision whose PDF was rendered and stored in R2 by an
export or a finalize. The list carries only the revision number and its timestamp;
the R2 object key is never on the wire. A per-version request returns a
time-limited presigned URL the browser fetches the stored PDF from directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PublishedVersion(BaseModel):
    """One revision that has a rendered PDF stored in R2 (an export or a finalize)."""

    model_config = ConfigDict(from_attributes=True)

    revision_no: int
    created_at: datetime


class PublishedVersionList(BaseModel):
    """A resume's published versions, newest first (may be empty)."""

    resume_id: int
    versions: list[PublishedVersion]


class VersionPdfUrl(BaseModel):
    """A time-limited presigned URL for one published version's stored PDF."""

    resume_id: int
    revision_no: int
    download_url: str
