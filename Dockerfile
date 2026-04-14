# pharma-derive backend — FastAPI + FastMCP + PydanticAI.
#
# Multi-stage build: Python 3.13-slim + uv for dependency management.
# Runtime stage receives configuration via compose environment variables
# (LLM_BASE_URL, LLM_API_KEY, DATABASE_URL) — NO .env is baked into the image
# so the same image can run in local dev, team, and enterprise tiers unchanged.
#
# Build:
#     docker build -t pharma-derive-backend:latest .
#
# Run standalone (sqlite, local mailbox):
#     docker run --rm -p 8000:8000 \
#         -e DATABASE_URL=sqlite+aiosqlite:///cdde.db \
#         -e LLM_BASE_URL=http://host.docker.internal:8650/v1 \
#         -v $(pwd)/output:/app/output \
#         -v $(pwd)/data:/app/data:ro \
#         pharma-derive-backend:latest
#
# Run in compose:
#     services.backend.build: .

# Stage 1: builder
FROM python:3.13-slim AS builder
WORKDIR /app

# Install uv (Astral's package manager).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies only — maximise Docker layer cache hits on unchanged uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: runtime
FROM python:3.13-slim
WORKDIR /app

# Bring in the pre-built virtualenv from stage 1.
COPY --from=builder /app/.venv /app/.venv

# Copy source, transformation specs, and YAML configs. Runtime data (data/)
# and outputs (output/) are mounted as volumes at compose time — they are NOT
# baked into the image.
COPY src/ src/
COPY specs/ specs/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
