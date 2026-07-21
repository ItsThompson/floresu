"""Golden-snapshot fixtures, the append-only hash lock, and the drift-guard checks.

Resume documents are authored (non-recomputable) content, so a change to the
document shape must fail the build unless the shape is versioned: ``schema_version``
is bumped, an upcaster step is registered, and a fresh golden is committed. This
module holds the machinery that guard rests on (the resume document schema itself
is owned elsewhere and only reused here):

- :func:`build_golden_document` builds one representative document that populates
  every field of every nested model, so any structural change (an added, removed,
  renamed, or retyped field) changes its canonical serialization.
- The committed goldens live in ``goldens/resume_schema/vN.json`` (one per released
  schema version), each holding the exact byte-stable canonical serialization.
- ``goldens/resume_schema/snapshots.lock`` records one sha256 per version. It is
  append-only: :func:`assert_lock_matches` recomputes every golden's hash, so
  editing a released golden or its recorded hash fails the build.
- The pure ``assert_*`` checks take their inputs injected (goldens, lock, current
  version, loader), mirroring the injectable upcaster registry, so both the real
  gate (``test_resume_golden.py``) and the guard-behavior proof
  (``test_resume_golden_guard.py``) drive them with real and synthetic inputs.

Regenerate the current version's golden with ``python -m tests.resume_goldens``
(or ``just resume-goldens``) after a schema-version bump; it refuses to overwrite a
golden that is already locked with different content, so a released shape stays
frozen.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from floresu.resumes.document import (
    IdentitySnapshot,
    IdentitySnapshotContact,
    IdentitySnapshotLink,
    LibraryRefItem,
    LocalItem,
    LocalItemSourceRefs,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, canonical_json

GOLDENS_DIR = Path(__file__).parent / "goldens" / "resume_schema"
LOCK_PATH = GOLDENS_DIR / "snapshots.lock"

_GOLDEN_NAME = re.compile(r"^v(\d+)\.json$")
_LOCK_LINE = re.compile(r"^v(\d+)\s+([0-9a-f]{64})$")

_LOCK_HEADER = (
    "# Append-only sha256 lock for the resume-document schema goldens.\n"
    '# One line per released schema_version: "v<N> <sha256 of vN.json>".\n'
    "# Never edit or reorder an existing line; a version bump appends a new line.\n"
    "# Guarded by tests/test_resume_golden.py.\n"
)

# The single set of field values the representative document carries. They are the
# "real field values" the backward-compat check asserts survive every upcast, so a
# future upcaster that drops content is caught rather than passing on "parsed ok".
GOLDEN_TEMPLATE_ID = "classic"
GOLDEN_IDENTITY_VARIANT_ID = 7
GOLDEN_FULL_NAME = "Ada Lovelace"
GOLDEN_EMAIL = "ada@example.com"
GOLDEN_PHONE = "+1-202-555-0100"
GOLDEN_LOCATION = "London, UK"
GOLDEN_LINK_LABEL = "Portfolio"
GOLDEN_LINK_URL = "https://ada.example.com"
GOLDEN_BULLET_ID = 101
GOLDEN_LOCAL_TEXT = "Led the datastore migration, cutting p99 latency 42%."
GOLDEN_NET_NEW_TEXT = "Python, Rust, PostgreSQL, Typst."
GOLDEN_SOURCE_IDS = [5]
GOLDEN_WORKLOG_IDS = [9, 12]


class GoldenGuardError(Exception):
    """A resume-schema golden/hash-lock invariant was violated."""


class ShapeDriftError(GoldenGuardError):
    """The current document shape does not match its committed golden."""


class LockViolationError(GoldenGuardError):
    """A released golden or its recorded sha256 changed, or the lock is malformed."""


def build_golden_document(version: int) -> ResumeDocument:
    """A representative document stamped with ``version`` that exercises every field.

    It sets both header projections, fully populates the nested identity snapshot,
    and holds both item kinds (a ``library_ref``, a copy-on-write ``local`` fork
    with provenance, and a net-new ``local`` item that leaves the optional
    provenance fields unset). Every nested model therefore appears with a concrete
    value, so a structural change anywhere alters the canonical serialization.
    """
    return ResumeDocument(
        schema_version=version,
        header=ResumeHeader(
            identity_variant_id=GOLDEN_IDENTITY_VARIANT_ID,
            identity_snapshot=IdentitySnapshot(
                full_name=GOLDEN_FULL_NAME,
                contact=IdentitySnapshotContact(
                    email=GOLDEN_EMAIL,
                    phone=GOLDEN_PHONE,
                    location=GOLDEN_LOCATION,
                ),
                links=[IdentitySnapshotLink(label=GOLDEN_LINK_LABEL, url=GOLDEN_LINK_URL)],
            ),
        ),
        template_id=GOLDEN_TEMPLATE_ID,
        sections=[
            ResumeSection(
                id="sec-work",
                kind=SectionKind.WORK,
                title="Experience",
                item_order=["item-ref", "item-fork"],
                items={
                    "item-ref": LibraryRefItem(id="item-ref", bullet_id=GOLDEN_BULLET_ID),
                    "item-fork": LocalItem(
                        id="item-fork",
                        text=GOLDEN_LOCAL_TEXT,
                        source_refs=LocalItemSourceRefs(
                            source_ids=list(GOLDEN_SOURCE_IDS),
                            worklog_ids=list(GOLDEN_WORKLOG_IDS),
                        ),
                        forked_from_bullet_id=GOLDEN_BULLET_ID,
                    ),
                },
            ),
            ResumeSection(
                id="sec-skills",
                kind=SectionKind.SKILLS,
                title="Skills",
                item_order=["item-net-new"],
                items={"item-net-new": LocalItem(id="item-net-new", text=GOLDEN_NET_NEW_TEXT)},
            ),
        ],
    )


def canonical_golden(document: ResumeDocument) -> str:
    """The byte-stable canonical serialization a golden file stores and is hashed on."""
    return canonical_json(document.model_dump(mode="json"))


def sha256_hex(text: str) -> str:
    """The sha256 recorded in the lock for a golden's exact bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_goldens(directory: Path = GOLDENS_DIR) -> dict[int, str]:
    """Map each committed ``vN.json`` to its exact on-disk text, keyed by version."""
    goldens: dict[int, str] = {}
    for path in sorted(directory.glob("v*.json")):
        match = _GOLDEN_NAME.match(path.name)
        if match is not None:
            goldens[int(match.group(1))] = path.read_text(encoding="utf-8")
    return goldens


def load_lock(path: Path = LOCK_PATH) -> dict[int, str]:
    """Parse ``snapshots.lock`` into ``{version: sha256}``, enforcing append-only order.

    Comment (``#``) and blank lines are ignored. A malformed line, a duplicate
    version, or a version that is not strictly ascending is a :class:`LockViolation`,
    so the file can only ever grow by appending a new version.
    """
    lock: dict[int, str] = {}
    previous = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LOCK_LINE.match(stripped)
        if match is None:
            raise LockViolationError(f"malformed snapshots.lock line: {line!r}")
        version = int(match.group(1))
        if version in lock:
            raise LockViolationError(f"duplicate lock entry for v{version}")
        if version <= previous:
            raise LockViolationError("snapshots.lock must be append-only and ascending by version")
        previous = version
        lock[version] = match.group(2)
    return lock


def assert_current_shape_locked(
    *, current: int, canonical_current: str, goldens: Mapping[int, str]
) -> None:
    """Fail unless the current-version canonical shape byte-matches its committed golden."""
    if current not in goldens:
        raise ShapeDriftError(
            f"no committed golden for the current schema version v{current}; "
            f"regenerate and commit v{current}.json"
        )
    if canonical_current != goldens[current]:
        raise ShapeDriftError(
            f"the resume document shape changed but schema_version is still v{current}; "
            "bump CURRENT_SCHEMA_VERSION, register an upcaster, and commit a new golden"
        )


def assert_lock_matches(*, goldens: Mapping[int, str], lock: Mapping[int, str]) -> None:
    """Fail if any golden lacks a lock entry, any lock entry lacks a golden, or a hash drifts."""
    unlocked = sorted(set(goldens) - set(lock))
    if unlocked:
        raise LockViolationError(f"goldens without a lock entry: {unlocked}")
    orphaned = sorted(set(lock) - set(goldens))
    if orphaned:
        raise LockViolationError(f"lock entries without a golden file: {orphaned}")
    for version in sorted(goldens):
        if lock[version] != sha256_hex(goldens[version]):
            raise LockViolationError(
                f"v{version}: the golden bytes or the recorded sha256 changed "
                "(released goldens are immutable)"
            )


def assert_historical_goldens_upcast[T](
    goldens: Mapping[int, str],
    *,
    load: Callable[[Mapping[str, Any]], T],
    invariants: Callable[[T], None],
) -> None:
    """Upcast every committed golden to the current shape and assert real values survive.

    ``load`` upcasts a raw golden to the current version and validates it against
    the current schema; ``invariants`` asserts the known field values are still
    present, so a lossy upcaster fails rather than passing on "parsed ok".
    """
    if not goldens:
        raise GoldenGuardError("expected at least the current version's golden to be committed")
    for version in sorted(goldens):
        invariants(load(json.loads(goldens[version])))


def _write_lock(lock: Mapping[int, str], path: Path = LOCK_PATH) -> None:
    lines = [f"v{version} {lock[version]}" for version in sorted(lock)]
    path.write_text(_LOCK_HEADER + "\n".join(lines) + "\n", encoding="utf-8")


def regenerate() -> None:
    """Write the current version's golden and append its hash, refusing to rewrite a lock.

    Only the current version's golden is (re)generated; historical goldens are
    frozen. If ``vCURRENT.json`` already exists with different content, the shape
    changed for an already-released version: this refuses to overwrite it and tells
    the caller to bump the version instead.
    """
    GOLDENS_DIR.mkdir(parents=True, exist_ok=True)
    current = CURRENT_SCHEMA_VERSION
    text = canonical_golden(build_golden_document(current))
    goldens = load_goldens()
    if current in goldens and goldens[current] != text:
        raise ShapeDriftError(
            f"v{current} is already committed with different content; the shape changed for a "
            "released version. Bump CURRENT_SCHEMA_VERSION, register an upcaster, and rerun."
        )
    lock = load_lock() if LOCK_PATH.exists() else {}
    digest = sha256_hex(text)
    if current in lock and lock[current] != digest:
        raise LockViolationError(f"v{current} is already locked with a different sha256")
    (GOLDENS_DIR / f"v{current}.json").write_text(text, encoding="utf-8")
    _write_lock({**lock, current: digest})


if __name__ == "__main__":
    regenerate()
