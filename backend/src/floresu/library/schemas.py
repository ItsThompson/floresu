"""Wire schemas for the library: the write body and the bulletpoint read shape.

A write (:class:`BulletpointWrite`) carries the required ``text`` and the bullet's
full provenance-edge lists: the ``source_ids`` it frames directly and the
``worklog_ids`` it frames. The same shape backs create and full-representation
update: setting ``source_ids`` / ``worklog_ids`` is how an edge is added (an id
included) or removed (an id omitted). IDs, timestamps, the content hash, and the
``revision`` token are server-owned and never accepted on a write.

A read (:class:`BulletpointRecord`) is one shape for both the list and the single
read: the bullet plus its resolved provenance edges, its ``revision`` token, and
``used_in_count`` (how many resumes reference it). The list and get reads supply the
real count from the :class:`~floresu.library.usage.BulletUsageCounter` port; write
responses leave it at 0 (the client refetches the list, which is truthful).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from floresu.library.models import Bulletpoint


class BulletpointWrite(BaseModel):
    """The create/update body: required text plus the full provenance-edge lists."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    # Sources this bullet frames directly; zero, one, or many. The service rejects
    # any id the user does not own, so a bullet can never frame a foreign source.
    source_ids: list[int] = Field(default_factory=list)
    # Worklog entries this bullet frames; zero, one, or many, ownership-checked too.
    worklog_ids: list[int] = Field(default_factory=list)


class BulletpointRecord(BaseModel):
    """A canonical bulletpoint with its resolved provenance edges and usage count."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    source_ids: list[int]
    worklog_ids: list[int]
    used_in_count: int
    revision: int
    archived_at: datetime | None


def to_record(
    bullet: Bulletpoint,
    source_ids: list[int],
    worklog_ids: list[int],
    *,
    used_in_count: int = 0,
) -> BulletpointRecord:
    """Project a bullet plus its resolved edge lists onto the read shape.

    ``used_in_count`` defaults to 0; the list and get reads pass the real count from
    the usage port.
    """
    return BulletpointRecord(
        id=bullet.id,
        text=bullet.text,
        source_ids=source_ids,
        worklog_ids=worklog_ids,
        used_in_count=used_in_count,
        revision=bullet.revision,
        archived_at=bullet.archived_at,
    )
