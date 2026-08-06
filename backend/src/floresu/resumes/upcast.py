"""Schema versioning: the read-time upcaster and canonical serialization.

The document shape evolves, so it is versioned for authored (non-recomputable)
content:

- ``schema_version`` lives in both the row column and the document JSON.
- On read, a version-keyed upcaster migrates an older document to CURRENT before
  it is validated against the current schema and served.
- On write, the incoming document is validated against the current schema and
  persisted with ``schema_version = CURRENT``.
- Canonical (stable-key-order) serialization gives a byte-stable form for hashing
  and golden snapshots, locked by ``tests/test_resume_golden.py`` and
  ``tests/test_resume_golden_guard.py``: a released golden and its recorded sha256
  can never change silently.

The upcaster registry maps a source version N to the pure transform that produces
a version N+1 document. It is empty at v1 (there is nothing to upcast yet); the
machinery is exercised by :func:`upcast_document`, which chains whatever steps are
registered. A registered step must exist for every version between a document's
version and CURRENT, or the read fails loudly rather than serving a half-migrated
document.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from floresu.core.errors import Validation
from floresu.resumes.document import ResumeDocument

# The current document shape version. Bump this and register an upcaster step (and,
# later, commit a golden snapshot) when the shape changes.
CURRENT_SCHEMA_VERSION = 1

# A pure transform from a version-N raw document to a version-(N+1) raw document.
Upcaster = Callable[[dict[str, Any]], dict[str, Any]]

# Registered per source version: ``UPCASTERS[n]`` upgrades a v-n document to v-n+1.
# Empty at v1; a shape change adds ``UPCASTERS[n] = step`` alongside the bump.
UPCASTERS: dict[int, Upcaster] = {}


def upcast_document(
    raw: Mapping[str, Any],
    *,
    upcasters: Mapping[int, Upcaster] = UPCASTERS,
    current: int = CURRENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Run the registered upcaster chain until the document reaches ``current``.

    Reads ``schema_version`` from the raw document, then applies the registered
    step for each version until it reaches ``current``. A document already at
    ``current`` passes through unchanged. A version newer than ``current`` (written
    by a newer deploy) is rejected rather than silently downgraded, and a gap in
    the chain (no registered step for an intermediate version) is a hard error, so
    a half-migrated document is never served.
    """
    version = raw.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise Validation(
            "The resume document is missing a valid schema_version.",
            fields={"schema_version": "expected an integer version"},
        )
    if version > current:
        raise Validation(
            "This resume was written by a newer version of the app and cannot be read here.",
            fields={"schema_version": f"document is v{version}, current is v{current}"},
        )
    working = dict(raw)
    while version < current:
        step = upcasters.get(version)
        if step is None:
            raise RuntimeError(f"no registered upcaster for schema version {version}")
        working = step(working)
        version += 1
        working["schema_version"] = version
    return working


def load_document(
    raw: Mapping[str, Any],
    *,
    upcasters: Mapping[int, Upcaster] = UPCASTERS,
    current: int = CURRENT_SCHEMA_VERSION,
) -> ResumeDocument:
    """Upcast a stored raw document to ``current`` and validate it against the schema."""
    return ResumeDocument.model_validate(upcast_document(raw, upcasters=upcasters, current=current))


def canonical_json(document: Mapping[str, Any]) -> str:
    """A byte-stable JSON serialization: stable key ordering for nested maps.

    Object keys are sorted recursively (so a document with the same content always
    serializes identically regardless of key insertion order), while array order is
    preserved (``sections`` and ``item_order`` are meaningful sequences). This is
    the single serializer the golden-snapshot drift guard hashes.
    """
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
