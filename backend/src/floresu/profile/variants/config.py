"""Identity-variant domain constants.

The audit ``entity_type`` for every variant write and the default list page size,
kept here so the service, router, and tests read one source.
"""

from __future__ import annotations

# The audit-log / write-event ``entity_type`` for every identity-variant write.
ENTITY_TYPE = "identity_variant"

# Default cap on a variant list read; the profile hub previews a bounded window.
DEFAULT_LIST_LIMIT = 200

# The structural-violation ``rule`` carried when archiving a variant a living
# resume still references. The archive is blocked and this signal names the rule
# plus the referencing resume ids, so the resume-side prompt can offer a
# replacement. It is the machine-readable contract that later resume slices key on.
REPLACEMENT_REQUIRED_RULE = "identity_variant_replacement_required"
