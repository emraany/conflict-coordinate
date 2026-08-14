# One image, two roles: the API service runs the default CMD, the scheduled
# ingest service overrides it with `python -m app.ingestion.runner`. They
# share every dependency, so a second image would only add drift.
FROM python:3.12-slim

# libexpat/libstdc++ come in via the base image; spaCy's wheels are manylinux
# so no compiler is needed. curl is here for the container healthcheck only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    # Without this the download cache (~900MB, mostly the spaCy model wheel)
    # is baked into the layer alongside the installed copy of the same files.
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so edits to app code don't re-resolve or re-download
# en_core_web_lg (~600MB) on every build.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
