"""Wire and domain types for the embedding pipeline.

These shapes cross the internal-API hop the worker uses to read a corpus item and
write its vector back, and back the fast-path that runs the same read/gate/store
inline. The worker package re-declares the wire shapes it needs (it shares no code
with the backend); nothing pins the two mirrors equal field-for-field, because
``contract/tests/`` covers the MCP-to-backend mirror only.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from floresu.embedding.config import EMBEDDING_DIMENSION


class EmbedOutcome(StrEnum):
    """The result of an embed/store attempt, for metrics and the worker's status.

    ``APPLIED`` wrote (or overwrote) the vector. The four ``SKIPPED_*`` outcomes
    are the gate's no-ops: ``SUPERSEDED`` (the item's hash moved past the job's),
    ``IDEMPOTENT`` (the stored vector already carries this hash), ``ARCHIVED`` (the
    item is archived, so any vector is removed and none is written), and
    ``MISSING`` (the item no longer exists, so any vector is removed).
    """

    APPLIED = "applied"
    SKIPPED_SUPERSEDED = "superseded"
    SKIPPED_IDEMPOTENT = "idempotent"
    SKIPPED_ARCHIVED = "archived"
    SKIPPED_MISSING = "missing"


class CorpusItem(BaseModel):
    """A corpus item's embeddable text, its current content hash, and archive state.

    The resolver composes ``text`` from the item's searchable columns (worklog
    title+description, bullet text, source label+summary+role fields). ``content_hash``
    is the item's current hash: the gate compares it against the job's enqueued
    hash to detect a superseded job. ``archived`` gates the item out entirely.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    content_hash: str
    archived: bool


class VectorWrite(BaseModel):
    """The worker's write-back payload: the vector plus the hash it was embedded at."""

    model_config = ConfigDict(frozen=True)

    content_hash: str
    vector: list[float] = Field(min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION)
    model: str


class StoreResult(BaseModel):
    """The outcome of a write-back or delete, echoed to the worker for its metrics."""

    model_config = ConfigDict(frozen=True)

    status: EmbedOutcome
