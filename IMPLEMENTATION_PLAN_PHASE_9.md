# Phase 9 — Docker Compose + README

**Dependencies:** Phase 7 (Streamlit app to containerize)
**Agent:** `general-purpose`
**Estimated files:** 4

This phase containerizes the system and provides complete setup/run instructions.

---

## 9.1 Dockerfile

### `Dockerfile` (NEW)

**Purpose:** Multi-stage Dockerfile for the CDDE application.

**Structure:**

```dockerfile
# Stage 1: Build — install dependencies
FROM python:3.13-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY specs/ specs/
COPY data/ data/
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8501
CMD ["streamlit", "run", "src/ui/app.py", "--server.port=8501", "--server.headless=true"]
```

**Constraints:**
- Use `python:3.13-slim` (not `alpine` — pandas/numpy wheels need glibc)
- Multi-stage build to keep image small
- Use `uv sync --frozen` for reproducible installs
- Do NOT copy `.env`, `tests/`, `tools/`, `*.md` into the image
- EXPOSE 8501 (Streamlit default port)
- Set `--server.headless=true` for Docker (no browser auto-open)

---

## 9.2 Docker Compose

### `docker-compose.yml` (NEW)

**Purpose:** Single-command startup for the full system.

**Services:**

```yaml
version: "3.9"

services:
  cdde:
    build: .
    ports:
      - "8501:8501"
    volumes:
      - ./output:/app/output
      - ./data:/app/data:ro
    environment:
      - LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:8650/v1}
      - LLM_API_KEY=${LLM_API_KEY:-not-needed-for-mailbox}
      - DATABASE_URL=sqlite+aiosqlite:///cdde.db
    restart: unless-stopped
```

**Constraints:**
- Single service for prototype (AgentLens runs on host, not in Docker)
- `host.docker.internal` for accessing host-side AgentLens proxy
- Mount `output/` for audit trail export
- Mount `data/` read-only for CDISC datasets
- Environment variables with defaults — override via `.env` file
- SQLite database file persists inside the container (acceptable for prototype)

### `.env.example` (NEW)

```env
# LLM Configuration
LLM_BASE_URL=http://host.docker.internal:8650/v1
LLM_API_KEY=not-needed-for-mailbox
LLM_MODEL=cdde-agent

# Database
DATABASE_URL=sqlite+aiosqlite:///cdde.db
```

---

## 9.3 .dockerignore

### `.dockerignore` (NEW)

```
.venv/
.git/
.github/
.claude/
__pycache__/
*.pyc
.coverage
.pytest_cache/
.ruff_cache/
output/
tests/
tools/
prototypes/
*.md
!README.md
.env
KEYS.md
```

---

## 9.4 README Update

### `README.md` (NEW — or major update if exists)

**Purpose:** Complete setup and run instructions — THE first thing evaluators see.

**Sections:**

1. **Title + Badge** — CDDE: Clinical Data Derivation Engine
2. **Overview** — One paragraph: what it does, why, key differentiators
3. **Quick Start**
   ```bash
   # Clone + install
   git clone https://github.com/matt-grain/pharma-derive.git
   cd pharma-derive
   uv sync

   # Run tests
   uv run pytest

   # Start Streamlit UI (requires AgentLens proxy on localhost:8650)
   uv run streamlit run src/ui/app.py

   # Or with Docker
   docker compose up --build
   ```
4. **Architecture** — Brief + link to `docs/design.md` and `ARCHITECTURE.md`
5. **Project Structure** — Tree view with one-line descriptions
6. **Configuration** — Environment variables table
7. **Development**
   ```bash
   uv sync --all-extras    # Install dev dependencies
   uv run pytest           # Run tests
   uv run ruff check .     # Lint
   uv run pyright .        # Type check
   ```
8. **Data** — CDISC Pilot Study description + how to download
9. **Deliverables** — Links to design doc, presentation, this README

**Constraints:**
- Keep under 150 lines
- No badges/shields that add visual noise without value
- Quick start must work in ≤5 commands
- Mention Python 3.13+ requirement
- Link to `docs/design.md` for the full design document
