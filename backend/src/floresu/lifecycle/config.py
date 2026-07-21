"""Lifecycle-domain constants: entity types, the export shape, and paths.

The entity-type strings are imported from each domain's config rather than
re-declared, so the audit ``entity_type`` a permanent delete records matches the
string that domain's own writes use (a domain truth, single-sourced there).
"""

from __future__ import annotations

from floresu.embedding.config import EmbedItemKind
from floresu.library.config import ENTITY_TYPE as BULLET_ENTITY_TYPE
from floresu.profile.config import ENTITY_TYPE as SOURCE_ENTITY_TYPE
from floresu.resumes.config import ENTITY_TYPE as RESUME_ENTITY_TYPE
from floresu.worklog.config import ENTITY_TYPE as WORKLOG_ENTITY_TYPE

# The embeddable kinds a permanent delete must also purge from the ``embeddings``
# table (the polymorphic row has no FK to the item, so it never cascades). Maps
# each embeddable entity type to its embed discriminator; a resume is absent
# because outputs are never indexed and so carry no vector to purge.
EMBEDDABLE_KIND_FOR_ENTITY: dict[str, EmbedItemKind] = {
    WORKLOG_ENTITY_TYPE: EmbedItemKind.WORKLOG,
    SOURCE_ENTITY_TYPE: EmbedItemKind.SOURCE,
    BULLET_ENTITY_TYPE: EmbedItemKind.BULLET,
}

# The version stamped into an export archive so a future importer can detect the
# shape it is reading.
EXPORT_SCHEMA_VERSION = 1

# Download filename stem for the export attachment; the route appends the date.
EXPORT_FILENAME_STEM = "floresu-export"

__all__ = [
    "BULLET_ENTITY_TYPE",
    "EMBEDDABLE_KIND_FOR_ENTITY",
    "EXPORT_FILENAME_STEM",
    "EXPORT_SCHEMA_VERSION",
    "RESUME_ENTITY_TYPE",
    "SOURCE_ENTITY_TYPE",
    "WORKLOG_ENTITY_TYPE",
]
