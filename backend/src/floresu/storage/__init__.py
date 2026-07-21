"""Object storage: the injected store interface, its R2 binding, and the key scheme.

Rendered PDFs that persist live in Cloudflare R2; only the object key is stored in
Postgres (on the resume revision), never the bytes. This module is a thin adapter:
the :class:`ObjectStore` port exposes just ``put`` and ``get_url``, the R2 binding
implements it over an injected S3-compatible client (so tests substitute a fake and
no live credentials are needed off the deployed box), and :func:`revision_pdf_key`
is the single source of the ``u/{userId}/r/{resumeId}/rev/{n}.pdf`` key scheme.
"""

from __future__ import annotations

from floresu.storage.keys import revision_pdf_key
from floresu.storage.store import ObjectStore, R2ObjectStore

__all__ = ["ObjectStore", "R2ObjectStore", "revision_pdf_key"]
