"""Exhaustive unit tests for the copy-on-write scope resolver.

The resolver is the product's core intent rule, so every branch is covered
directly: the web used-in-1-vs-2 threshold, an explicit web scope short-circuiting
the prompt, the MCP explicit-scope requirement, and both resolved scopes. It is
pure, so no fakes are needed.
"""

from __future__ import annotations

import pytest

from floresu.core.errors import Validation
from floresu.resumes.cow import (
    SHARED_BULLET_THRESHOLD,
    EditChannel,
    ResumeEditScope,
    ScopeResolution,
    resolve_edit_scope,
)


def test_the_shared_threshold_is_two() -> None:
    # The web prompt fires at two or more referencing resumes, not before.
    assert SHARED_BULLET_THRESHOLD == 2


@pytest.mark.parametrize("used_in_count", [0, 1])
def test_web_unshared_bullet_applies_everywhere_without_a_prompt(used_in_count: int) -> None:
    resolution = resolve_edit_scope(
        channel=EditChannel.WEB, requested=None, used_in_count=used_in_count
    )
    assert resolution is ScopeResolution.EVERYWHERE


@pytest.mark.parametrize("used_in_count", [2, 3, 17])
def test_web_shared_bullet_prompts_for_scope(used_in_count: int) -> None:
    resolution = resolve_edit_scope(
        channel=EditChannel.WEB, requested=None, used_in_count=used_in_count
    )
    assert resolution is ScopeResolution.PROMPT


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (ResumeEditScope.THIS_RESUME, ScopeResolution.THIS_RESUME),
        (ResumeEditScope.EVERYWHERE, ScopeResolution.EVERYWHERE),
    ],
)
def test_web_explicit_scope_is_honored_even_when_shared(
    requested: ResumeEditScope, expected: ScopeResolution
) -> None:
    # Once the user has answered the prompt, the chosen scope applies regardless of
    # the shared count.
    resolution = resolve_edit_scope(channel=EditChannel.WEB, requested=requested, used_in_count=9)
    assert resolution is expected


def test_mcp_requires_an_explicit_scope() -> None:
    with pytest.raises(Validation) as excinfo:
        resolve_edit_scope(channel=EditChannel.MCP, requested=None, used_in_count=5)
    assert "scope" in (excinfo.value.fields or {})


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (ResumeEditScope.THIS_RESUME, ScopeResolution.THIS_RESUME),
        (ResumeEditScope.EVERYWHERE, ScopeResolution.EVERYWHERE),
    ],
)
@pytest.mark.parametrize("used_in_count", [0, 1, 2, 8])
def test_mcp_applies_the_explicit_scope_regardless_of_count(
    requested: ResumeEditScope, expected: ScopeResolution, used_in_count: int
) -> None:
    # The agent never prompts; its explicit scope applies whether the bullet is
    # shared or not.
    resolution = resolve_edit_scope(
        channel=EditChannel.MCP, requested=requested, used_in_count=used_in_count
    )
    assert resolution is expected
