/**
 * Single source of truth for the E2E stack's ports, URLs, and credentials.
 *
 * The infrastructure (Postgres, Redis, MinIO) runs from docker-compose.e2e.yml
 * on non-default host ports so the suite never collides with a local dev stack.
 * The app processes (both ASGI apps, the frontend, the fake embedding provider)
 * run as host processes launched by Playwright's `webServer`, so this module also
 * builds the environment those processes inherit.
 */

export const PORTS = {
  postgres: 5433,
  redis: 6380,
  minioApi: 9002,
  fakeEmbeddings: 9010,
  backendExternal: 8000,
  backendInternal: 8001,
  frontend: 5173,
} as const;

export const EXTERNAL_API_URL = `http://localhost:${PORTS.backendExternal}`;
export const INTERNAL_API_URL = `http://localhost:${PORTS.backendInternal}`;
export const FRONTEND_URL = `http://localhost:${PORTS.frontend}`;
export const MCP_PUBLIC_URL = "http://localhost:9000";

export const DATABASE_URL = `postgresql+asyncpg://floresu:floresu@localhost:${PORTS.postgres}/floresu`;
export const REDIS_URL = `redis://localhost:${PORTS.redis}/0`;

/** MinIO stands in for Cloudflare R2 (both speak the S3 API). */
export const OBJECT_STORE = {
  endpointUrl: `http://localhost:${PORTS.minioApi}`,
  accessKeyId: "minioadmin",
  secretAccessKey: "minioadmin",
  bucket: "floresu-e2e",
} as const;

/** The shared secret gating the internal trust boundary (:8001). */
export const INTERNAL_API_TOKEN = "e2e-internal-api-token";

/** HS256 session secret. >= 32 bytes so a real signed session resolves. */
export const SESSION_JWT_SECRET = "e2e-session-secret-0123456789-abcdef-ghij";

/**
 * Environment shared by both backend ASGI apps and any host process that talks to
 * the same infrastructure. `ENVIRONMENT=development` keeps session cookies
 * non-Secure and host-only so they flow over plain-HTTP localhost.
 */
export const backendEnv: Record<string, string> = {
  ENVIRONMENT: "development",
  LOG_LEVEL: "warning",
  DATABASE_URL,
  REDIS_URL,
  INTERNAL_API_TOKEN,
  SESSION_JWT_SECRET,
  PUBLIC_BASE_URL: EXTERNAL_API_URL,
  APP_PUBLIC_URL: FRONTEND_URL,
  MCP_PUBLIC_URL,
  // Fake embedding provider: an OpenAI-compatible local server, so the query
  // embed path succeeds offline and no run ever calls OpenAI.
  OPENAI_API_KEY: "e2e-fake-key",
  OPENAI_BASE_URL: `http://localhost:${PORTS.fakeEmbeddings}`,
  // MinIO object store (faked R2). botocore uses path-style addressing for a
  // localhost endpoint, so the minted presigned URL is reachable on the host.
  R2_ENDPOINT_URL: OBJECT_STORE.endpointUrl,
  R2_ACCESS_KEY_ID: OBJECT_STORE.accessKeyId,
  R2_SECRET_ACCESS_KEY: OBJECT_STORE.secretAccessKey,
  R2_BUCKET: OBJECT_STORE.bucket,
};
