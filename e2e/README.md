# e2e

Playwright full-stack end-to-end tests. They drive a real browser against the
real system: both backend ASGI apps, the frontend production build, Postgres
(pgvector), Redis, and MinIO (an S3-compatible stand-in for Cloudflare R2). The
embedding provider is a local fake, so no run calls OpenAI or real R2.

## What it covers

The product's critical paths end to end, plus the P0 management and destructive
flows and a P1 happy-path breadth layer (per-pixel and timing detail stay at the
vitest layer):

- **Initialize**: sign up, the onboarding wizard, land on Home (persisted, so it
  does not reappear on reload), then seed a role, a worklog entry, and a first
  living resume.
- **Update the worklog**: add and edit worklog entries and tags, then create a
  library bullet linked to a source and an entry.
- **Job hunting**: create a job application, fork a living resume into a tailored
  draft, edit it (including the copy-on-write scope dialog and promoting a local
  fork), see the live PDF preview, export the ATS PDF, and mark the application
  submitted (which finalizes the resume read-only; a later library edit never
  changes it).
- **Auth**: login, session resume on reload, and logout.
- **Live feed**: the SSE activity feed reflects a human action.
- **Search**: hybrid search ranks a worklog entry and a bullet together, a source
  filter narrows, and an empty query returns nothing.
- **Settings**: archive restore and web-only permanent delete.
- **Agent boundary**: the OAuth consent screen connects an agent, an agent write
  over the internal boundary is attributed in the feed with its color and bot
  glyph, the internal boundary denies without the token, and the agent has no
  delete route.
- **Data and account**: export the account archive (the download holds exactly the
  seeded records); delete the account behind a confirm + typed-email gate, after
  which sign-in fails and every connected agent is revoked.
- **Agent lifecycle**: connect an agent via consent, then revoke it; the held
  refresh token is invalidated immediately (`invalid_grant`).
- **Resume delete**: web-only, confirm-gated permanent delete. A finalized resume's
  stored PDF object and finalize audit row survive the delete, while the
  resume-scoped revisions route 404s (the revision rows cascade); a URL minted
  before the delete still resolves to the byte-identical frozen PDF.
- **Profile sources**: create project, education, and certification through the
  browser, each with its kind-specific fields, and attach a worklog entry.
- **Worklog breadth**: the global timeline with month grouping (newest first) and
  combined source/tag/date filters; the source contextual side panel, where a
  panel-added entry pre-attaches to that source; tag removal, where a removed tag
  stays global while used elsewhere and keeps a deterministic stable color.
- **Search breadth**: combined kind/tag/layer/date filters with results grouped by
  source (presence and grouping asserted, not rank).
- **Resume identity**: the header variant selector; selecting a variant re-points
  the header on the next preview, asserted through the resume document.
- **Skills**: curate a skills list (add, rename, reorder, archive); the usage count
  derives from worklog tags, and tags are never auto-promoted to skills.

### Not covered here (by design)

Three browser-flaky flows stay at the vitest layer; this suite does not claim
them:

- Transient SSE disconnect + gap replay:
  `frontend/src/views/HomeView/feedConnection.test.ts`. The live-feed spec here
  asserts only live push + reload replay, not drop/restore.
- Debounced preview refresh + expand-thumbnail timing:
  `frontend/src/views/ResumeEditorView/hooks/useResumePreview.test.ts`.
- Drag-to-reorder sections and items:
  `frontend/src/views/ResumeEditorView/hooks/useDragList.test.ts` and
  `frontend/src/views/ProfileHubView/hooks/useSectionOrder.test.ts`. Skills reorder
  is drag-only too, so the skills spec asserts the `POST /skills/reorder` outcome
  instead of the drag gesture.

### MCP coverage boundary

The agent scenario drives the OAuth authorization-server consent flow and the
internal write boundary (the seam the MCP server proxies to) directly, rather
than running a full MCP client loop. The MCP transport, token audience binding,
and tool surface are covered by the `mcp` and `contract` suites.

## Running

```sh
cd e2e
npm ci
npx playwright install chromium
npm test            # brings up infra, then runs the suite
```

`npm test` runs `harness/infra.ts up` (Docker Compose infra + migrations + object
-store bucket), then Playwright starts the app processes and runs the specs.
Infrastructure is torn down afterwards unless `E2E_KEEP_STACK=1` is set. Use
`npm run test:only` to skip the infra bring-up when the stack is already running.

Docker is required (the infrastructure runs from `docker-compose.e2e.yml` on
non-default host ports, so it never collides with a local dev stack).

### CI (sharded)

CI runs the `e2e` job as a matrix of four shards. Each shard runs
`npm test -- --shard=<i>/4` on its own runner VM with its own isolated stack, and
emits a `blob-report/`. A dependent `e2e-report` job downloads every shard blob
and merges them into one HTML report via `npx playwright merge-reports`.

Inside a shard, CI runs the specs in parallel (`fullyParallel: true`,
`workers: 4`), gated on `process.env.CI`; the isolation audit confirmed every spec
is account-scoped, so parallel contexts never share account state. Local runs are
unchanged: `npm test` is serial (`fullyParallel: false`, `workers: 1`) with no
sharding.
