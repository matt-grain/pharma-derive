# pharma-derive frontend — Vite + React SPA served by nginx.
#
# Multi-stage build:
#   Stage 1 (builder): node 22-alpine + pnpm, installs deps + runs vite build.
#   Stage 2 (runtime): nginx alpine, serves the static dist/ on port 3000.
#
# Why pnpm not npm: the repo uses pnpm as the primary package manager
# (pnpm-lock.yaml is authoritative). An npm ci attempt would fail because
# package-lock.json is not kept in sync with pnpm-lock.yaml.
#
# Build:
#     docker build -t pharma-derive-frontend:latest ./frontend
#
# Run in compose:
#     services.frontend.build: ./frontend

# Stage 1: builder
FROM node:22-alpine AS builder
WORKDIR /app

# Enable corepack so pnpm is available without a separate install step.
# Corepack ships with node 22 and pins pnpm to the version declared in
# package.json's packageManager field (if set) or the latest stable.
RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

# Stage 2: runtime — nginx alpine serving the static SPA on port 3000.
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
