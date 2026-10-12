# Build from the repository root: docker build -t productloop-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    PRODUCTLOOP_SKIP_DOTENV=1 \
    PRODUCTLOOP_STATE_DB=/tmp/productloop/lifecycle.sqlite3 \
    PRODUCTLOOP_BIGQUERY_ENABLED=0 \
    PRODUCTLOOP_ANALYSIS_WORKER_ENABLED=0

WORKDIR /app

# Install dependencies separately so source edits can reuse this layer.
COPY backend/requirements.lock.txt /app/backend/requirements.lock.txt
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.lock.txt \
    && python -m pip check

# Preserve relative paths used by app services (repository root is /app).
COPY backend/app/ /app/backend/app/
COPY shared/ /app/shared/
COPY data/ /app/data/
COPY bigquery/ /app/bigquery/

RUN groupadd --gid 10001 productloop \
    && useradd --uid 10001 --gid productloop --create-home productloop \
    && mkdir -p /tmp/productloop \
    && chown productloop:productloop /tmp/productloop

USER productloop
WORKDIR /app/backend
EXPOSE 8080

# exec forwards termination signals; PORT is supplied by Cloud Run.
# SQLite here is for local/private staging only, not durable cloud storage.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1"]
