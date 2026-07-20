# KritiFin backend (FastAPI). Slim Python base; pinned deps installed first for
# layer caching. Runs uvicorn with a small worker count suited to a modest VM.
FROM python:3.12-slim AS base

# - PYTHONUNBUFFERED: logs stream immediately (important for `docker logs`).
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the image.
# - PIP_NO_CACHE_DIR: smaller image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2-binary, pymupdf, cryptography ship manylinux wheels, so no compiler
# toolchain is needed on top of the slim base.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (context is ./backend — see docker-compose build.context).
COPY . .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness only (no DB/Qdrant dependency): keeps the container from being killed
# during a transient dependency blip. External monitors use /health/ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status==200 else 1)"

# 2 web workers is a conservative default for a small VM; raise via the compose
# command override as the box grows. INLINE_WORKER=true (the default) means each
# web process also drains the durable job queue — fine at this scale.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
