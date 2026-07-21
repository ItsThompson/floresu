"""Wire schemas for the web-only lifecycle surface.

The destructive routes return a small receipt naming what was removed so the web
client can confirm the action and correlate it with the audit event. Confirmation
itself is a required ``confirm`` query flag on each destructive route (the
contract-level gate), not a body field, so the same shape works for a ``DELETE``.
The export archive is streamed as a downloadable attachment, not a typed body, so
it needs no response model here.
"""

from __future__ import annotations

from pydantic import BaseModel


class DeletionReceipt(BaseModel):
    """The result of a permanent delete: what was removed, and whether a vector went with it."""

    entity_type: str
    entity_id: int
    # True when the item was embeddable and its ``embeddings`` row was purged in the
    # same transaction; False for a non-embeddable entity (a resume) that has none.
    embedding_purged: bool


class AccountDeletionReceipt(BaseModel):
    """The result of an account deletion: the account is gone and agents are revoked."""

    deleted: bool
    revoked_agent_count: int
