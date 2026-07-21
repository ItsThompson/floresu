"""Resume domain constants.

The audit ``entity_type`` for every resume write, the default resume-list page
size, the default template a blank resume selects, and the placeholder title a
blank resume takes when the caller supplies none. Kept here so the service,
router, and tests read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every resume write.
ENTITY_TYPE = "resume"

# Default cap on a resume-list read; resumes are few per user at P0.
DEFAULT_LIST_LIMIT = 200

# The template a blank resume selects until the editor changes it. Real templates
# are defined by the rendering slice; this is a stable default id.
DEFAULT_TEMPLATE_ID = "default"

# The title a blank resume takes when the caller supplies none.
DEFAULT_TITLE = "Untitled resume"
