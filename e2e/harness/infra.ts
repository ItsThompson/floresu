import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { backendEnv, OBJECT_STORE } from "./env";

const here = dirname(fileURLToPath(import.meta.url));
export const E2E_DIR = resolve(here, "..");
export const REPO_ROOT = resolve(E2E_DIR, "..");
export const BACKEND_DIR = resolve(REPO_ROOT, "backend");
const COMPOSE_FILE = resolve(E2E_DIR, "docker-compose.e2e.yml");

function run(command: string, args: string[], cwd: string, env?: Record<string, string>): void {
  execFileSync(command, args, { cwd, stdio: "inherit", env: { ...process.env, ...env } });
}

const ENSURE_BUCKET_PY = [
  "import asyncio, aioboto3, botocore",
  "async def main():",
  "    session = aioboto3.Session()",
  `    async with session.client('s3', endpoint_url='${OBJECT_STORE.endpointUrl}',`,
  `        aws_access_key_id='${OBJECT_STORE.accessKeyId}', aws_secret_access_key='${OBJECT_STORE.secretAccessKey}',`,
  "        region_name='auto') as client:",
  "        try:",
  `            await client.create_bucket(Bucket='${OBJECT_STORE.bucket}')`,
  "        except botocore.exceptions.ClientError as exc:",
  "            if exc.response['Error']['Code'] not in ('BucketAlreadyOwnedByYou', 'BucketAlreadyExists'): raise",
  "asyncio.run(main())",
].join("\n");

/**
 * Bring up the E2E infrastructure (Postgres, Redis, MinIO), migrate the database
 * to head, and create the object-store bucket. Idempotent. Runs before Playwright
 * starts the app `webServer` processes, so the backend never boots ahead of its
 * database.
 */
export function bringUpInfra(): void {
  run("docker", ["compose", "-f", COMPOSE_FILE, "up", "-d", "--wait"], E2E_DIR);
  run("uv", ["run", "alembic", "upgrade", "head"], BACKEND_DIR, {
    DATABASE_URL: backendEnv.DATABASE_URL,
  });
  run("uv", ["run", "python", "-c", ENSURE_BUCKET_PY], BACKEND_DIR);
}

/** Tear down the E2E infrastructure and its volumes. */
export function tearDownInfra(): void {
  run("docker", ["compose", "-f", COMPOSE_FILE, "down", "-v"], E2E_DIR);
}

// CLI entry: `tsx harness/infra.ts up|down`.
const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  const action = process.argv[2];
  if (action === "down") tearDownInfra();
  else bringUpInfra();
}
