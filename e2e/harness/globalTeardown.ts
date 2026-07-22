import { tearDownInfra } from "./infra";

/**
 * Playwright global teardown: bring down the E2E infrastructure after the suite.
 * Set `E2E_KEEP_STACK=1` to leave Postgres, Redis, and MinIO running for
 * debugging a failed run.
 */
async function globalTeardown(): Promise<void> {
  if (process.env.E2E_KEEP_STACK === "1") return;
  tearDownInfra();
}

export default globalTeardown;
