"""The default opaque-id factory injected as the ``IdFactory`` seam.

Services mint surrogate/opaque ids through an injected factory so a deterministic
id sequence makes minted ids assertable without patching. This module is the
single home for that default and its type alias; the domain injection seams
import them rather than redefining a ``uuid4().hex`` copy under per-domain names.

Two id producers stay out of this seam by design: ``oauth.new_urlsafe_id``
(a ``secrets.token_urlsafe`` protocol identifier) and the correlation-scoped
request-id minter. Both are distinct operations tied to their own module.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

IdFactory = Callable[[], str]


def new_hex_id() -> str:
    """The default opaque id: a uuid4 hex string. Injected as an ``IdFactory`` default."""
    return uuid4().hex
