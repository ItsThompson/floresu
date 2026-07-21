"""The object-key scheme for persisted resume PDFs.

The single source of the key layout so the render/export path and any future reader
agree byte-for-byte. Keys are namespaced by user, resume, and revision, so a resume
never collides with another and re-exporting a revision overwrites its own object
rather than accumulating orphans.
"""

from __future__ import annotations


def revision_pdf_key(user_id: int, resume_id: int, revision_no: int) -> str:
    """The R2 object key for a resume revision's rendered PDF.

    ``u/{userId}/r/{resumeId}/rev/{n}.pdf`` per the rendering section: namespaced by
    user and resume and revision, so it is unique per revision and stable across
    re-exports of the same revision.
    """
    return f"u/{user_id}/r/{resume_id}/rev/{revision_no}.pdf"
