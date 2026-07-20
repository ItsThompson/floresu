"""Profile-sources domain constants.

The audit ``entity_type`` for every source write and the default section-list
page size, kept here so the service, router, and tests read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every source write.
ENTITY_TYPE = "source"

# Default cap on a section list read; the profile hub previews a bounded window.
DEFAULT_LIST_LIMIT = 200
