import { createBrowserRouter, RouterProvider } from "react-router";

import { ApiClientProvider } from "@/api";
import { AuthProvider } from "@/auth";

import { appRoutes } from "./routes";

const router = createBrowserRouter(appRoutes);

/**
 * Same-origin by default (the Vite dev proxy forwards /auth and /me to the
 * backend, and MSW intercepts in the mock harness); a deployment points at the
 * API subdomain via `VITE_API_BASE_URL`. Read once at the app root: the base
 * never changes at runtime, and the shared clients bind to it here.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export function App() {
  return (
    <ApiClientProvider baseUrl={API_BASE_URL}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ApiClientProvider>
  );
}
