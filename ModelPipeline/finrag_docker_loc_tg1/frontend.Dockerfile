# ============================================================================
# Frontend Dockerfile - Streamlit UI
# Context: ModelPipeline/ (parent directory of finrag_docker_loc_tg1)
# Requirements: serving/frontend/requirements.txt
#
# Multi-stage, same shape as backend.Dockerfile. The frontend is a pure HTTP
# client of the backend - it needs no AWS access, no ML dependencies, and no
# part of finrag_ml_tg1, so only serving/frontend/ is copied in.
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1 - builder: resolve dependencies into /opt/venv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

COPY serving/frontend/requirements.txt /tmp/requirements.txt

ENV UV_LINK_MODE=copy
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 - runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

# Only the Streamlit app itself - not the whole ModelPipeline context. Path is
# kept identical to the repo layout so the CMD below matches local invocation.
COPY --chown=appuser:appuser serving/frontend ./serving/frontend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8501

# app.py and its siblings import each other flat ("from api_client import ..."),
# with "from frontend.X import ..." fallbacks in a few try blocks - so both the
# package parent and the module dir go on the path.
ENV PYTHONPATH="/app/serving:/app/serving/frontend"

EXPOSE 8501

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5).status == 200 else 1)"]

CMD ["streamlit", "run", "serving/frontend/app.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--browser.serverAddress", "localhost"]
