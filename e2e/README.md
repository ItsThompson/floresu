# e2e

Playwright full-stack end-to-end tests. They drive a real browser against the
real system: both backend ASGI apps, the frontend production build, Postgres
(pgvector), Redis, and MinIO (an S3-compatible stand-in for Cloudflare R2). The
embedding provider is a local fake, so no run calls OpenAI or real R2.

## What it covers

The product's critical paths, end to end:

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
