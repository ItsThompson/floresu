"""Identity variants: labeled contact sets a resume header projects.

An identity variant is a per-user labeled bundle of a display ``full_name``, an
optional ``contact`` (email, phone, location: each optional per variant), and a
list of ``links``. A resume projects exactly one variant by referencing its id in
the resume document header.

Exactly one variant is the user's default at all times (once at least one exists):
creating the first variant sets it as default automatically, and marking a
different variant default flips the previous default off in the same transaction.
The default cannot be archived until another is made default. Variants are
unordered, so unlike sources and skills they have no reorder operation; the
default is set via update.

Identity variants live under the profile domain in their own subpackage, mirroring
the per-domain file taxonomy the sources family established.
"""
