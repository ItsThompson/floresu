# Testing

This guide describes the test layers, how to run each one, the main patterns, and the high-value targets. It documents the current implemented state.

## Philosophy

- Pure deep modules (the copy-on-write scope resolver, the reciprocal-rank fusion, the search DAG assembly, the resume document operations) are exhaustively tested, including property tests where useful.
- Trust boundaries fail closed and are tested for the deny path.
- Cross-package wire contracts are machine-gated, so drift between the backend and the MCP server fails a test rather than a request in production.
- The resume document shape is frozen by a golden plus a hash lock, so a released shape cannot change silently.
- The frontend pins a coverage floor and tests its data layer against a mock backend, so test behavior cannot drift from production behavior.

## Test layers

| Layer | Scope | Tooling | Command |
|-------|-------|---------|---------|
| Backend unit and integration | Service rules, repositories, routers, OAuth flow, DB integration | pytest, Postgres + Redis via testcontainers, 80% coverage gate | `cd backend && uv run pytest` |
| Backend property tests | The pure deep modules (fusion, DAG, document ops, scope resolver) | pytest plus hypothesis | `cd backend && uv run pytest` |
| Worker | The embed and purge jobs, the internal client, the provider | pytest, 80% coverage gate | `cd worker && uv run pytest` |
| MCP | Tool registration, the internal client, the bearer boundary, the frozen tool schemas | pytest, 80% coverage gate | `cd mcp && uv run pytest` |
| Contract drift | The internal-boundary header constants and the MCP-to-backend schema mirror | pytest in the `contract/` project | `cd contract && uv run pytest` |
| Codegen drift | The committed frontend client is regenerated and diffed against a clean tree | `just codegen`, then `git diff --exit-code` | (CI `codegen-drift` job) |
| Resume schema lock | The resume golden snapshot plus the append-only sha256 hash lock | pytest golden + guard tests | (CI `resume-schema-lock` job) |
| Frontend unit and component | Components, hooks, the data layer | vitest plus Testing Library, 70% coverage gate | `cd frontend && npm test` |
| Frontend acceptance | The data layer against a mock backend | vitest plus MSW | `cd frontend && npm test` |
| E2E | The full spine and UI smoke against the running stack | Playwright | `cd e2e && npm test` |

The contract project is the only interpreter where the backend and MCP packages import together (it editable-installs both). Run it with `cd contract && uv run pytest`, or let CI run it.

## Patterns

The examples below are illustrative, not copied source. They show the shape of each style.

### A pure-module unit test

A pure deep module takes inputs and returns a result, so a test asserts on the return value with no I/O or mocks.

```python
def test_mcp_scope_is_required_for_an_agent_edit():
    with pytest.raises(Validation):
        resolve_edit_scope(channel=EditChannel.MCP, requested=None, used_in_count=1)
```

### An MSW-backed hook test

A data-layer test renders a hook through the provider stack and serves the REST response from an MSW handler, so the test pins the real client contract.

```tsx
it("returns the worklog timeline", async () => {
  server.use(http.get("*/worklog", () => HttpResponse.json(entries)));
  const { result } = renderHook(() => useWorklog(), { wrapper: renderWithProviders });
  await waitFor(() => expect(result.current.data).toEqual(entries));
});
```

### A route-coverage assertion

Every mounted product route needs a `route_registry.py` entry per app. The coverage test cross-checks the mounted routes against the registry in both directions, so an undeclared route fails deny.

```python
def test_external_routes_are_all_declared():
    report = verify_route_coverage(external_app, EXTERNAL_ROUTE_ACCESS)
    assert report.is_covered
```

Canonical source: `backend/tests/`.

## High-value targets

| Priority | Target | Focus |
|----------|--------|-------|
| High | Route coverage | `test_route_registry.py`; an undeclared route fails deny, in both apps |
| High | Auth boundaries | `require_user` and `require_internal_user` deny paths; the OAuth cleanup reaper; refresh replay |
| High | Contract drift | `contract/tests/`; the header constants and the MCP-to-backend schema mirror |
| High | Resume schema lock | The golden plus the hash lock; a shape change fails unless the version is bumped and an upcaster is registered |
| High | Copy-on-write scope | The web-prompt-versus-agent-explicit rule; forking and promotion |
| Medium | Hybrid search | Empty query, filtered-to-nothing, and the degrade-to-lexical soft notice |
| Medium | Embedding pipeline | The content-hash gate; supersede, purge, and the failure retry |

## End-to-end scenarios

The Playwright spine drives the full stack. Twenty-three specs live in `e2e/tests/`, grouped by the surface they drive:

| Group | Specs | Covers |
|-------|-------|--------|
| First run and auth | `initialize`, `auth` | First-run bring-up and the empty state; human register, login, session resume, logout |
| Worklog | `worklog`, `worklog-timeline`, `worklog-tags`, `worklog-side-panel` | Recording and editing entries; month grouping and combined filters; tag add and remove with a deterministic color; the source contextual panel |
| Library and search | `library-search`, `search-filters` | Library bullets and hybrid search; combined filters with results grouped by source |
| Resumes | `resume-assemble`, `resume-history`, `resume-variant`, `resume-delete` | Building a resume from library bullets; revision history and stored-PDF viewing; the header identity-variant selector; confirm-gated permanent delete with retention |
| Job hunting | `jobhunt` | Job applications and the finalize-on-submit flow |
| Career profile | `profile-sources`, `skills`, `identity-archive` | Creating each source kind through the browser; curating skills and the derived usage count; archiving a referenced variant and its replacement prompt |
| Feed and history | `feed`, `item-history` | The live activity feed (SSE); the per-item history surface |
| Settings, data, account | `settings`, `data-export`, `account-delete` | Archive restore and web-only permanent delete; the account export archive; confirm-gated account delete |
| Agents | `agent-boundary`, `agent-revoke` | The agent OAuth connect flow and the bearer boundary; revoking an agent and killing its refresh token |

Three browser-flaky flows stay at the vitest layer by design and this suite does not claim them. See `e2e/README.md` for that boundary and for the sharded CI run.

No E2E run calls OpenAI or real R2: embedding is a local fake and the object store is MinIO.

## Coverage gates

| Suite | Floor | Enforced by |
|-------|-------|-------------|
| Backend | 80% | `backend/pyproject.toml` (`--cov-fail-under=80`) |
| Worker | 80% | `worker/pyproject.toml` (`--cov-fail-under=80`) |
| MCP | 80% | `mcp/pyproject.toml` (`--cov-fail-under=80`) |
| Frontend | 70% | `frontend/vite.config.ts` thresholds |

A run below a floor fails locally and in CI.

## Cross-references

- Commands and local setup: `docs/development.md`.
- CI jobs and gates: `docs/ci-cd.md`.
- The MCP tool surface and the internal hop: `docs/mcp.md`.
- Storage ownership and the resume model: `docs/data-model.md`.
