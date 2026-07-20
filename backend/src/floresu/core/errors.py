"""Error contract: the single boundary between the service layer and HTTP.

The service layer raises :class:`FloresuError` subclasses; this module maps the
whole hierarchy to RFC 9457 ``application/problem+json`` in one exception handler,
so every transport (external REST, internal REST, and the MCP server layered on
the internal REST) emits one error contract. FastAPI's ``RequestValidationError``
is mapped into the same field-map shape so clients handle a single format.

Error codes are single-sourced as :class:`ErrorCode`; the machine-readable
``code`` and the human ``title`` travel in the body so an agent can self-correct
without a human. Domain-specific codes (e.g. resume immutability) are added by
their owning domains; the codes here are the base HTTP vocabulary every service
needs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.responses import Response

from floresu.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request

    from floresu.core.app_factory import ExceptionHandler, ExceptionKey

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

# Stable identifier base for the ``type`` member. RFC 9457 ``type`` URIs need not
# be dereferenceable; they are stable identifiers keyed off the error code.
ERROR_TYPE_BASE = "https://floresu.app/errors/"

_log = get_logger("floresu-core")


class ErrorCode(StrEnum):
    """Single source of machine-readable error codes carried in ``problem.code``.

    The base HTTP vocabulary every service raises. Domains extend this set with
    their own codes (e.g. optimistic-concurrency or immutability sub-codes) in
    their own modules as those features land.
    """

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    VALIDATION = "VALIDATION"
    CONFLICT = "CONFLICT"
    INTERNAL = "INTERNAL"


def _type_uri(code: ErrorCode) -> str:
    """Derive the ``type`` URI from a code: ``NOT_FOUND`` -> ``.../not-found``."""
    return f"{ERROR_TYPE_BASE}{code.value.lower().replace('_', '-')}"


class Violation(BaseModel):
    """One structural rule failure, model-recoverable by naming the rule and IDs.

    Carried in a :class:`Validation` error's problem+json body. Lives in the error
    contract because it is part of the wire shape every client reads.
    """

    rule: str
    ids: list[str]
    message: str


class ExpectedError(Exception):
    """Marker for a model-recoverable domain/protocol error, not an operational fault.

    Concrete subclasses expose an HTTP ``status``; the failure classifier
    (:func:`floresu.core.observability._is_unexpected`) reads it via ``getattr`` so
    it works whether ``status`` is a class attribute (:class:`FloresuError`) or set
    per-instance by another expected-error hierarchy. An ``ExpectedError`` with
    ``status < 500`` is not counted as a service-method failure.
    """


class FloresuError(ExpectedError):
    """Base of the service-layer error hierarchy mapped to problem+json.

    Subclasses fix the HTTP ``status``, default ``code``, and human ``title``.
    Callers pass a recoverable ``detail``, may override ``code`` with a more
    specific value, and may attach a field-level ``fields`` map.
    """

    status: ClassVar[int]
    title: ClassVar[str]
    default_code: ClassVar[ErrorCode]

    def __init__(
        self,
        detail: str,
        *,
        code: ErrorCode | None = None,
        fields: Mapping[str, str] | None = None,
        instance: str | None = None,
    ) -> None:
        self.detail = detail
        self.code = code or self.default_code
        self.fields = dict(fields) if fields else None
        self.instance = instance
        super().__init__(detail)


class NotFound(FloresuError):
    status = 404
    title = "Resource not found"
    default_code = ErrorCode.NOT_FOUND


class Forbidden(FloresuError):
    # The service applies a 404-over-403 policy (no existence leak), so this is
    # reserved for a future case where 403 is the correct answer (a resource the
    # caller CAN legitimately see but not act on).
    status = 403
    title = "Access forbidden"
    default_code = ErrorCode.FORBIDDEN


class Unauthorized(FloresuError):
    status = 401
    title = "Authentication required"
    default_code = ErrorCode.UNAUTHORIZED


class Conflict(FloresuError):
    status = 409
    title = "Conflict with the current state"
    default_code = ErrorCode.CONFLICT


class Validation(FloresuError):
    """422; additionally carries a ``violations`` array for structural failures."""

    status = 422
    title = "Validation failed"
    default_code = ErrorCode.VALIDATION

    def __init__(
        self,
        detail: str,
        *,
        violations: list[Violation] | None = None,
        code: ErrorCode | None = None,
        fields: Mapping[str, str] | None = None,
        instance: str | None = None,
    ) -> None:
        super().__init__(detail, code=code, fields=fields, instance=instance)
        self.violations = list(violations) if violations else []


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details body. Extension members (``code``/``fields``/
    ``violations``) are omitted from the wire when unset (``exclude_none``)."""

    type: str
    title: str
    status: int
    code: ErrorCode
    detail: str
    instance: str | None = None
    fields: dict[str, str] | None = None
    violations: list[Violation] | None = None


def _loc_to_field(loc: tuple[int | str, ...]) -> str:
    """Flatten a Pydantic error location into a dotted field path (``body.title``)."""
    return ".".join(str(part) for part in loc)


def _problem_from_floresu_error(exc: FloresuError, instance: str | None) -> ProblemDetail:
    violations = exc.violations if isinstance(exc, Validation) else None
    return ProblemDetail(
        type=_type_uri(exc.code),
        title=exc.title,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        instance=exc.instance or instance,
        fields=exc.fields,
        violations=violations or None,
    )


def _problem_from_request_validation(
    exc: RequestValidationError, instance: str | None
) -> ProblemDetail:
    fields = {_loc_to_field(error["loc"]): str(error["msg"]) for error in exc.errors()}
    return ProblemDetail(
        type=_type_uri(Validation.default_code),
        title="Request validation failed",
        status=Validation.status,
        code=Validation.default_code,
        detail=f"{len(fields)} request field(s) failed validation.",
        instance=instance,
        fields=fields,
    )


def _render(problem: ProblemDetail) -> Response:
    return Response(
        content=problem.model_dump_json(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
    )


async def handle_floresu_error(request: Request, exc: Exception) -> Response:
    """Map any :class:`FloresuError` subclass to problem+json (registered on the base)."""
    if not isinstance(exc, FloresuError):  # pragma: no cover - registered only for FloresuError
        raise exc
    return _render(_problem_from_floresu_error(exc, request.url.path))


async def handle_request_validation_error(request: Request, exc: Exception) -> Response:
    """Map FastAPI's ``RequestValidationError`` into the same field-map shape."""
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered for this type
        raise exc
    return _render(_problem_from_request_validation(exc, request.url.path))


async def handle_unexpected(request: Request, exc: Exception) -> Response:
    """Render any unhandled exception as a generic 500 problem+json.

    This is the single structured-fault log site: it emits exactly one ``error``
    event carrying ``exc_info`` (revives ``format_exc_info`` in the log chain) and
    the request path. The response body is generic so no stack trace or original
    exception message leaks to the client. ``request_id`` is added by the
    correlation contextvars binding, which the log chain merges automatically.
    """
    _log.error("unhandled_exception", exc_info=exc, path=request.url.path)
    return _render(
        ProblemDetail(
            type=_type_uri(ErrorCode.INTERNAL),
            title="Internal server error",
            status=500,
            code=ErrorCode.INTERNAL,
            detail="An unexpected error occurred.",
            instance=request.url.path,
        )
    )


def build_exception_handlers() -> dict[ExceptionKey, ExceptionHandler]:
    """The exception-handler map both apps wire through ``create_app``.

    One handler for the whole ``FloresuError`` hierarchy (Starlette dispatches by
    MRO), the ``RequestValidationError`` override, and a catch-all ``Exception``
    handler so any unhandled fault renders as a generic 500 problem+json (and is
    logged once) instead of leaking. The three keys are MRO-disjoint, so
    registration order is irrelevant.
    """
    handlers: dict[ExceptionKey, ExceptionHandler] = {
        FloresuError: handle_floresu_error,
        RequestValidationError: handle_request_validation_error,
        Exception: handle_unexpected,
    }
    return handlers
