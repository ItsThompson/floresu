# deployments

Operational overlays and provisioning for the single-VPS deploy: the production
Compose topology, the Cloudflare Tunnel ingress, box-less secret delivery, the
pre-traffic migration + CI-owned rollback, and the Prometheus -> Alertmanager ->
Discord monitoring stack.

## Topology

One box, one Compose project (`floresu`), three network tiers plus observability.
Every first-party service is expose-only (no host `ports:`); the Cloudflare
Tunnel is the sole ingress.

| Tier | Services |
|------|----------|
| edge | `frontend` (nginx static SPA) |
| compute | `backend` (both ASGI apps: `:8000` external + `:8001` internal), `mcp` (`:9000`), `worker` (arq) |
| data | `postgres` (pgvector), `redis` |
| observability | `prometheus`, `node-exporter`, `alertmanager`, `grafana` |
| ingress (deploy overlay) | `cloudflared` |

Networks: `app-net` carries every first-party service; `data-net` isolates the
data tier. Only `backend` and `worker` bridge `app-net <-> data-net`. `postgres`
is reachable only on `data-net`. `redis` is dual-homed (`data-net` + `app-net`)
so the MCP rate limiter reaches it on `app-net` without joining `data-net`.

## Compose files

| File | Role |
|------|------|
| `docker-compose.yml` | Production-shaped base (the deployable artifact): expose-only, all tiers |
| `docker-compose.dev.yml` | Local-dev overlay: host-published Postgres/Redis, dev env (`just up` / `just up-dev`) |
| `docker-compose.tunnel.yml` | Deploy overlay: `cloudflared`, environment-sourced secrets, app-net subnet pin |
| `docker-compose.deploy.yml` | Deploy overlay: `.env.prod` + app secrets to backend/mcp/worker/grafana |

`.env.prod` is the committed, non-secret half of the production config; real
secrets live only in GitHub Actions.

## Ingress and the path allow-list

`deployments/cloudflare/config.yml` is the committed ingress template (CI renders
the `CF_*` vars). One named tunnel, three hosts, outbound-only (zero inbound
ports), TLS at the Cloudflare edge. The path allow-list refuses the observability
surface at the edge:

- `floresu.app` -> `frontend:80`
- `api.floresu.app` -> `backend:8000`, but `/metrics`, `/healthz`, `/readyz` are 404'd at the edge
- `mcp.floresu.app` -> `mcp:9000`, but ONLY `/mcp(/...)` and the PRM document; everything else is 404'd
- the internal app (`:8001`) is never tunnel-routed

`/metrics` and health are scraped/probed in-network only.

## Box-less deploy

`scripts/deploy.sh` runs the Compose CLI in CI against the VPS Docker engine over
an SSH Docker Context. No `.env`, no rendered config, and no secret files ever
land on the box: every config/secret is read CLI-side and transmitted to the
daemon as an environment-sourced Compose config/secret.

Lifecycle: assert required secret env -> `pull` -> pre-traffic Alembic migration
(after Postgres is healthy, never at app startup) -> `up -d --force-recreate` ->
~60s health gate -> record the deployed SHA. On a failed gate the script exits
non-zero and CI (`cd.yml`) owns rollback: it reads the previous SHA and re-deploys
pinned to `sha-<prev>`.

## Monitoring and alerting

Prometheus scrapes `backend:8000/:8001`, `mcp:9000`, `worker:9100`, and
`node-exporter` in-network (`deployments/prometheus/prometheus.yml`). Alert rules
(`deployments/prometheus/alerts.yml`) route through Alertmanager to a single
Discord webhook with `send_resolved` (`deployments/alertmanager/alertmanager.yml`):
`ServiceDown`, `HostDiskAlmostFull`, `HighErrorRate` (critical); `SlowQueries`,
`EmbeddingJobFailureRate`, `EmbeddingJobStuck`, `AuthFailuresSpike` (warning).
Grafana ships a provisioned overview dashboard (non-gating).

Alertmanager is gated behind the `tunnels` Compose profile so local dev does not
crash-loop on a blank webhook; a live bring-up requires the webhook secret.

## Go-live checklist (HITL: requires provisioned infrastructure)

The deployment code is complete and testable without infrastructure. Before the
first real deploy, provision and supply:

1. **Domains + DNS**: confirm `floresu.app`, `api.floresu.app`, `mcp.floresu.app`
   (or your domains) and point them at the Cloudflare Tunnel. Update `.env.prod`
   (`PUBLIC_BASE_URL`, `APP_PUBLIC_URL`, `MCP_PUBLIC_URL`, `COOKIE_DOMAIN`,
   `CORS_ORIGIN`, `CF_*_HOSTNAME`) if the domains differ.
2. **VPS** (x86_64): install Docker Engine, create the `deploy` SSH user, apply
   `deployments/docker/daemon.json` (log rotation).
3. **Cloudflare**: create a named tunnel; put its UUID in `.env.prod` `CF_TUNNEL_ID`
   and its `credentials.json` in the `FLORESU_CLOUDFLARED_CREDENTIALS` GitHub secret.
4. **GHCR owner**: set `.env.prod` `GHCR_OWNER` to your GitHub org/user (lowercase).
5. **GitHub Actions secrets**: `DEPLOY_SSH_KEY`, `DEPLOY_SERVER_IP`,
   `POSTGRES_PASSWORD`, `SESSION_JWT_SECRET`, `INTERNAL_API_TOKEN`,
   `DISCORD_WEBHOOK_URL`, `GF_SECURITY_ADMIN_PASSWORD`, `OPENAI_API_KEY`,
   `FLORESU_OAUTH_PRIVATE_KEY` (RSA PEM), `FLORESU_CLOUDFLARED_CREDENTIALS`.
6. **R2** (rendering/storage, wired by the rendering ticket): provision the bucket
   and add the `R2_*` secrets when that code lands; they are not consumed yet.

Backups / point-in-time recovery are explicitly deferred (spec §12/§15);
`HostDiskAlmostFull` warns before the disk fills.
