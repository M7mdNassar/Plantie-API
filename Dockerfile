# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# System deps for PyMuPDF (ingestion script) and building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image at build time, into a path under
# /app (NOT /tmp — see note in src/config.py: many hosts, Render included,
# mount a fresh empty tmpfs over /tmp when the container actually starts,
# which silently erases anything written to /tmp during the build).
# Must match FASTEMBED_MODEL / FASTEMBED_CACHE_DIR in your .env — update
# this line too if you ever change either setting.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/app/.fastembed_cache')"

COPY . .

RUN mkdir -p /app/pdfs \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENV WEB_CONCURRENCY=1
CMD ["sh", "-c", "gunicorn src.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --bind 0.0.0.0:8000 --timeout 120 --access-logfile - --error-logfile -"]