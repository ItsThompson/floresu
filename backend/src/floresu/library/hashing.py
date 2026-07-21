"""The bulletpoint content hash: the single source of the re-embed gate.

A canonical bulletpoint's embeddable text is its ``text``. The content hash is
computed here and nowhere else, so the service owns one definition of "the content
changed": it recomputes the hash on every edit and signals a re-embed only when
the value differs. The embedding worker compares the same hash against the stored
embedding's hash to decide whether to re-embed.
"""

from __future__ import annotations

import hashlib


def compute_content_hash(text: str) -> str:
    """A deterministic hash over the embeddable bullet text.

    Stable for the same input across processes, so the worker's freshness check is
    a plain string compare.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
