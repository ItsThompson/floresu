"""Activity-feed tuning constants.

Right-sized for a single VPS and a handful of users. Kept in one module so the
store, the SSE stream, and the tests read one source.
"""

from __future__ import annotations

# The bounded replay window: the last N events per user are retained in the Redis
# replay buffer. A reconnect within this window replays the gap; a longer gap is
# recovered by a normal page reload (which re-reads recent audit rows). Sized well
# above the audit feed page so the initial load and the buffer overlap.
REPLAY_BUFFER_SIZE = 200

# Idle heartbeat cadence (seconds). With no event for this long, the SSE stream
# emits a comment frame so the tunnel/edge does not idle-buffer or close the
# stream between events.
HEARTBEAT_INTERVAL_SECONDS = 15
