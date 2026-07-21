"""Skills domain constants.

The audit ``entity_type`` for every skill write and the default list page size,
kept here so the service, router, and tests read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every skill write.
ENTITY_TYPE = "skill"

# Default cap on a skill list read; the profile hub previews a bounded window.
DEFAULT_LIST_LIMIT = 200
