"""In-memory test doubles and factories for the identity-variants domain.

The service is tested sociably: the real :class:`IdentityVariantService` runs over
this in-memory repository (substituted at the only true external boundary,
Postgres), a fake :class:`ResumeVariantRepointer` standing in for the resume side,
the real :class:`WriteEventPublisher` seam wired with a capturing consumer, and the
shared :class:`FakeSession` recording the ``transaction`` boundary. The repo mirrors
the server-minted id and enforces ``UNIQUE (user_id, label)`` by raising a
unique-violation ``IntegrityError``. The re-pointer's referencing seam is seeded
directly, standing in for the resumes the archive flow re-points.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from floresu.profile.variants.models import IdentityVariant
from floresu.profile.variants.schemas import IdentityVariantWrite

if TYPE_CHECKING:
    from collections.abc import Sequence

    from floresu.core.actor import Actor

__all__ = [
    "FakeResumeVariantRepointer",
    "InMemoryIdentityVariantRepository",
    "build_variant_write",
]


class _UniqueOrigError(Exception):
    """A stand-in DBAPI error carrying the Postgres unique-violation SQLSTATE."""

    def __init__(self) -> None:
        self.sqlstate = "23505"
        super().__init__(self.sqlstate)


class InMemoryIdentityVariantRepository:
    """A dict-backed :class:`IdentityVariantRepository` with scoping and unique labels."""

    def __init__(self) -> None:
        self._variants: dict[int, IdentityVariant] = {}
        self._next_id = 1

    async def add(self, variant: IdentityVariant) -> None:
        if any(
            other.user_id == variant.user_id and other.label == variant.label
            for other in self._variants.values()
        ):
            # Mirror the ``UNIQUE (user_id, label)`` breach the real table raises.
            raise IntegrityError("INSERT INTO identity_variants", {}, orig=_UniqueOrigError())
        variant.id = self._next_id
        self._next_id += 1
        self._variants[variant.id] = variant

    async def get(self, user_id: int, variant_id: int) -> IdentityVariant | None:
        variant = self._variants.get(variant_id)
        if variant is None or variant.user_id != user_id:
            return None
        return variant

    async def list(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[IdentityVariant]:
        rows = [v for v in self._variants.values() if v.user_id == user_id]
        if not include_archived:
            rows = [v for v in rows if v.archived_at is None]
        rows.sort(key=lambda v: (v.label, v.id))
        return rows[:limit]

    async def current_default(self, user_id: int) -> IdentityVariant | None:
        for variant in self._variants.values():
            if variant.user_id == user_id and variant.is_default and variant.archived_at is None:
                return variant
        return None


class FakeResumeVariantRepointer:
    """A dict-backed :class:`ResumeVariantRepointer` seeded with referencing resume ids.

    Stands in for the resume service the composition root binds. Records each
    re-point call so the archive orchestration can be asserted, and can be told to
    fail to exercise the all-or-nothing rollback.
    """

    def __init__(self) -> None:
        self._references: dict[tuple[int, int], list[int]] = {}
        self.repoint_calls: list[tuple[str, int, int]] = []
        self.fail = False

    def set_references(self, user_id: int, variant_id: int, resume_ids: list[int]) -> None:
        """Seed the living-resume ids that reference a variant (the re-point set)."""
        self._references[(user_id, variant_id)] = resume_ids

    async def resumes_referencing_variant(self, user_id: str, variant_id: int) -> Sequence[int]:
        return self._references.get((int(user_id), variant_id), [])

    async def repoint_variant(
        self, user_id: str, actor: Actor, from_variant_id: int, to_variant_id: int
    ) -> Sequence[int]:
        if self.fail:
            raise RuntimeError("repoint failed")
        self.repoint_calls.append((user_id, from_variant_id, to_variant_id))
        return self._references.get((int(user_id), from_variant_id), [])


def build_variant_write(**overrides: Any) -> IdentityVariantWrite:
    base: dict[str, Any] = {
        "label": "Personal",
        "full_name": "Ada Lovelace",
        "contact": {"email": "ada@example.com", "location": "London"},
        "links": [{"label": "Site", "url": "https://ada.example.com"}],
        "is_default": False,
    }
    base.update(overrides)
    return IdentityVariantWrite(**base)
