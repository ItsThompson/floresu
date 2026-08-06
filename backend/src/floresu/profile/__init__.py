"""Profile domain: the ground-truth sources layer (class table inheritance).

Sources are the roles, projects, certifications, and education entries a worklog
entry or bullet attaches to. They are modeled as a supertable: one ``sources``
base row carries the common columns and a ``kind`` discriminator, and one
kind-locked subtype table per kind carries the kind-specific columns. It also
establishes the per-domain file taxonomy (``models`` / ``schemas`` /
``repository`` / ``service`` / ``router`` / ``wiring`` / ``config``)
every other domain mirrors.
"""
