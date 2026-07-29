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

# Bake the embedding model into the image so the container never has to
# talk to Hugging Face at runtime. Must match FASTEMBED_MODEL in your .env —
# update this line too if you ever change that setting.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"
ENV HF_HUB_OFFLINE=1

COPY . .

RUN mkdir -p /app/pdfs \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Each gunicorn worker is a SEPARATE OS PROCESS — it runs its own copy of
# `lifespan`, so it loads its own full copy of the embedding model. N workers
# = N copies of the model in memory, all at once. On a 512MB instance
# (Render's free/starter tier), even 2 workers can OOM before ever binding
# the port. Default to 1 worker; only raise WEB_CONCURRENCY if your plan
# actually has the RAM for it (rule of thumb: model + SDK overhead is
# roughly 250-400MB per worker — check your plan's memory before raising this).
ENV WEB_CONCURRENCY=1
CMD ["sh", "-c", "gunicorn src.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --bind 0.0.0.0:8000 --timeout 120 --access-logfile - --error-logfile -"]