"""Embedding-domain constants: the pinned P0 provider, the corpus kinds, and the
wire contract shared with the out-of-tree arq worker.

The vector dimension is pinned here and at migration time to the P0 provider
(`text-embedding-3-small`, 1536). Changing the provider dimension is a migration,
not a config flip, so the column and this constant move together.

The arq queue name and the two job names are a duplicated wire contract with the
worker package (which re-declares the same literals), like the internal-boundary
header names. A change here that is not mirrored in ``floresu_worker`` would route
enqueued jobs to a queue the worker never drains; the cross-package contract tests
are the guard against that drift.
"""

from __future__ import annotations

from enum import StrEnum

# The P0 embedding provider and its output dimension. The dimension is pinned to
# the ``vector(N)`` column at migration time; the provider and the column can only
# change together (a migration), never via a runtime toggle.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536


class EmbedItemKind(StrEnum):
    """The three embeddable corpus kinds; the ``embeddings.item_kind`` discriminator.

    The values match the ``WriteEvent.entity_type`` strings the corpus writers emit
    (worklog entries, canonical bullets, and profile sources), so the enqueue seam
    maps a write event to an embed job by this membership alone. Outputs (resume
    documents) are deliberately absent: they never enter the searchable corpus.
    """

    WORKLOG = "worklog"
    BULLET = "bullet"
    SOURCE = "source"


# The arq queue the external app enqueues onto and the worker drains, plus the two
# job (arq function) names. Shared wire contract with ``floresu_worker``.
EMBED_QUEUE_NAME = "floresu:embed"
EMBED_ITEM_JOB = "embed_item"
PURGE_ITEM_JOB = "purge_item"
