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
from dataclasses import dataclass
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
