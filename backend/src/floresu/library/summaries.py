"""Human-readable audit summary lines for bulletpoint writes.

The activity feed and per-item history render the short ``summary`` an audit row
carries. These builders are the one home for a bulletpoint write's summary line, so
the create path, the edit path, and the copy-on-write / promote path
(:mod:`floresu.library.cow`) all read identically in the feed rather than each
inventing its own phrasing. :func:`preview` is the shared single-line truncation
they share.
"""

from __future__ import annotations

_PREVIEW_LIMIT = 60


def preview(text: str) -> str:
    """A short, single-line preview of bullet text for an audit summary line."""
    single_line = " ".join(text.split())
    if len(single_line) <= _PREVIEW_LIMIT:
        return single_line
    return f"{single_line[: _PREVIEW_LIMIT - 1]}…"


def created_summary(text: str) -> str:
    return f"Added bulletpoint “{preview(text)}”"


def edited_summary(text: str) -> str:
    return f"Edited bulletpoint “{preview(text)}”"


def archived_summary(text: str) -> str:
    return f"Archived bulletpoint “{preview(text)}”"


def restored_summary(text: str) -> str:
    return f"Restored bulletpoint “{preview(text)}”"
