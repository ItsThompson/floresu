import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";

// One MSW server for the whole suite. `onUnhandledRequest: "error"` surfaces any
// call the handlers do not cover, so a test cannot silently hit the network.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
