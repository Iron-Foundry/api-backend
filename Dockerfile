FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --compile-bytecode

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --compile-bytecode

# Build provenance for GET /version. Declared after the dependency layers so a
# new commit sha only invalidates this final layer, not the uv sync cache.
ARG GIT_SHA=""
ARG BUILD_TIME=""
ENV GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

EXPOSE 8000

# Apply pending Alembic migrations before booting so the schema always matches
# the deployed code. The entrypoint runs once per container, before gunicorn
# forks its workers, so migrations run a single time. exec keeps gunicorn as the
# foreground process for correct signal handling.
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run gunicorn app.main:app --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"]
