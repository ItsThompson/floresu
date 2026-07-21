"""The copy-on-write scope resolver: the product's core intent rule, as pure logic.

Editing a resume item that resolves to a canonical bulletpoint is intent-driven,
and the intent is stated differently on the two clients:

- The **web** UI prompts for scope only when the bullet is shared by two or more
  resumes; a bullet used by one resume (or none) applies in place without a prompt,
  which is equivalent to ``everywhere``.
- The **MCP** tool always carries an explicit ``scope`` argument, so the agent must
  state intent; omitting it is a validation error, never a silent default.

:func:`resolve_edit_scope` is that rule as one pure function of the channel, the
scope the caller supplied (if any), and the "used in N" count. It decides one of
three outcomes: prompt the web user, apply the edit only to this resume (fork a
resume-local copy), or apply it everywhere (edit the canonical bullet). It performs
no I/O, so the service supplies the count and acts on the outcome, and the rule is
exhaustively unit-testable in isolation.
"""

from __future__ import annotations

from enum import StrEnum

from floresu.core.errors import Validation


class EditChannel(StrEnum):
    """Which client boundary an edit arrives on; it decides how scope is stated."""

    WEB = "web"  # prompts for scope only when the bullet is shared (used in >= 2)
    MCP = "mcp"  # scope is a required, explicit argument (the agent states intent)


class ResumeEditScope(StrEnum):
    """The intent a scoped bullet edit carries: fork here, or edit the canonical."""

    THIS_RESUME = "this_resume"  # fork a resume-local copy; canonical bullet untouched
    EVERYWHERE = "everywhere"  # edit the canonical bullet; every reference updates


class ScopeResolution(StrEnum):
    """The resolver's decision: prompt the web user, or apply one of the two scopes."""

    PROMPT = "prompt"  # web only: the bullet is shared, so ask before applying
    THIS_RESUME = "this_resume"
    EVERYWHERE = "everywhere"


# The web prompt fires when a bullet is referenced by this many live resumes or more.
SHARED_BULLET_THRESHOLD = 2


def resolve_edit_scope(
    *, channel: EditChannel, requested: ResumeEditScope | None, used_in_count: int
) -> ScopeResolution:
    """Resolve how a scoped bullet edit applies, per the channel's intent rule.

    - MCP requires an explicit scope; a missing scope is a validation error.
    - Web honors an explicit scope when the user has already chosen one; otherwise
      it prompts when the bullet is shared (used in two or more resumes) and applies
      everywhere when it is not (used in one resume, or none).
    """
    if requested is not None:
        return ScopeResolution(requested.value)
    if channel is EditChannel.MCP:
        raise Validation(
            "An agent edit of a shared bullet requires an explicit scope of "
            "'this_resume' or 'everywhere'.",
            fields={"scope": "required for an agent edit"},
        )
    if used_in_count >= SHARED_BULLET_THRESHOLD:
        return ScopeResolution.PROMPT
    return ScopeResolution.EVERYWHERE
