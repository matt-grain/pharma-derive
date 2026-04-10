# Stage 1: Build
FROM python:3.13-slim AS builder
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies
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

EXPOSE 8501

CMD ["streamlit", "run", "src/ui/app.py", "--server.port=8501", "--server.headless=true", "--server.address=0.0.0.0"]
