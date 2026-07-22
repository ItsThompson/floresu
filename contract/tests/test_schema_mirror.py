"""The schema-mirror contract test: MCP wire types vs backend request/response types.

Three guards keep the boundary honest:

- every MCP wire type is classified (an unclassified type fails, so no type ships
  without a mirror decision);
- each classified type matches its backend counterpart field-for-field, modulo the
  deltas declared in :mod:`tests.mirror_registry` (an undeclared divergence fails,
  and a declared delta that no longer occurs fails too, so the allowlist cannot rot);
- the directly-returned discriminated unions match their backend members, modulo the
  documented web-only omissions.

A self-test proves the engine actually detects drift, so a green run is meaningful.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, ConfigDict

from tests.mirror_registry import (
    MCP_SCHEMA_MODULES,
    MIRRORS,
    UNION_MIRRORS,
    UnionMirror,
    backend_for,
    union_members,
)
from tests.schema_compare import MirrorSpec, compare


def _declared_mcp_wire_types() -> set[type[BaseModel]]:
    """Every Pydantic model defined in the MCP ``schemas*`` modules."""
    found: set[type[BaseModel]] = set()
    for module in MCP_SCHEMA_MODULES:
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == module.__name__
            ):
                found.add(obj)
    return found


def test_every_mcp_wire_type_is_classified() -> None:
    """No MCP wire type ships without a mirror classification (mirrored or lean)."""
    declared = _declared_mcp_wire_types()
    classified = set(MIRRORS)
    unclassified = declared - classified
    stale = classified - declared
    assert not unclassified, "MCP wire types with no schema-mirror classification: " + ", ".join(
        sorted(t.__name__ for t in unclassified)
    )
    assert not stale, "classified types no longer declared as MCP wire types: " + ", ".join(
        sorted(t.__name__ for t in stale)
    )


def _mirror_key(mcp_model: type[BaseModel]) -> str:
    return f"{mcp_model.__module__.rsplit('.', 1)[-1]}.{mcp_model.__name__}"


_MIRROR_ITEMS: list[tuple[type[BaseModel], MirrorSpec]] = sorted(
    MIRRORS.items(), key=lambda kv: _mirror_key(kv[0])
)
_MIRROR_IDS: list[str] = [_mirror_key(mcp_model) for mcp_model, _ in _MIRROR_ITEMS]


@pytest.mark.parametrize(("mcp_model", "spec"), _MIRROR_ITEMS, ids=_MIRROR_IDS)
def test_mcp_type_mirrors_backend_field_for_field(
    mcp_model: type[BaseModel], spec: MirrorSpec
) -> None:
    """An MCP type matches its backend counterpart, honoring only declared deltas."""
    report = compare(mcp_model, spec, backend_for)
    detail = "\n".join(
        [f"  drift: {v}" for v in report.violations]
        + [f"  stale: {s}" for s in report.stale_exceptions]
    )
    assert report.ok, f"{mcp_model.__name__} <-> {spec.backend.__name__} drift:\n{detail}"


@pytest.mark.parametrize("union", UNION_MIRRORS, ids=lambda u: u.name)
def test_returned_union_mirrors_backend_members(union: UnionMirror) -> None:
    """A directly-returned discriminated union matches its backend members.

    Every MCP member maps to a distinct backend member; the only backend members
    without an MCP counterpart are the documented web-only omissions.
    """
    mcp_members = union_members(union.mcp)
    be_members = union_members(union.backend)

    mapped = {backend_for(m) for m in mcp_members}
    assert None not in mapped, f"{union.name}: an MCP member is unclassified"
    assert len(mapped) == len(mcp_members), f"{union.name}: MCP members collide onto one backend"

    expected_backend = set(be_members) - union.backend_only
    assert mapped == expected_backend, (
        f"{union.name}: member drift "
        f"(mcp maps to {sorted(t.__name__ for t in mapped if t is not None)}; "
        f"backend minus documented omissions is {sorted(t.__name__ for t in expected_backend)})"
    )
    assert union.backend_only <= set(be_members), f"{union.name}: backend_only lists a non-member"


def test_engine_detects_injected_drift() -> None:
    """The diff engine reports real drift, so a passing mirror test is meaningful."""

    class McpShape(BaseModel):
        model_config = ConfigDict(extra="forbid")

        id: int
        label: str
        count: int

    class BackendShape(BaseModel):
        model_config = ConfigDict(extra="forbid")

        id: int
        label: str | None  # nullability + type drift vs MCP `label: str`
        total: int  # renamed field: `count` on MCP, `total` on backend

    report = compare(McpShape, MirrorSpec(BackendShape), backend_for)
    assert not report.ok
    joined = " ".join(report.violations)
    assert "label" in joined  # type drift caught
    assert "count" in joined and "total" in joined  # rename caught on both sides


def test_engine_flags_requiredness_only_drift() -> None:
    """A field differing only in required/optional (same, non-nullable type) is caught."""

    class Mcp(BaseModel):
        model_config = ConfigDict(extra="forbid")

        x: int  # required

    class Backend(BaseModel):
        model_config = ConfigDict(extra="forbid")

        x: int = 0  # optional, identical non-nullable type

    report = compare(Mcp, MirrorSpec(Backend), backend_for)
    assert not report.ok
    joined = " ".join(report.violations)
    assert "requiredness differs" in joined
    assert "type mismatch" not in joined  # only requiredness drifted


def test_engine_flags_nullability_only_drift() -> None:
    """A field differing only in nullability (same requiredness) is caught."""

    class Mcp(BaseModel):
        model_config = ConfigDict(extra="forbid")

        y: str  # required, non-nullable

    class Backend(BaseModel):
        model_config = ConfigDict(extra="forbid")

        y: str | None  # required, nullable

    report = compare(Mcp, MirrorSpec(Backend), backend_for)
    assert not report.ok
    joined = " ".join(report.violations)
    assert "type mismatch" in joined  # nullability is carried in the type node
    assert "requiredness differs" not in joined  # both required
