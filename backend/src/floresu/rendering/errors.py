"""Rendering error contract.

A render failure is a model-recoverable outcome, not an operational fault: the
document could not be compiled to a PDF (a malformed document or a Typst error). It
maps to a 422 so the preview surfaces an error state (never a stale image as
current) and an export is blocked with a recoverable message, both via the shared
problem+json handler.
"""

from __future__ import annotations

from floresu.core.errors import Validation


class RenderError(Validation):
    """A resume that could not be compiled to a PDF (bad document or Typst error)."""
