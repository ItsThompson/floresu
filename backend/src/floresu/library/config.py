"""Library domain constants.

The audit ``entity_type`` for every bulletpoint write and the default library page
size, kept here so the service, router, and tests read one source. The re-embed
metadata key is shared across embeddable domains and lives in ``core/events``.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every bulletpoint write.
ENTITY_TYPE = "bullet"

# Default cap on a library list read; the Library previews a bounded window.
DEFAULT_LIST_LIMIT = 200
