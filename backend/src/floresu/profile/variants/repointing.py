"""The variants domain's port onto the resume side of an archive-with-replacement.

Archiving a variant a living resume references must re-point those resumes to a
replacement before the archive, in one transaction. Finding and re-pointing the
referencing resumes is a resumes concept: it reads and rewrites the resume document
header and runs the resume save contract (revision snapshot + audit). To drive it
from the variants archive without a ``variants -> resumes`` import cycle, the
variants domain declares this narrow port and depends on it; the resume service
implements it (it owns the resume document, revision, and snapshot rules) and the
composition root binds the two, exactly as ``library.usage.BulletUsageCounter`` is
bound in ``library/wiring.py``.

Keeping only the Protocol here is what prevents the cycle: this module imports no
resumes model, so nothing in ``profile/variants/`` reaches into the resumes ORM. The
implementation lives in ``resumes/service.py``, whose ``resumes_referencing_variant``
and ``repoint_variant`` structurally satisfy this interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from floresu.core.actor import Actor


class ResumeVariantRepointer(Protocol):
    """Find and re-point the living resumes that reference a user's identity variant."""

    async def resumes_referencing_variant(
        self, user_id: str, variant_id: int
    ) -> Sequence[int]:
        """The ids of the user's living resumes whose header references ``variant_id``.

        Empty when nothing references it, so the archive proceeds directly. A
        non-empty result drives the replacement prompt (and its count) when no
        replacement was chosen.
        """
        ...

    async def repoint_variant(
        self, user_id: str, actor: Actor, from_variant_id: int, to_variant_id: int
    ) -> Sequence[int]:
        """Re-point every referencing living resume's header from one variant to another.

        Runs inside the caller's transaction so the re-points commit atomically with
        the variant archive. Each re-pointed resume records an audit ``UPDATE`` under
        the resume save contract (a save creates a revision snapshot). Returns the
        ids of the resumes changed.
        """
        ...
