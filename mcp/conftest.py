"""Pytest configuration shared by the MCP test suite."""

from pathlib import Path

NO_TESTS_COLLECTED = 5
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")


def pytest_sessionfinish(session, exitstatus):
    """Treat "no tests collected" as success only while the suite is empty.

    An empty suite reports exit code 5. This remaps 5 to 0, but only when no test
    module exists yet under the configured test paths. Once a test module is
    present, a zero-collection result (for example a misconfigured ``testpaths``)
    stays a failure. Collection and import errors report other codes and already
    fail the gate.
    """
    if exitstatus != NO_TESTS_COLLECTED:
        return
    rootpath = Path(session.config.rootpath)
    testpaths = session.config.getini("testpaths") or ["."]
    for testpath in testpaths:
        base = rootpath / testpath
        if any(next(base.rglob(pattern), None) is not None for pattern in TEST_FILE_PATTERNS):
            return
    session.exitstatus = 0
