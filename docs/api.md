# REST API reference

This reference catalogs the Floresu backend REST surface, the access-level map, the copy-on-write item flow, and the error contract.

Canonical sources:

- Access map (machine-checked): `backend/src/floresu/core/route_registry.py`
- Domain wire schemas: each domain's `schemas.py` and `router.py`
- Error contract: `backend/src/floresu/core/errors.py`, `backend/src/floresu/oauth/errors.py`
- Revision guard: `backend/src/floresu/resumes/operations.py` (`guard_revision`), with a parallel path in `library/`
- Unique-constraint conflict mapping: `backend/src/floresu/core/conflicts.py`
- Generated client contract: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`, `frontend/src/api/client.ts`

The Pydantic schema modules are the single source of truth for the wire shapes. The frontend consumes the external app's document as OpenAPI-generated TypeScript. Run `just codegen` after any external REST change; CI drift-gates the generated client.

## Two apps and access levels

The backend serves two apps from one factory. The external app (`:8000`) is internet-facing. The internal app (`:8001`) is app-net only and is the MCP server's and the embed worker's only intended caller. See `architecture.md` for the split and `auth.md` for the trust boundaries.

Every mounted product route declares an access level in `route_registry.py`. A coverage test cross-checks the mounted routes (read from each app's OpenAPI document) against the per-app registry in both directions: an `undeclared` mounted route fails deny, and an `orphaned` registry entry catches a stale declaration. So an unscoped endpoint cannot ship.

| Access level | Meaning |
|--------------|---------|
| `PUBLIC` | No authentication (session-establishing auth endpoints, OAuth discovery metadata). |
| `EXTERNAL_COOKIE` | `require_user`: the human session cookie. |
| `INTERNAL_TRUSTED` | `require_internal_user`: the trusted `X-User-ID` behind `X-Internal-Api-Token`. |
| `OAUTH` | The OAuth 2.1 AS handshake surface (unauthenticated protocol endpoints). |

The same path can carry different levels on the two apps. For example `POST /worklog` is `EXTERNAL_COOKIE` on `:8000` and `INTERNAL_TRUSTED` on `:8001`. Health and metrics routes mount with `include_in_schema=False`, so the coverage check excludes them by construction. See `monitoring.md` for `/metrics`.

## Route groups

The internal app mounts the same domain routers as the external app, but never the web-only lifecycle routes, the human auth and `/me` routes, the OAuth AS, or the feed. It additionally mounts the embedding pipeline. The internal app exposes zero `DELETE` routes: partial mutations and purges use `POST`.

| Group | Prefix | External `:8000` | Internal `:8001` |
|-------|--------|------------------|------------------|
| Human auth | `/auth` | `PUBLIC` | not mounted |
| Current user | `/me` | `EXTERNAL_COOKIE` | not mounted |
| OAuth 2.1 AS | `/.well-known`, `/oauth`, `/me/clients` | `OAUTH` / `EXTERNAL_COOKIE` | not mounted |
| Profile sources | `/sources` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Skills | `/skills` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Identity variants | `/identity-variants` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Worklog + tags | `/worklog` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Library bullets | `/bullets` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Resumes + rendering + revisions + finalize | `/resumes` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Job applications | `/job-applications` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Hybrid search | `/search` | `EXTERNAL_COOKIE` | `INTERNAL_TRUSTED` |
| Embedding pipeline | `/embed` | not mounted | `INTERNAL_TRUSTED` |
| Activity feed | `/feed` | `EXTERNAL_COOKIE` | not mounted |
| Web-only lifecycle | various | `EXTERNAL_COOKIE` | not mounted |

## Human auth and current user

External app only. See `auth.md` for the session and OAuth models.

| Method and path | Access | Notes |
|-----------------|--------|-------|
| `POST /auth/register` | `PUBLIC` | 201; sets both cookies; returns `AuthenticatedUser` |
| `POST /auth/login` | `PUBLIC` | Generic 401 on any credential mismatch |
| `POST /auth/refresh` | `PUBLIC` | Reads `floresu_refresh`; rotates the session |
| `POST /auth/logout` | `PUBLIC` | 204; revokes the `sid`; clears cookies |
| `GET /me` | `EXTERNAL_COOKIE` | The resolved user |
| `POST /me/onboarding` | `EXTERNAL_COOKIE` | Marks onboarding complete |

## OAuth 2.1 AS

External app only.

| Method and path | Access | Notes |
|-----------------|--------|-------|
| `GET /.well-known/oauth-authorization-server` | `OAUTH` | RFC 8414 metadata, `no-store` |
| `GET /oauth/jwks` | `OAUTH` | Public JWKS, `no-store` |
| `POST /oauth/register` | `OAUTH` | RFC 7591 Dynamic Client Registration; 201 |
| `GET /oauth/authorize` | `OAUTH` | 302 to the SPA consent page with `auth_request_id` |
| `GET /oauth/authorize/context` | `OAUTH` | Consent context (optional session) |
| `POST /oauth/authorize/decision` | `EXTERNAL_COOKIE` | The consent decision |
| `POST /oauth/token` | `OAUTH` | Both grant types; `no-store` |
| `POST /oauth/revoke` | `OAUTH` | RFC 7009 refresh-token revoke |
| `GET /me/clients` | `EXTERNAL_COOKIE` | The user's connected agents |
| `DELETE /me/clients/{client_id}` | `EXTERNAL_COOKIE` | 204; revoke a grant |

## Profile, worklog, and library

Mounted on both apps at the same paths. Each domain follows one shape: create, list, get, update (`PUT`), soft-archive (`POST .../archive`), and restore (`POST .../restore`). Skills and sources also carry a `POST .../reorder`.

| Group | Representative routes |
|-------|-----------------------|
| Sources | `POST /sources`, `GET /sources`, `POST /sources/reorder`, `GET/PUT /sources/{id}`, `POST /sources/{id}/archive`, `POST /sources/{id}/restore` |
| Skills | `POST /skills`, `GET /skills`, `POST /skills/reorder`, `GET/PUT /skills/{id}`, `POST /skills/{id}/archive`, `POST /skills/{id}/restore` |
| Identity variants | `POST /identity-variants`, `GET /identity-variants`, `GET/PUT /identity-variants/{id}`, `POST /identity-variants/{id}/archive`, `POST /identity-variants/{id}/restore` |
| Worklog | `POST /worklog`, `GET /worklog`, `GET /worklog/tags`, `GET/PUT /worklog/{id}`, `POST /worklog/{id}/archive`, `POST /worklog/{id}/restore`, `POST /worklog/{id}/tags` |
| Library | `POST /bullets`, `GET /bullets`, `GET/PUT /bullets/{id}`, `POST /bullets/{id}/archive`, `POST /bullets/{id}/restore` |

`POST /worklog/{id}/tags` carries `{label, action}` for both add and remove, so the internal app needs no `DELETE`. `PUT /bullets/{id}` advances the bullet's optimistic `revision` under `If-Match`.

## Resumes, rendering, and job applications

Mounted on both apps. The core resume routes and the rendering, revision, finalize, and copy-on-write routes:

| Method and path | Purpose | Notes |
|-----------------|---------|-------|
| `POST /resumes` | Create a living or application resume | `kind` chosen at creation |
| `GET /resumes` | List resumes | `kind` and `include_archived` filters |
| `GET /resumes/{id}` | Full resolved document | |
| `PUT /resumes/{id}` | Overwrite the document | `If-Match` revision |
| `POST /resumes/{id}/items` | Append an item to a section | `If-Match`; see the deep spec |
| `POST /resumes/{id}/items/{item_id}/remove` | Remove an item | `If-Match` |
| `POST /resumes/{id}/reorder` | Reorder sections or items | `If-Match` |
| `POST /resumes/bullet-edit` | Copy-on-write scoped bullet edit | `If-Match` revisions in the body |
| `POST /resumes/{id}/items/{item_id}/promote` | Promote a resume-local item to a canonical bullet | `If-Match` |
| `GET /resumes/templates` | List global render templates | |
| `POST /resumes/{id}/preview` | Ephemeral PDF stream | Never stored |
| `POST /resumes/{id}/export` | Persist a PDF to R2 | Records the object key |
| `GET /resumes/{id}/revisions` | List published versions | Revisions with a stored PDF |
| `GET /resumes/{id}/revisions/{revision_no}/pdf` | Presigned URL for a version's PDF | Read only |
| `POST /resumes/{id}/finalize` | Freeze an application resume | Snapshots identity, stores the PDF, submits the linked application |
| `POST /job-applications` | Create an application | |
| `GET /job-applications` | List applications | |
| `GET /job-applications/{id}` | One application with its linked resume id | |
| `PATCH /job-applications/{id}` | Edit an application; `status=submitted` finalizes the linked resume | |

## Embedding pipeline and search

The embedding pipeline is internal-app only: the arq worker reads an item's text and writes back its vector over these trusted-header routes. Purge is a `POST`, not a `DELETE`, so the internal app keeps its zero-`DELETE` invariant.

| Method and path | App | Purpose |
|-----------------|-----|---------|
| `GET /embed/items/{kind}/{item_id}` | internal | Read the item's embeddable text and current content hash |
| `PUT /embed/items/{kind}/{item_id}` | internal | Write the vector back (re-gated on the content hash) |
| `POST /embed/items/{kind}/{item_id}/purge` | internal | Remove the vector (archived or deleted item) |
| `POST /search` | both | Hybrid search over the corpus |

`POST /search` runs lexical retrieval (full-text GIN) plus best-effort semantic retrieval (pgvector), fuses the two rankings with reciprocal rank fusion, and returns a scored provenance DAG. An empty query returns an empty result, never a full dump. A failed query embedding degrades to lexical-only and surfaces a soft notice. See `data-model.md` for the vector index.

## Web-only lifecycle and feed

External app only, so an agent has no destructive route. Permanent delete uses `DELETE`.

| Method and path | Purpose |
|-----------------|---------|
| `DELETE /worklog/{id}` | Hard-delete a worklog entry |
| `DELETE /sources/{id}` | Hard-delete a source |
| `DELETE /bullets/{id}` | Hard-delete a bullet |
| `DELETE /resumes/{id}` | Hard-delete a resume |
| `GET /account/export` | Export the account's data |
| `DELETE /account` | Delete the account |
| `GET /feed` | The live activity SSE stream |
| `GET /feed/history` | The initial-load feed read |

`GET /feed` is a `text/event-stream`. Each event frame carries the monotonic `audit_log.id` as the SSE `id:`, so the browser reports it back as `Last-Event-ID` on reconnect and the server replays the buffered gap. See `data-model.md` for the audit log.

## Deep spec: resume copy-on-write item flow

A resume item either references a canonical bullet (`library_ref`) or holds inline text (`local`). Editing a referenced bullet is intent-driven, and the intent differs by client (`resumes/cow.py`).

- Web prompts for scope only when the bullet is shared (referenced by two or more live resumes). A bullet used by one resume, or none, applies in place, which is equivalent to `everywhere`.
- The MCP tool always carries an explicit `scope` argument; omitting it is a validation error, never a silent default.

The two scopes:

- `this_resume`: fork every reference to that bullet in this resume into a resume-local item carrying the edited text and `forked_from_bullet_id`. The canonical bullet is untouched. The write-derived index drops the bullet's row unless another item still references it.
- `everywhere`: edit the canonical bullet; every reference updates.

The routes:

- `POST /resumes/bullet-edit` carries the scope and the guarding revisions in the body: the canonical bullet revision for `everywhere`, the resume revision for `this_resume`.
- `POST /resumes/{id}/items/{item_id}/promote` promotes a resume-local item to a canonical bullet and swaps the item to a reference. Only a `local` item can be promoted; a `library_ref` item already is one. The resume revision travels in `If-Match`.

Concurrency: the resume `revision` (or the bullet `revision`) is the optimistic-concurrency token. On `PUT`, add-item, remove-item, reorder, and promote it travels in the `If-Match` header. `guard_revision` rejects a stale value.

## Error contract

Every service-layer fault raises a `FloresuError` subclass. One exception handler maps the whole hierarchy to RFC 9457 `application/problem+json`, so every transport (external REST, internal REST, MCP over internal REST) emits one error shape. FastAPI's `RequestValidationError` maps into the same field-map shape. Never build problem+json by hand.

### Problem body

Media type `application/problem+json`. Members: `type`, `title`, `status`, `code`, `detail`, optional `instance`, `fields`, `violations`. Extension members are omitted from the wire when unset.

### Error codes

`code` is the `ErrorCode` StrEnum (`core/errors.py`). It is the base HTTP vocabulary every service raises, and the whole product vocabulary today: no domain currently adds a code (the module docstring leaves that open for a future domain-specific code, but none exists).

| Code | Status | Meaning |
|------|--------|---------|
| `NOT_FOUND` | 404 | Resource not found (also the 404-over-403 no-existence-leak answer for a resource another account owns) |
| `UNAUTHORIZED` | 401 | Authentication required or session expired |
| `FORBIDDEN` | 403 | Reserved; not raised in production (the service returns 404 instead) |
| `VALIDATION` | 422 | Request or structural validation failed; may carry a `violations` array |
| `CONFLICT` | 409 | Conflict with the current state |
| `INTERNAL` | 500 | Unexpected fault; the body is generic and leaks no stack trace |

Concurrency and immutability outcomes reuse the base `CONFLICT` code; there is no distinct `STALE_REVISION` or `IMMUTABLE` code and no `412`:

| Outcome | Status | Code | Source |
|---------|--------|------|--------|
| Stale `If-Match` revision | 409 | `CONFLICT` | `resumes/operations.py` `guard_revision` (parallel path in `library/`) |
| Write against a finalized resume | 409 | `CONFLICT` | `resumes/operations.py` `guard_editable` |
| Missing or malformed `If-Match` header | 422 | `VALIDATION` | FastAPI `RequestValidationError` |
| Duplicate of a unique constraint (name, label, 1:1 link) | 409 | `CONFLICT` | `core/conflicts.py` `conflict_on_duplicate` |
| Non-owner or unknown resource | 404 | `NOT_FOUND` | 404-over-403 |

Structural violations surface as a `Violation` list (`rule`, `ids`, `message`) in the problem body.

### Two error contracts on the OAuth router

The OAuth router uses two error contracts by design (`oauth/errors.py`).

- Agent protocol endpoints (`/oauth/register`, `/oauth/authorize`, `/oauth/token`, `/oauth/revoke`) return RFC 6749 `{error, error_description}` JSON that the MCP SDK parses. The `OAuthErrorCode` set includes `invalid_grant`, `invalid_client`, `invalid_target` (RFC 8707), and more.
- SPA-facing endpoints (`/oauth/authorize/context`, `/oauth/authorize/decision`, `/me/clients`) return RFC 9457 problem+json.

Do not mix them. Adding an OAuth route means choosing the right error family.

## The generated client

The frontend REST client is generated, never hand-written. `just codegen` exports the external app's OpenAPI document to `frontend/openapi.json`, then runs `openapi-typescript` into `frontend/src/api/schema.d.ts` (consumed by `client.ts`). The `codegen-drift` CI job regenerates both and fails on a stale committed client. See `development.md`.

## Cross-references

- Trust boundaries and the OAuth model: `docs/auth.md`.
- Storage ownership and the copy-on-write model: `docs/data-model.md`.
- MCP tool catalog and the internal-hop contract: `docs/mcp.md`.
- Code generation and env groups: `docs/development.md`.
- The `/metrics` endpoint and error-rate alerts: `docs/monitoring.md`.
