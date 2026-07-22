"""Model comparison and the mirror-spec allowlist for the schema-mirror test.

:func:`compare` diffs an MCP model against its backend counterpart field-for-field
using the normalized nodes from :mod:`tests.schema_diff`, honoring the intentional
deltas a :class:`MirrorSpec` declares. Each declared delta must actually occur, so a
stale exception (one the code no longer diverges by) fails just like an undeclared
divergence: the allowlist cannot silently widen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from tests.schema_diff import Node, Resolver, describe, nodes_match, parse, strip_optional


@dataclass(frozen=True)
class FieldSpec:
    wire_name: str
    node: Node
    required: bool


def field_specs(model: type[BaseModel]) -> dict[str, FieldSpec]:
    """The model's fields keyed by wire name (alias where set), normalized."""
    specs: dict[str, FieldSpec] = {}
    for name, info in model.model_fields.items():
        wire = info.alias or name
        specs[wire] = FieldSpec(wire, parse(info.annotation), info.is_required())
    return specs


@dataclass(frozen=True)
class MirrorSpec:
    """How one MCP model mirrors a backend model, plus its documented deltas.

    ``lean_optional`` names response fields the MCP relaxes to optional-with-default
    (same type) while the backend requires them: a lean read tolerates a backend
    field addition without breaking a deserialize. ``required_on_mcp`` names input
    fields the MCP makes required and non-nullable while the backend leaves them
    optional and nullable (the agent must state intent). ``extra_fields`` names
    MCP-only fields (e.g. a client-side union discriminator dropped before the
    call); ``missing_fields`` names backend fields the lean MCP shape omits. Each
    listed delta must actually occur, or the entry is flagged as stale.
    """

    backend: type[BaseModel]
    note: str = ""
    lean_optional: frozenset[str] = field(default_factory=frozenset)
    required_on_mcp: frozenset[str] = field(default_factory=frozenset)
    extra_fields: frozenset[str] = field(default_factory=frozenset)
    missing_fields: frozenset[str] = field(default_factory=frozenset)


@dataclass
class MirrorReport:
    mcp: type[BaseModel]
    backend: type[BaseModel]
    violations: list[str] = field(default_factory=list)
    stale_exceptions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and not self.stale_exceptions


def compare(mcp_model: type[BaseModel], spec: MirrorSpec, resolve: Resolver) -> MirrorReport:
    """Diff an MCP model against its backend counterpart, honoring documented deltas."""
    report = MirrorReport(mcp=mcp_model, backend=spec.backend)
    mcp_fields = field_specs(mcp_model)
    be_fields = field_specs(spec.backend)
    mcp_names, be_names = set(mcp_fields), set(be_fields)

    used_extra: set[str] = set()
    used_missing: set[str] = set()
    used_lean: set[str] = set()
    used_required: set[str] = set()

    for name in sorted(mcp_names - be_names):
        if name in spec.extra_fields:
            used_extra.add(name)
        else:
            report.violations.append(f"{name!r}: on MCP but not on backend {spec.backend.__name__}")

    for name in sorted(be_names - mcp_names):
        if name in spec.missing_fields:
            used_missing.add(name)
        else:
            report.violations.append(f"{name!r}: on backend {spec.backend.__name__} but not on MCP")

    for name in sorted(mcp_names & be_names):
        mf, bf = mcp_fields[name], be_fields[name]

        if name in spec.required_on_mcp:
            if (
                mf.required
                and not bf.required
                and nodes_match(mf.node, strip_optional(bf.node), resolve)
            ):
                used_required.add(name)
            else:
                report.violations.append(
                    f"{name!r}: declared required-on-MCP exception not satisfied "
                    f"(mcp {describe(mf.node)} required={mf.required}; "
                    f"backend {describe(bf.node)} required={bf.required})"
                )
            continue

        types_ok = nodes_match(mf.node, bf.node, resolve)
        if not types_ok:
            report.violations.append(
                f"{name!r}: type mismatch (mcp {describe(mf.node)} vs backend {describe(bf.node)})"
            )
        if mf.required != bf.required:
            if name in spec.lean_optional and not mf.required and bf.required and types_ok:
                used_lean.add(name)
            else:
                report.violations.append(
                    f"{name!r}: requiredness differs (mcp required={mf.required}, "
                    f"backend required={bf.required})"
                )

    for name in sorted(spec.extra_fields - used_extra):
        report.stale_exceptions.append(f"extra_fields lists {name!r} but it is not MCP-only")
    for name in sorted(spec.missing_fields - used_missing):
        report.stale_exceptions.append(f"missing_fields lists {name!r} but it is not backend-only")
    for name in sorted(spec.lean_optional - used_lean):
        report.stale_exceptions.append(f"lean_optional lists {name!r} but its requiredness matches")
    for name in sorted(spec.required_on_mcp - used_required):
        report.stale_exceptions.append(f"required_on_mcp lists {name!r} but the delta is absent")

    return report
