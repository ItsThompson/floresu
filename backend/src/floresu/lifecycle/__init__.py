"""Web-human-only lifecycle: restore, permanent delete, data export, account delete.

The destructive and recovery operations that protect the store from a runaway
agent. Every route in this domain mounts on the external (human, session-cookie)
app only; the internal (agent-facing) app never exposes them, so an agent has no
permanent-delete, export, or account-delete route. This is the enforcement half
of "archive-not-delete everywhere; permanent delete is web-human-only."
"""
