"""Skills: a deliberately curated profile list with a derived usage count.

A skill is a per-user, curated entry (``UNIQUE (user_id, name)``) the human or the
agent adds on purpose: a tag is never auto-promoted to a skill. A skill carries no
stored count; its usage is computed on read by matching its name against the tag
labels used on worklog (and bullets once they exist), so the number always
reflects the current tags.

Skills live under the profile domain (they are a profile-family entity per the MCP
``profile_*`` surface) but in their own subpackage, mirroring the per-domain file
taxonomy (``models`` / ``schemas`` / ``repository`` / ``service`` / ``router`` /
``wiring`` / ``config``) the sources family established, rather than growing the
sources modules with an unrelated entity.
"""
