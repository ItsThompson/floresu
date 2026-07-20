import createClient, { type Client } from "openapi-fetch";

import type { paths } from "./schema";

/**
 * Typed API client.
 *
 * `openapi-fetch` turns the generated OpenAPI `paths` into one typed call per
 * endpoint over a single generic fetch (`client.GET("/me", ...)`), so
 * request/response shapes come straight from `npm run codegen` output and are
 * never hand-written. Each call is independently mockable by URL (see
 * `src/mocks`). The base URL is injected rather than read here so this stays
 * testable.
 */
export const createApiClient = (baseUrl: string): Client<paths> => createClient<paths>({ baseUrl });

export type ApiClient = Client<paths>;

/**
 * The session-aware client (credentials + 401→refresh→retry middleware), built
 * by `createSessionClient`. Structurally identical to `ApiClient`; the distinct
 * alias lets the auth hooks read as binding the credentialed client.
 */
export type SessionClient = Client<paths>;
