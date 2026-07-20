"""The internal-boundary header names are the single-sourced wire contract.

These string values are shared with the out-of-tree MCP client and pinned by a
cross-package contract test. Renaming a value here is a wire-breaking change, so
this test fixes the exact strings and guards against an accidental edit.
"""

from __future__ import annotations

from floresu.core.headers import ACTOR_HEADER, INTERNAL_API_TOKEN_HEADER, USER_ID_HEADER


def test_internal_boundary_header_names_are_the_wire_contract() -> None:
    assert USER_ID_HEADER == "X-User-ID"
    assert INTERNAL_API_TOKEN_HEADER == "X-Internal-Api-Token"
    assert ACTOR_HEADER == "X-Actor"


def test_the_three_boundary_headers_are_distinct() -> None:
    names = {USER_ID_HEADER, INTERNAL_API_TOKEN_HEADER, ACTOR_HEADER}
    assert len(names) == 3
