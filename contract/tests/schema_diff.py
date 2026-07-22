"""The pure schema-diff engine behind the schema-mirror contract test.

The MCP server and the backend re-declare their shared wire types independently
(separate images, no shared import). This module reduces a Pydantic model to a
normalized field map and compares an MCP model against its backend counterpart
field-for-field: field names (by wire alias), types, nullability, and
required/optional. It has no I/O and no knowledge of which types mirror which;
:mod:`tests.mirror_registry` supplies that mapping and the allowed deltas.

Type normalization collapses the two packages' independently-declared types onto a
comparable shape:

- primitives compare by name; enums and ``Literal``\\ s compare by their value set,
  so the backend ``SourceKind`` and the MCP ``SourceKind`` (distinct classes, equal
  members) match, as do ``Literal[SourceKind.ROLE]`` and ``Literal[ProfileKind.ROLE]``;
- containers (``list``/``dict``/optional/union) compare structurally by element;
- a nested model is a leaf matched through the registry: an MCP model field matches
  a backend model field only when the registry declares them a mirrored pair, so
  every nested model must itself be classified.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

_NONE_TYPE = type(None)
_SCALARS: frozenset[type] = frozenset({int, str, float, bool, bytes, date, datetime})

# Maps an MCP model to its declared backend counterpart (or None if unclassified).
Resolver = Callable[[type[BaseModel]], type[BaseModel] | None]


class UnsupportedAnnotationError(Exception):
    """A field annotation the normalizer does not model (a new type shape shipped)."""


# --- normalized type nodes ---


@dataclass(frozen=True)
class ScalarNode:
    name: str


@dataclass(frozen=True)
class EnumNode:
    values: tuple[str, ...]


@dataclass(frozen=True)
class LiteralNode:
    values: tuple[str, ...]


@dataclass(frozen=True)
class ModelNode:
    model: type[BaseModel]


@dataclass(frozen=True)
class ListNode:
    item: Node


@dataclass(frozen=True)
class DictNode:
    key: Node
    value: Node


@dataclass(frozen=True)
class UnionNode:
    members: tuple[Node, ...]


@dataclass(frozen=True)
class OptionalNode:
    inner: Node


Node = (
    ScalarNode | EnumNode | LiteralNode | ModelNode | ListNode | DictNode | UnionNode | OptionalNode
)


def _unwrap_annotated(ann: Any) -> Any:
    """Strip ``Annotated[...]`` layers (discriminated unions carry a ``FieldInfo``)."""
    while hasattr(ann, "__metadata__"):
        ann = get_args(ann)[0]
    return ann


def _literal_value(arg: Any) -> str:
    """A ``Literal`` argument's wire value (an enum member's value, else the raw value)."""
    if isinstance(arg, enum.Enum):
        return str(arg.value)
    return str(arg)


def parse(ann: Any) -> Node:
    """Normalize a field annotation into a comparable :data:`Node`."""
    ann = _unwrap_annotated(ann)
    origin = get_origin(ann)

    if origin is Union:
        args = get_args(ann)
        non_none = [a for a in args if a is not _NONE_TYPE]
        optional = len(non_none) != len(args)
        parsed = [parse(a) for a in non_none]
        node: Node = parsed[0] if len(parsed) == 1 else UnionNode(tuple(parsed))
        return OptionalNode(node) if optional else node
    if origin is list:
        (item,) = get_args(ann)
        return ListNode(parse(item))
    if origin is dict:
        key, value = get_args(ann)
        return DictNode(parse(key), parse(value))
    if origin is Literal:
        return LiteralNode(tuple(sorted(_literal_value(a) for a in get_args(ann))))
    if isinstance(ann, type):
        if issubclass(ann, enum.Enum):
            return EnumNode(tuple(sorted(str(m.value) for m in ann)))
        if issubclass(ann, BaseModel):
            return ModelNode(ann)
        if ann in _SCALARS:
            return ScalarNode(ann.__name__)
    raise UnsupportedAnnotationError(repr(ann))


def strip_optional(node: Node) -> Node:
    """The non-nullable core of a node (unwraps one :class:`OptionalNode`)."""
    return node.inner if isinstance(node, OptionalNode) else node


def describe(node: Node) -> str:
    """A short, human-readable rendering of a node for failure messages."""
    match node:
        case ScalarNode(name):
            return name
        case EnumNode(values):
            return f"enum{{{','.join(values)}}}"
        case LiteralNode(values):
            return f"literal{{{','.join(values)}}}"
        case ModelNode(model):
            return f"model:{model.__name__}"
        case ListNode(item):
            return f"list[{describe(item)}]"
        case DictNode(key, value):
            return f"dict[{describe(key)},{describe(value)}]"
        case UnionNode(members):
            return f"union[{'|'.join(describe(m) for m in members)}]"
        case OptionalNode(inner):
            return f"optional[{describe(inner)}]"


def nodes_match(a: Node, b: Node, resolve: Resolver) -> bool:
    """Whether an MCP node ``a`` and a backend node ``b`` are the same wire shape."""
    match (a, b):
        case (OptionalNode(ai), OptionalNode(bi)):
            return nodes_match(ai, bi, resolve)
        case (ScalarNode(an), ScalarNode(bn)):
            return an == bn
        case (EnumNode(av), EnumNode(bv)):
            return av == bv
        case (LiteralNode(av), LiteralNode(bv)):
            return av == bv
        case (ListNode(ai), ListNode(bi)):
            return nodes_match(ai, bi, resolve)
        case (DictNode(ak, av), DictNode(bk, bv)):
            return nodes_match(ak, bk, resolve) and nodes_match(av, bv, resolve)
        case (ModelNode(am), ModelNode(bm)):
            return resolve(am) is bm
        case (UnionNode(am), UnionNode(bm)):
            return _unions_match(am, bm, resolve)
        case _:
            return False


def _unions_match(
    a_members: tuple[Node, ...], b_members: tuple[Node, ...], resolve: Resolver
) -> bool:
    """Every MCP union member matches one distinct backend member (a bijection)."""
    if len(a_members) != len(b_members):
        return False
    remaining = list(b_members)
    for am in a_members:
        for i, bm in enumerate(remaining):
            if nodes_match(am, bm, resolve):
                del remaining[i]
                break
        else:
            return False
    return not remaining


# --- field extraction + model comparison ---


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
