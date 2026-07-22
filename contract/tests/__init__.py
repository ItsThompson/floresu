"""Cross-package contract tests: the MCP<->backend drift guards.

This package is imported nowhere at runtime. It is the one interpreter that loads
both :mod:`floresu` (backend) and :mod:`floresu_mcp` (MCP server) so the two
independently re-declared wire contracts can be compared directly:

- :mod:`tests.test_schema_mirror` proves the MCP tool input/output schemas mirror
  the backend internal-API request/response types field-for-field.
- :mod:`tests.test_header_constants` proves the internal-boundary header names and
  the single OAuth scope are identical across the two packages.
"""
