# ============================================================================
# Backend Dockerfile - FastAPI + ML Orchestrator
# Context: ModelPipeline/ (parent directory of finrag_docker_loc_tg1)
# Requirements: finrag_ml_tg1/environments/requirements_app_backend.txt
#
# Multi-stage: dependencies are resolved into a throwaway venv in the builder
# stage, then only that venv is copied into a clean runtime stage. Neither pip,
# uv, nor any build toolchain survives into the final image.
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1 - builder: resolve dependencies into /opt/venv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv is the resolver/installer; it stays in this stage only.
RUN pip install --no-cache-dir uv

# Copy only the requirements file so this layer caches independently of code.
COPY finrag_ml_tg1/environments/requirements_app_backend.txt /tmp/requirements.txt

# UV_LINK_MODE=copy: hardlinks from the uv cache do not survive a stage copy.
ENV UV_LINK_MODE=copy
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 - runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Bring in the resolved dependencies only.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Unprivileged runtime user. --chown on COPY avoids duplicating /app in a
# second layer, which a separate chown -R would do.
RUN useradd --create-home --uid 10001 appuser

# Copy the ModelPipeline context. .dockerignore keeps venvs, notebooks,
# parquet/data_cache content, secrets, and tests out of the image.
COPY --chown=appuser:appuser . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# api_service.py imports "backend.*", which lives under /app/serving.
ENV PYTHONPATH="/app/serving"

# CRITICAL - do not remove. This single variable drives three things:
#   1. MLConfig.model_root  (the "walk up to a dir named ModelPipeline" lookup
#      cannot succeed here, because the code lives at /app, not /ModelPipeline)
#   2. MLConfig.data_loading_mode -> S3_STREAMING. Without it the container
#      silently selects LOCAL_CACHE and then fails looking for data_cache/
#      tables that are deliberately not baked into this image.
#   3. serving/backend/config.py's model_pipeline_root pydantic-settings field,
#      whose default_factory would otherwise raise RuntimeError at import.
ENV MODEL_PIPELINE_ROOT=/app

EXPOSE 8000

USER appuser

# Python-based probe so the runtime image needs no curl (and therefore no apt
# layer at all).
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status == 200 else 1)"]

CMD ["uvicorn", "backend.api_service:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
