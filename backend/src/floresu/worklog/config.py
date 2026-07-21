"""Worklog domain constants.

The audit ``entity_type`` for every worklog write and the default timeline page
size, kept here so the service, router, and tests read one source. The re-embed
metadata key is shared across embeddable domains and lives in ``core/events``.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every worklog write.
ENTITY_TYPE = "worklog"

# Default cap on a timeline list read; the global timeline previews a bounded window.
DEFAULT_LIST_LIMIT = 200
