/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL. Empty (same-origin) in dev; the API subdomain in prod. */
  readonly VITE_API_BASE_URL?: string;
  /** When "true", start the MSW mock worker before rendering (`npm run dev:mock`). */
  readonly VITE_MOCK_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
