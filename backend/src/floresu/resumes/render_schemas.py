"""Wire schemas for the resume render surface: the preview request and export result.

Preview optionally overrides the template (the selector previews a template without
saving it to the document); export takes the resume as saved and returns where the
persisted PDF lives plus a time-limited URL to download it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PreviewRequest(BaseModel):
    """A preview render, optionally with a template override (not persisted)."""

    model_config = ConfigDict(extra="forbid")

    template_id: str | None = None


class ExportResult(BaseModel):
    """Where a persisted resume PDF lives, plus a time-limited URL to download it."""

    model_config = ConfigDict(extra="forbid")

    resume_id: int
    revision: int
    object_key: str
    download_url: str
