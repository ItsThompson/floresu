"""Hybrid search: the deep module backing the Library view and the agent tool.

A single small interface (:class:`~floresu.search.schemas.SearchQuery` in,
:class:`~floresu.search.schemas.SearchResult` out) hides the retrieval pipeline
(lexical FTS + semantic pgvector ANN), the model-free RRF fusion, and the
provenance-graph assembly, so the engine can be replaced without touching callers.
"""

from __future__ import annotations
