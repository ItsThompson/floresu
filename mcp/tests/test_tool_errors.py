"""Tool-error mapping tests.

Backend RFC 9457 problem+json bodies fold into one model-recoverable message; a
success passes through; a non-JSON body degrades to a readable fallback. The
carried status/code let the tool-metrics wrapper log structurally.
"""

from __future__ import annotations

import httpx
import pytest

from floresu_mcp.tool_errors import BackendToolError, raise_for_problem
from tests.fakes import json_error


def test_success_response_passes_through() -> None:
    response = httpx.Response(200, json={"id": 1})

    assert raise_for_problem(response) is response


def test_problem_body_folds_into_a_recoverable_message() -> None:
    response = json_error(409, "STALE_REVISION", "The resume changed; re-read and retry.")

    with pytest.raises(BackendToolError) as excinfo:
        raise_for_problem(response)

    error = excinfo.value
    assert error.status_code == 409
    assert error.code == "STALE_REVISION"
    assert "STALE_REVISION" in str(error)
    assert "re-read" in str(error)


def test_field_and_violation_details_are_rendered() -> None:
    response = json_error(
        422,
        "VALIDATION",
        "invalid input",
        fields={"title": "must not be blank"},
        violations=[{"rule": "dag_cycle", "message": "cycle detected", "ids": ["b1", "b2"]}],
    )

    with pytest.raises(BackendToolError) as excinfo:
        raise_for_problem(response)

    message = str(excinfo.value)
    assert "title: must not be blank" in message
    assert "dag_cycle" in message
    assert "b1" in message and "b2" in message


def test_non_json_body_degrades_to_a_readable_fallback() -> None:
    response = httpx.Response(502, text="upstream boom")

    with pytest.raises(BackendToolError) as excinfo:
        raise_for_problem(response)

    error = excinfo.value
    assert error.status_code == 502
    assert error.code == "HTTP_502"
    assert "upstream boom" in str(error)
