"""Object-store constants."""

from __future__ import annotations

# Lifetime of a presigned download / preview-expand URL. Long enough for a
# click-through, short enough that a leaked URL expires quickly; downloads re-mint
# the URL on demand rather than storing a long-lived one.
PRESIGN_TTL_SECONDS = 900
