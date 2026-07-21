"""Job application domain constants.

The audit ``entity_type`` for every job-application write and the default
application-list page size. Kept here so the service, router, and finalize (which
also syncs a linked application) read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every job-application write.
ENTITY_TYPE = "job_application"

# Default cap on an application-list read; applications are few per user at P0.
DEFAULT_LIST_LIMIT = 200
