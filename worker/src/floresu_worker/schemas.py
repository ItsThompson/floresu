"""Worker-side wire shapes for the embed hop, mirrored from the backend.

The worker re-declares the two shapes it exchanges with the backend internal
embed routes: the item content it reads (:class:`EmbedItemContent`) and the
write-back payload it posts (:class:`VectorWrite`). The backend owns the
authoritative definitions in ``floresu.embedding.schemas``; the cross-package
contract test that pins these mirrors against them field-for-field is a Ticket 22
follow-up, not a guard that exists yet.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from floresu_worker.config import EMBEDDING_DIMENSION


class EmbedItemContent(BaseModel):
    """An item's embeddable text, its current content hash, and archive state."""

    model_config = ConfigDict(frozen=True)

    text: str
    content_hash: str
    archived: bool


class VectorWrite(BaseModel):
    """The write-back payload: the vector plus the hash it was embedded at."""

    model_config = ConfigDict(frozen=True)

    content_hash: str
    # Pinned width mirrors the backend ``VectorWrite`` so a misconfigured worker
    # fails in-process rather than one hop later at the backend's 422.
    vector: list[float] = Field(min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION)
    model: str
