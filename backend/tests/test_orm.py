"""Declarative base: the deterministic constraint-naming convention is applied."""

from __future__ import annotations

from floresu.core.orm import NAMING_CONVENTION, Base


def test_naming_convention_covers_every_constraint_kind() -> None:
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["uq"] == "uq_%(table_name)s_%(column_0_name)s"


def test_metadata_carries_the_convention() -> None:
    # Every model subclassing Base gets deterministic constraint names, which is
    # what keeps Alembic autogenerate reversible.
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
