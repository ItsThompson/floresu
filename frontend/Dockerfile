# syntax=docker/dockerfile:1

# =============================================================================
# Floresu frontend image: build the Vite SPA, then serve the static bundle from
# nginx with a history-API fallback. Two stages so node and the build toolchain
# never ship in the runtime image.
#
# HOST-SPLIT prod: the SPA is served from floresu.com and calls the API
# cross-origin at api.floresu.com. VITE_API_BASE_URL and VITE_MCP_URL are baked
# into the bundle at build time (the SPA reads import.meta.env.*); cd.yml sources
# them from .env.prod for the production build. Empty means same-origin (local).
# =============================================================================

FROM node:22-alpine AS builder
WORKDIR /app

# Install deps first (cached across source-only changes).
COPY package.json package-lock.json ./
RUN npm ci

# Build. VITE_API_BASE_URL (the API origin, api.floresu.com in prod; empty ->
# same-origin) and VITE_MCP_URL (the MCP endpoint shown on the onboarding
# connect-agent step) are baked into the bundle here from compose build.args.
COPY . ./
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_MCP_URL=""
ENV VITE_MCP_URL=$VITE_MCP_URL
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the stock server block with the SPA config (static + history fallback).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Container healthcheck: nginx serves /healthz for the in-container probe. The
# tunnel edge allow-list 404s /healthz on the app host, so it is not public.
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:80/healthz"]

# nginx:alpine's default CMD runs nginx in the foreground.
