# syntax=docker/dockerfile:1

# =============================================================================
# CAD-to-Cutlist Engine — production image
#
#   Stage 1: build the React/Vite frontend
#   Stage 2: install the Python engine + all extras, add built frontend, run
#
# Run:   docker compose up -d --build
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — frontend build (node)
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /app

# Install deps first for layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# API token is embedded into the SPA bundle at build time so the review UI
# can call /api/* with Authorization headers. Pass via compose build args.
ARG VITE_API_TOKEN=""
ENV VITE_API_TOKEN=${VITE_API_TOKEN}

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Core deps + optional extras (ezdxf for DXF input, groq for AI features).
# Everything ships as wheels for 3.12 — no compiler needed.
COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir ".[cad,ai]"

# Built SPA served by FastAPI at /
COPY --from=frontend /app/dist/ ./frontend/dist/
ENV CUTLIST_FRONTEND_DIR=/app/frontend/dist

# Persistent review sessions live on a volume
ENV CUTLIST_SESSION_DIR=/data/sessions
RUN mkdir -p /data/sessions \
    && groupadd --system cutlist \
    && useradd --system --gid cutlist --create-home cutlist \
    && chown -R cutlist:cutlist /data /app

USER cutlist

EXPOSE 8000

# Engine is stateful in-process (per-session locks + cache): default to a
# single worker. Scale horizontally with a shared volume on CUTLIST_SESSION_DIR.
ENV CUTLIST_WORKERS=1
CMD ["sh", "-c", "exec python -m uvicorn cutlist_engine.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${CUTLIST_WORKERS}"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else sys.exit(1)"
