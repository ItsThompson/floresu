"""Audit domain constants.

Default page sizes for the two audit reads. The activity feed renders the recent
window the web app shows on load (older rows arrive via scroll or SSE); item
history shows a single item's recent writes. Both are defaults the reads accept an
override for, kept here so the service, the future feed/history routers, and tests
read one source.
"""

from __future__ import annotations

DEFAULT_FEED_LIMIT = 50
DEFAULT_ITEM_HISTORY_LIMIT = 50
