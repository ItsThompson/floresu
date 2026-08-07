"""Audit: the append-only log behind the activity feed and per-item history.

Every content write publishes one :class:`~floresu.core.events.WriteEvent` through
the write-event seam; this domain's transactional consumer appends exactly one
``audit_log`` row for it, in the write's own transaction, so a committed write can
never lack its provenance record. Business rules live in
:class:`~floresu.audit.service.AuditService`; the SSE endpoint that streams the
feed and the item-history view both read these rows.
"""

from __future__ import annotations
