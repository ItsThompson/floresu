# contract

Dev- and test-only cross-package drift guards. This project exists to catch
divergence between the MCP server's wire types and the backend's wire types, and
to assert the internal-boundary header constants match across packages.

It is never shipped. It editable-installs both the backend and the MCP packages
so the contract tests can import both in one interpreter.
