"""The library's read-only port onto the resume-reference count.

The Library list badge reports how many resumes reference each canonical bullet
("used in N"). That count is a resumes concept: it is ``COUNT(*)`` over
``resume_bullet_ref``, the resumes domain's write-derived index. To surface it in
the library reads without a ``library -> resumes`` import cycle, the library
declares this narrow port and depends on it; the resumes repository implements it
(it owns ``resume_bullet_ref``) and the composition root binds the two.

Keeping only the Protocol here is what prevents the cycle: this module imports no
resumes model, so nothing in ``library/`` reaches into the resumes ORM. The query
lives in ``resumes/repository.py``, whose ``used_in_counts`` structurally satisfies
this interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class BulletUsageCounter(Protocol):
    """How many live resumes reference each of a set of canonical bullets."""

    async def used_in_counts(self, bullet_ids: Sequence[int]) -> dict[int, int]:
        """Map each id to its live resume-reference count.

        Batched: one grouped count for the whole set, never one query per id. An id
        that no resume references is absent from the result, so the call site
        defaults it to 0. An empty input returns an empty map with no query.
        """
        ...
