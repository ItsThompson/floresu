"""Worker-side wire constants, mirrored from the backend.

The worker shares no code with the backend, so it re-declares the few wire
literals the internal-API hop and the arq queue need: the internal-boundary
header names, the embed queue name, the two job (arq function) names, and the
embed route prefix. These MUST match the backend (``floresu.embedding.config`` and
``floresu.core.headers``); a silent drift would route jobs to a queue the worker
never drains or send an unrecognized identity header. No machine guard pins them
equal: ``contract/tests/`` covers the MCP-to-backend mirror only, so this match is
an unenforced convention.
"""

from __future__ import annotations

# Internal trust-boundary headers, mirrored from ``floresu.core.headers``. The
# worker sets X-User-ID (the item owner) + X-Internal-Api-Token on every call.
USER_ID_HEADER = "X-User-ID"
INTERNAL_API_TOKEN_HEADER = "X-Internal-Api-Token"
ACTOR_HEADER = "X-Actor"
REQUEST_ID_HEADER = "X-Request-ID"

# The arq queue this worker drains and the two job names it registers, mirrored
# from ``floresu.embedding.config``.
EMBED_QUEUE_NAME = "floresu:embed"
EMBED_ITEM_JOB = "embed_item"
PURGE_ITEM_JOB = "purge_item"

# The internal-app embed route prefix; the worker reads item text and writes the
# vector back under ``/embed/items/{kind}/{item_id}``.
EMBED_PATH = "/embed/items"

# The pinned P0 provider model and its output dimension, mirrored from
# ``floresu.embedding.config``. Pinned to the backend's ``embeddings.vector``
# column; changing them is a backend migration, not a worker config flip.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# The worker's actor label on the internal hop. Embedding is a system side
# channel, not an agent action, so it is attributed to the worker itself.
WORKER_ACTOR = "floresu-embed-worker"
