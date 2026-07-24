"""Unit tests for the default wall clock.

``utcnow`` is the single ``Clock`` default injected across the domain seams. It
must hand back the timezone-aware UTC "now" so a pinned clock is a drop-in for it
in tests and expiry math stays in UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from floresu.core.clock import utcnow


def test_utcnow_is_timezone_aware_utc() -> None:
    assert utcnow().tzinfo is UTC


def test_utcnow_reads_the_current_instant() -> None:
    before = datetime.now(UTC)
    sampled = utcnow()
    after = datetime.now(UTC)
    assert before <= sampled <= after
