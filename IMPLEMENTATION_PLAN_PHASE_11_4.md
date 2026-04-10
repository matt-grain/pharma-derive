# Phase 11.4 — Docker Compose + nginx

**Depends on:** Phase 11.1 (backend), Phase 11.3 (frontend)
**Agent:** `general-purpose`
**Goal:** Multi-container Docker Compose with nginx reverse proxy, sticky sessions, and separate frontend/backend containers. Replace the existing single-container Streamlit setup.

---

## 1. Backend Dockerfile — `Dockerfile` (MODIFY)

**Change:** Replace the Streamlit CMD with uvicorn. Keep the multi-stage build.

```dockerfile
# Stage 1: Build
FROM python:3.13-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: Runtime
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY specs/ specs/
COPY data/ data/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 2. Frontend Dockerfile — `frontend/Dockerfile` (NEW)

**Purpose:** Multi-stage build: npm build → nginx serve static files.

```dockerfile
# Stage 1: Build
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA fallback: all routes → index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

---

## 3. Frontend nginx config — `frontend/nginx.conf` (NEW)

**Purpose:** Serve the SPA with client-side routing fallback.

```nginx
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 4. Reverse proxy nginx — `nginx/nginx.conf` (NEW)

**Purpose:** Top-level reverse proxy: routes `/api/` and `/mcp/` to backend, everything else to frontend. Sticky sessions via `ip_hash`.

```nginx
upstream backend {
    ip_hash;  # sticky sessions — workflow state is in-memory on one container
    server backend:8000;
}

upstream frontend {
    server frontend:3000;
}

server {
    listen 80;

    # API and MCP routes → backend
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /mcp/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
        # SSE support for MCP
    }

    location /health {
        proxy_pass http://backend;
    }

    # Everything else → frontend SPA
    location / {
        proxy_pass http://frontend;
    }
}
```

---

## 5. Docker Compose — `docker-compose.yml` (REPLACE)

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - backend
      - frontend
    restart: unless-stopped

  backend:
    build: .
    expose:
      - "8000"
    volumes:
      - ./output:/app/output
      - ./data:/app/data:ro
    environment:
      - LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:8650/v1}
      - LLM_API_KEY=${LLM_API_KEY:-not-needed-for-mailbox}
      - DATABASE_URL=${DATABASE_URL:-sqlite+aiosqlite:///cdde.db}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  frontend:
    build: ./frontend
    expose:
      - "3000"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
```

**Notes:**
- `nginx` on port 80 (host) — single entry point
- `backend` and `frontend` only expose ports internally (no host binding)
- Backend healthcheck so frontend waits for API availability
- PostgreSQL is NOT included — for homework scope, SQLite is sufficient. Production would add a `db` service.

---

## 6. .dockerignore updates — `.dockerignore` (MODIFY) and `frontend/.dockerignore` (NEW)

**Root `.dockerignore`:**
```
.venv/
.git/
__pycache__/
*.pyc
.coverage
cdde.db
output/
traces/
frontend/
.claude/
node_modules/
```

**`frontend/.dockerignore`:**
```
node_modules/
dist/
.env
```

---

## Verification

1. `docker compose build` — both images build successfully
2. `docker compose up -d` — all 3 services start
3. `curl http://localhost/health` — returns `{"status": "ok"}`
4. `curl http://localhost/api/v1/specs/` — returns spec list
5. Open `http://localhost` — React SPA loads
6. `docker compose down` — clean shutdown
