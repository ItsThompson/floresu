"""Worker-side wire shapes for the embed hop, mirrored from the backend.

The worker re-declares the two shapes it exchanges with the backend internal
embed routes: the item content it reads (:class:`EmbedItemContent`) and the
write-back payload it posts (:class:`VectorWrite`). The backend owns the
authoritative definitions in ``floresu.embedding.schemas``; a contract test pins
these mirrors against them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
    vector: list[float]
    model: str
