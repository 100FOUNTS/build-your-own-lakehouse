# Image of the pipeline and the API. It carries the CODE, not the data: data comes in through a volume (see compose.yaml).
FROM python:3.12-slim

# uv with a pinned version: the same image today and six months from now.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

WORKDIR /app

# 1) First ONLY the dependency files. Docker caches every step: as long as pyproject.toml and uv.lock do not change,
#    this layer (the slow one: it installs dagster, dbt, scikit-learn...) is reused even if you change your code.
#    --locked: installs exactly what uv.lock says and fails if the lock is outdated. --no-dev: no pytest or ruff.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# 2) Then the code. This layer changes often, but it is cheap.
COPY src ./src
COPY dbt ./dbt

# Use the environment uv created, and import the code without installing it (as the Makefile does).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/tmp/dagster_home

# Do not run as root: if something fails or someone gets in through the API, they have no admin permissions in the container.
# /app/data is where the volume is mounted; it must be writable (bronze, the warehouse and the model are created there).
RUN useradd --create-home lakehouse \
    && mkdir -p /app/data /tmp/dagster_home \
    && chown -R lakehouse /app/data /app/dbt /tmp/dagster_home
USER lakehouse

EXPOSE 8000

# By default it serves the API. The pipeline uses the same image with another command (see compose.yaml).
CMD ["uvicorn", "lakehouse.api:app", "--host", "0.0.0.0", "--port", "8000"]
