"""Lean render-template read schema (re-declared, not imported).

``list_templates`` returns the global template registry entries the agent picks
from when creating or rendering a resume. The read shape ignores unrecognized
fields so a backend addition never breaks it. The cross-package contract tests
(Ticket 22) keep the mirror honest.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TemplateInfo(BaseModel):
    """A template registry entry the selector lists."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
