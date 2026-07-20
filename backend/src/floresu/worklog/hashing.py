"""The worklog content hash: the single source of the re-embed gate.

A worklog entry's embeddable text is its title plus its description. The content
hash is computed here and nowhere else, so the service owns one definition of
"the content changed": it recomputes the hash on every edit and signals a
re-embed only when the value differs. The embedding worker compares the same hash
against the stored embedding's hash to decide whether to re-embed.
"""

from __future__ import annotations

import hashlib


def compute_content_hash(title: str, description: str | None) -> str:
    """A deterministic hash over the embeddable text (title + description).

    Stable for the same inputs across processes, so the worker's freshness check
    is a plain string compare. The newline separator keeps ``title="a"`` /
    ``description="b"`` distinct from ``title="a b"`` / ``description=None``.
    """
    payload = f"{title}\n\n{description or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
