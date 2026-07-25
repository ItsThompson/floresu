# Runbook: deploy

Docker Context deploy of the whole stack to the single VPS. The Compose CLI runs in CI (or an operator checkout); the engine runs on the VPS, reached over a Docker Context (`ssh://deploy@<ip>`, context name `floresu`). All config and secret content is sourced CLI-side and transmitted to the daemon, so the box holds no `.env`, OAuth key, or rendered config. Driven by `scripts/deploy.sh`; run automatically by CD on merge to `main`, or manually.

## What a deploy does

CD registers the context, exports the config/secret env (committed `.env.prod` + files rendered in the runner + GitHub secrets), and runs `scripts/deploy.sh <server-ip>`, which:

1. **Preflight:** assert every required config/secret env var is set (fail fast). See the list below.
2. **Pull:** `docker --context floresu compose ... pull`.
3. **Migrations (pre-traffic):** start postgres, wait healthy, then `... run --rm backend alembic upgrade head`. Aborts the deploy on failure. See `migration.md`.
4. **Start:** `docker --context floresu compose --profile tunnels up -d --force-recreate`. Force-recreate re-applies the current environment-sourced config and secrets to every service, since `up -d` alone does not recreate a service when only that content changed.
5. **Health gate:** poll `docker --context floresu compose ps` health across all services (about 60 seconds).
6. **Record on success:** the one remaining `ssh` line writes the deployed SHA to `/opt/floresu/.deployed-sha` (the rollback key). On a failed gate the script exits non-zero and CD owns the rollback (below); the script never re-deploys itself.

The deploy layers three Compose files under the `tunnels` profile: `docker-compose.yml` (base), `docker-compose.tunnel.yml` (cloudflared, the OAuth key secret, the alertmanager config secret, the pinned app-net subnet), and `docker-compose.deploy.yml` (backend/mcp/worker prod config and app secrets, the Redis password, Grafana admin password). Host bootstrap is a one-time bring-up concern (`bring-up.md`), not part of a deploy. Not zero-downtime: there is a brief per-deploy gap while containers recreate, accepted at this scale.

### Required config/secret env vars

`deploy.sh` asserts all of these before any compose call (the migration `run` materializes configs and secrets exactly like `up`, so every one must be set first):

`FLORESU_OAUTH_PRIVATE_KEY`, `FLORESU_CLOUDFLARED_CREDENTIALS`, `FLORESU_ALERTMANAGER_CONFIG`, `FLORESU_CLOUDFLARED_INGRESS`, `FLORESU_PROMETHEUS_CONFIG`, `FLORESU_PROMETHEUS_ALERTS`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SESSION_JWT_SECRET`, `INTERNAL_API_TOKEN`, `GF_SECURITY_ADMIN_PASSWORD`, `R2_ENDPOINT_URL`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.

## Triggering a deploy

- **Automatic:** CD (`cd.yml`) builds/pushes `:latest` + `:sha-<sha>` images, then registers the context, exports the config/secret env, and runs `./scripts/deploy.sh <ip>` with `DEPLOY_SHA` set. A static concurrency group at the CD layer serializes deploys so a manual dispatch and a push-deploy cannot race onto the box.
- **Manual:** register the context and export the config/secret env first (see `bring-up.md` Phase E), then `DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <server-ip>`. Set `DEPLOY_SHA` to the SHA whose images CD pushed.
- **Preview only:** `just deploy-dry-run <server-ip>` (or `DRY_RUN=1 ./scripts/deploy.sh <ip>`) prints the compose/ssh plan without touching a server. The preflight still runs, so the required env vars must be set (even dummy values) to reach the plan.

## Cloudflare tunnel ingress

The tunnel is the only ingress (zero inbound ports). CI renders `deployments/cloudflare/config.yml` via `envsubst` (substituting `CF_TUNNEL_ID` + the three `CF_*_HOSTNAME` vars from `.env.prod`) into the `FLORESU_CLOUDFLARED_INGRESS` env var, and `docker-compose.tunnel.yml` delivers it as an environment-sourced Compose config mounted at `/etc/cloudflared/config.yml` (no file on the box). Three ingress rules: `floresu.com` -> frontend, `api.floresu.com` -> backend `:8000`, `mcp.floresu.com` -> mcp `:9000`. The MCP host publicly exposes only the PRM discovery document and the `/mcp` transport; `/metrics`, `/healthz`, and `/readyz` are refused at the edge (scraped in-network only). The named-tunnel credentials are delivered the same way (a GitHub secret transmitted as an environment-sourced Compose secret).

## Secrets and config

**Committed non-secret config:** `.env.prod` (sourced in the runner). Its keys and meanings mirror `.env.example`'s production values.

**How app config reaches the containers:** the deploy overlay (`docker-compose.deploy.yml`) loads `.env.prod` into backend/mcp/worker via `env_file` (read CLI-side and transmitted over the context: no file on the box) and passes the app secrets (`SESSION_JWT_SECRET`, `INTERNAL_API_TOKEN`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `REDIS_PASSWORD`, and the optional `OPENAI_API_KEY`) through from the runner env. `environment:` overrides `env_file`, so a stray dev `.env` cannot leak into a deploy. The OAuth AS private key is materialized as a `0400` file at `/run/secrets/oauth_private_key` (the path `.env.prod`'s `OAUTH_PRIVATE_KEY_PATH` points at).

**GitHub repo secrets** (CI/CD only): see `docs/ci-cd.md` for the full list. CD exports these into the deploy step's environment; Compose transmits them to the daemon as environment-sourced configs and secrets. Nothing is written to the box.

## Rollback (CI-owned)

On a failed health gate the deploy exits non-zero and CD runs a conditional rollback step: it reads the previous `/opt/floresu/.deployed-sha` (via `./scripts/deploy.sh read-deployed-sha <ip>`), checks that SHA out in the runner, re-exports the env from that checkout, and re-runs the deploy once with `FLORESU_IMAGE_TAG=sha-<prev>`. Because the checkout moves to the previous SHA, this restores the previous **images AND config**. If no previous `.deployed-sha` exists (the first deploy), `read-deployed-sha` refuses and the workflow fails: there is nothing to roll back to. See `rollback.md`.

**Forward-only migrations (caveat):** a release carrying a schema migration can block re-deploying the previous image against the already-migrated DB. Migrations are forward-only; down-migrations are manual and out of scope. See `migration.md`.

## First-time bring-up

One-time VPS bring-up (UFW + SSH hardening, non-root deploy user, Docker install, creating the tunnel + routing DNS, registering the Docker Context, generating the OAuth key and setting the CD repo secrets) is a separate, human-run procedure: see `bring-up.md`. This runbook covers the repeatable deploy that runs afterward.

## Cross-references

- One-time bring-up: `bring-up.md`.
- Migration discipline: `migration.md`.
- Rollback: `rollback.md`.
- The CI/CD pipeline view and the secret list: `docs/ci-cd.md`.
