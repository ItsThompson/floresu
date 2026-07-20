"""Pytest configuration shared by the backend test suite."""

NO_TESTS_COLLECTED = 5


def pytest_sessionfinish(session, exitstatus):
    """Treat "no tests collected" (exit code 5) as success.

    An empty suite reports exit code 5. A collection or import error reports a
    different code, so a genuine failure still fails the gate.
    """
    if exitstatus == NO_TESTS_COLLECTED:
        session.exitstatus = 0
