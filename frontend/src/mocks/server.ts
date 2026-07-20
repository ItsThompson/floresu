import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/**
 * Node MSW server for unit tests. The default handlers cover the happy path;
 * individual tests override per-endpoint behavior with `server.use(...)` to
 * exercise error and anonymous states. Lifecycle is wired in `src/test/setup.ts`.
 */
export const server = setupServer(...handlers);
