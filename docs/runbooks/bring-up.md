# Runbook: one-time production bring-up

The **one-time** procedure that stands up the single production VPS and does the first live release. Everything here is done **once, by hand, by the operator**, because it depends on external infrastructure a human must supply. The repeatable deploy that runs afterward is `deploy.md`; this runbook never has to run again unless the box is rebuilt.

> The deploy machinery (`scripts/deploy.sh`, `docker-compose.tunnel.yml`, `docker-compose.deploy.yml`, CI/CD) is already delivered and tested. This runbook provisions the infra it runs against, owns the one-time host bootstrap (Docker install, daemon config, prune cron) and Docker Context registration, and performs the first deploy. The repeatable deploy afterward drives everything over a Docker Context: the box holds no `.env`, OAuth key, or rendered config.

## What the operator must supply (prerequisites)

None of these can be produced by the codebase or CI; the operator provides them:

1. **A VPS** (Ubuntu LTS) with root or sudo access, and its public IP. Size it above the sum of the Compose memory ceilings (about 5 GiB across the always-on services), so at least **8 GB RAM** with headroom for the OS and the Docker daemon. Use **x86_64**: the first-party images are amd64-only, so an ARM box would need a multi-arch `cd.yml` change.
2. **An SSH keypair** for the non-root `deploy` user (CD uses the private half).
3. **A Cloudflare account** with the `floresu.com` zone (DNS managed by Cloudflare) and `cloudflared` installed locally to create the tunnel.
4. **Production secret values:** a strong `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SESSION_JWT_SECRET` (at least 32 bytes), `INTERNAL_API_TOKEN`, a generated OAuth RSA private key, a real Discord Incoming Webhook URL, a `GF_SECURITY_ADMIN_PASSWORD`, an `OPENAI_API_KEY`, and the R2 credentials (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`) plus a bucket.
5. **Admin rights on the GitHub repo** to set the CD repo secrets.
6. **Authorization to run the live deploy.**

Never commit the secret values; they live only in GitHub Actions secrets (Phase D). Non-secret production config is committed in `.env.prod`; the box holds no `.env`, no OAuth PEM, and no tunnel credentials.

---

## Phase A: provision and harden the VPS

Run as root (or a sudo admin) on the box.

### A1. UFW baseline

The stack publishes no host ports (everything is `expose:`-only) and the tunnel is outbound-only, so the only inbound port ever needed is SSH.

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose      # verify: default deny incoming, only OpenSSH allowed
```

### A2. SSH hardening (key-only, no root)

```sh
# /etc/ssh/sshd_config.d/10-floresu.conf
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
```

```sh
sudo systemctl restart ssh   # keep your current session open until a key-only login works
```

### A3. Non-root deploy user

`scripts/deploy.sh` connects as `deploy` over an SSH Docker Context, so `deploy` needs Docker-group membership.

```sh
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /home/deploy/.ssh
echo "ssh-ed25519 AAAA... deploy@floresu" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh && sudo chmod 700 /home/deploy/.ssh && sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

### A4. fail2ban + unattended-upgrades

```sh
sudo apt-get update
sudo apt-get install -y fail2ban unattended-upgrades
sudo systemctl enable --now fail2ban                 # default sshd jail
sudo dpkg-reconfigure -plow unattended-upgrades      # enable automatic security updates
```

Verify a fresh key-only login as `deploy@<ip>` works before closing your root session.

### A5. Host bootstrap (Docker, daemon config, prune cron)

Install Docker and its runtime config once here (as root/sudo on the box). Mirror `deployments/docker/daemon.json` for log rotation.

```sh
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine + CLI
sudo usermod -aG docker deploy                        # log out/in for it to take effect

sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" }
}
JSON
sudo systemctl restart docker

# Daily image/build-cache prune:
sudo tee /etc/cron.daily/floresu-docker-prune >/dev/null <<'CRON'
#!/bin/sh
docker system prune -af --filter until=72h >> /var/log/floresu-docker-prune.log 2>&1
CRON
sudo chmod +x /etc/cron.daily/floresu-docker-prune

# The box only needs a dir for the rollback key; named volumes are created by
# Compose over the context on the first deploy (pgdata, redisdata, promdata, grafanadata).
sudo mkdir -p /opt/floresu && sudo chown deploy:deploy /opt/floresu
```

---

## Phase B: create the Cloudflare tunnel and route DNS

Run locally where `cloudflared` is installed and logged into the Cloudflare account that owns `floresu.com`.

```sh
cloudflared tunnel login                       # authorize the floresu.com zone
cloudflared tunnel create floresu              # prints the tunnel UUID and writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns floresu floresu.com
cloudflared tunnel route dns floresu api.floresu.com
cloudflared tunnel route dns floresu mcp.floresu.com
```

Record the tunnel UUID; set `CF_TUNNEL_ID` in the committed `.env.prod` (non-secret) and commit it. The credentials file `~/.cloudflared/<UUID>.json` becomes the `FLORESU_CLOUDFLARED_CREDENTIALS` GitHub secret (raw JSON, Phase D). The tunnel dials out only; no inbound port is opened.

---

## Phase C: prepare the production config and secret values

Under the Docker Context model the box stores no secrets and no `.env`.

### C1. Finalize `.env.prod` (committed, non-secret)

Set the environment-specific values and commit:

- `CF_TUNNEL_ID` = the tunnel UUID from Phase B.
- Confirm `GHCR_OWNER` matches your GitHub owner (lowercase), and the hostnames and public URLs (`PUBLIC_BASE_URL`, `APP_PUBLIC_URL`, `MCP_PUBLIC_URL`) are correct.
- Set `R2_ENDPOINT_URL` (the account endpoint, `https://<account>.r2.cloudflarestorage.com`) and `R2_BUCKET`.

`.env.prod` already sets `ENVIRONMENT=production` (fail-fast on a short `SESSION_JWT_SECRET` or missing OAuth key, `Secure` cookies), `OAUTH_PRIVATE_KEY_PATH=/run/secrets/oauth_private_key`, and `COOKIE_DOMAIN`/`CORS_ORIGIN` for the apex. `DATABASE_URL` is assembled from `POSTGRES_*` in the compose environment block, so only the password is a secret.

### C2. Generate the OAuth AS private key (a GitHub secret, not the box)

```sh
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out oauth_private.pem
```

The PEM content becomes the `FLORESU_OAUTH_PRIVATE_KEY` GitHub secret. Compose materializes it as a `0400` file at `/run/secrets/oauth_private_key` inside the backend container, so the key never lands on the box. The MCP Resource Server verifies agent tokens against the public JWKS the AS derives from this key.

### C3. Generate the remaining secret values

```sh
openssl rand -base64 48   # SESSION_JWT_SECRET  (>= 32 bytes)
openssl rand -base64 48   # INTERNAL_API_TOKEN
openssl rand -hex 32      # POSTGRES_PASSWORD   (hex -> safe inside DATABASE_URL)
openssl rand -hex 32      # REDIS_PASSWORD
openssl rand -base64 24   # GF_SECURITY_ADMIN_PASSWORD
```

Also have ready the real `DISCORD_WEBHOOK_URL`, the `OPENAI_API_KEY`, the R2 credentials, and the tunnel `credentials.json` from Phase B. All are set as GitHub secrets in Phase D; none is placed on the box.

---

## Phase D: set the GitHub repo secrets (for CD)

Set via the repo **Settings -> Secrets and variables -> Actions**, or `gh`:

```sh
gh secret set DEPLOY_SERVER_IP             --body "<vps-ip>"
gh secret set DEPLOY_SSH_KEY               < ~/.ssh/deploy_ed25519         # deploy user's PRIVATE key
gh secret set POSTGRES_PASSWORD            --body "<generated hex>"
gh secret set REDIS_PASSWORD               --body "<generated hex>"
gh secret set SESSION_JWT_SECRET           --body "<generated>"
gh secret set INTERNAL_API_TOKEN           --body "<generated>"
gh secret set DISCORD_WEBHOOK_URL          --body "<real discord webhook>"
gh secret set GF_SECURITY_ADMIN_PASSWORD   --body "<generated>"
gh secret set OPENAI_API_KEY               --body "<openai key>"
gh secret set R2_ACCESS_KEY_ID             --body "<r2 access key id>"
gh secret set R2_SECRET_ACCESS_KEY         --body "<r2 secret>"
gh secret set FLORESU_OAUTH_PRIVATE_KEY    < oauth_private.pem             # RAW PEM content
gh secret set FLORESU_CLOUDFLARED_CREDENTIALS < ~/.cloudflared/<UUID>.json # RAW credentials.json
```

`GITHUB_TOKEN` is not set manually: it is the built-in Actions token. Ensure Actions can write packages (repo/org **Settings -> Actions -> Workflow permissions**), since `cd.yml` requests `packages: write` and logs into GHCR with it.

---

## Phase E: first live deploy

The simplest path: once the repo secrets (Phase D) are set and `.env.prod` is committed (C1), push to `main` (or run the CD **workflow_dispatch**). CD registers the Docker Context, exports the config/secrets, and runs `scripts/deploy.sh`.

To deploy manually from a local checkout instead, register the context and export the same environment yourself (mirroring `cd.yml`):

```sh
docker context create floresu --docker "host=ssh://deploy@<vps-ip>"

set -a
source .env.prod
FLORESU_PROMETHEUS_CONFIG="$(cat deployments/prometheus/prometheus.yml)"
FLORESU_PROMETHEUS_ALERTS="$(cat deployments/prometheus/alerts.yml)"
FLORESU_CLOUDFLARED_INGRESS="$(envsubst '$CF_TUNNEL_ID $CF_APP_HOSTNAME $CF_API_HOSTNAME $CF_MCP_HOSTNAME' < deployments/cloudflare/config.yml)"
FLORESU_ALERTMANAGER_CONFIG="$(DISCORD_WEBHOOK_URL='<webhook>' envsubst '$DISCORD_WEBHOOK_URL' < deployments/alertmanager/alertmanager.yml)"
FLORESU_OAUTH_PRIVATE_KEY="$(cat oauth_private.pem)"
FLORESU_CLOUDFLARED_CREDENTIALS="$(cat ~/.cloudflared/<UUID>.json)"
POSTGRES_PASSWORD='<hex>'; REDIS_PASSWORD='<hex>'; SESSION_JWT_SECRET='<gen>'; INTERNAL_API_TOKEN='<gen>'
GF_SECURITY_ADMIN_PASSWORD='<gen>'; OPENAI_API_KEY='<key>'
R2_ACCESS_KEY_ID='<id>'; R2_SECRET_ACCESS_KEY='<secret>'
set +a

DRY_RUN=1 DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <vps-ip>   # preview
DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <vps-ip>             # real
```

The script asserts every required config/secret env var is set, pulls, runs migrations pre-traffic (`alembic upgrade head`; aborts on failure), starts the stack under the `tunnels` profile, health-gates every service (about 60 seconds), then records `/opt/floresu/.deployed-sha` on success. On a failed gate it exits non-zero; CD (not the script) owns the rollback re-run.

---

## Phase F: verify the release

### F1. All services healthy, zero open inbound ports

```sh
docker --context floresu compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml --profile tunnels ps   # every service: healthy
ssh deploy@<vps-ip> 'sudo ufw status verbose'        # only OpenSSH inbound; the tunnel is outbound-only
```

`FLORESU_ALERTMANAGER_CONFIG` is rendered in CI from `DISCORD_WEBHOOK_URL`; a blank webhook makes Alertmanager exit on config load and the health gate fails, so a green deploy means the webhook rendered.

### F2. All three hostnames reachable through the tunnel

```sh
curl -sI https://floresu.com | head -1                                     # SPA (frontend)
curl -sI https://api.floresu.com/.well-known/oauth-authorization-server    # AS metadata (backend :8000)
curl -sI https://mcp.floresu.com/.well-known/oauth-protected-resource      # PRM (mcp :9000)
```

Confirm the boundary holds: the internal app is never tunnel-routed, and `mcp.floresu.com` serves only the PRM document and the `/mcp` transport (any other path returns 404 at ingress):

```sh
curl -sI https://mcp.floresu.com/metrics    # expect 404 (never tunnel-exposed)
curl -sI https://api.floresu.com/metrics    # expect 404 (edge-blocked observability path)
```

### F3. Live end-to-end smoke

1. **Register** a human user in the SPA (`https://floresu.com`).
2. **Agent OAuth connect:** point MCP Inspector at `https://mcp.floresu.com`, walk the 401 -> PRM -> AS `/oauth/authorize` (SPA consent) -> `/oauth/token` flow, and confirm the agent gets an `aud=mcp` access token.
3. **Record and search:** create a worklog entry via the agent tools, then run `search_experience` to confirm the item is retrievable.
4. **Assemble and export:** build a resume, then export it and confirm the PDF persists to R2.

### F4. Synthetic alert reaches Discord

```sh
docker --context floresu compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml --profile tunnels stop mcp
# wait ~1-2m -> ServiceDown fires -> FIRING message in Discord
docker --context floresu compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml --profile tunnels start mcp
# -> RESOLVED message (send_resolved: true)
```

---

## Done

The box is provisioned, hardened, and serving. From here, every change ships through the repeatable deploy in `deploy.md` (CD on merge to `main`, or a manual `./scripts/deploy.sh <ip>`).

## Cross-references

- The repeatable deploy: `deploy.md`.
- Migration discipline: `migration.md`.
- Rollback: `rollback.md`.
- The CI/CD pipeline and secret list: `docs/ci-cd.md`.
