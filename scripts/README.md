# scripts

Deploy and operational scripts.

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Box-less Docker Context deploy: assert secrets, pull, pre-traffic Alembic migration, `up -d --force-recreate`, ~60s health gate, record the deployed SHA. Rollback is CI-owned (`cd.yml`). See the header for usage and env. |
| `tests/deploy_test.sh` | Pure-bash test harness for `deploy.sh` (helpers, preflight, dry-run phase plan, overlay shape, rollback contract, ingress allow-list). Runs without a daemon or VPS: `just test-deploy`. |
| `serve-backend.sh` | Runs both backend ASGI apps in one container/process group; exits if either app dies. The backend image `CMD`. |
| `healthcheck-backend.sh` | Probes both backend apps' liveness. |

The box-less deploy runs the Compose CLI in CI against the VPS Docker engine over
an SSH Docker Context: no `.env`, rendered config, or secret file lands on the
box. See `deployments/README.md` for the topology and the go-live checklist.
