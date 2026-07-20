"""Worklog domain constants.

The audit ``entity_type`` for every worklog write, the default timeline page size,
and the metadata key that carries the re-embed trigger, kept here so the service,
router, and tests read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every worklog write.
ENTITY_TYPE = "worklog"

# Default cap on a timeline list read; the global timeline previews a bounded window.
DEFAULT_LIST_LIMIT = 200

# The write-event ``metadata`` key that carries the re-embed trigger. A write that
# warrants (re)embedding (a create, or an edit that changes the content hash)
# carries the new hash under this key; the embed consumer (a post-commit side
# channel a later slice registers) keys on its presence and compares the hash to
# gate embedding. An edit that leaves the hash unchanged omits it, so no re-embed
# is signalled.
REEMBED_CONTENT_HASH_KEY = "content_hash"
