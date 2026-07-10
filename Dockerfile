FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --compile-bytecode

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --compile-bytecode

EXPOSE 8000

CMD ["uv", "run", "gunicorn", "app.main:app", \
     "--workers", "3", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000"]
