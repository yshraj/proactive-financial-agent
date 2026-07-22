# KritiFin backend (FastAPI). One base stage with the app + deps, then two
# deployable targets:
#
#   api    (default) — uvicorn web server. Runs unchanged on a VM/compose and
#            on AWS Lambda: the Lambda Web Adapter extension copied into
#            /opt/extensions is started by the Lambda runtime and proxies
#            invocations to uvicorn over HTTP; outside Lambda the file is
#            inert. No Mangum, no code changes.
#   worker — queue worker as a native Lambda handler (app/lambda_worker.py)
#            via awslambdaric. Invoked async by the API after each enqueue and
#            by the EventBridge safety-net schedule (deploy/aws/template.yaml).
#
# Build:  docker build --target api -t kritifin-api .
#         docker build --target worker -t kritifin-worker .
# (sam build selects targets via Metadata.DockerBuildTarget in the template.)
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

# Unprivileged runtime user (created before COPY so ownership is set in the
# same layer as the files, instead of a duplicating chown -R afterwards).
RUN useradd --create-home --uid 10001 appuser

# App code (context is ./backend — see docker-compose build.context).
COPY --chown=appuser:appuser . .

# The local-disk storage fallback (no SUPABASE_SERVICE_ROLE_KEY) writes to
# uploads/, which .dockerignore keeps out of the image — pre-create it writable.
RUN install -d -o appuser -g appuser /app/uploads

# ---------------------------------------------------------------------------
# worker: queue worker Lambda (native handler, no HTTP server).
# ---------------------------------------------------------------------------
FROM base AS worker

# Runtime interface client that speaks the Lambda Runtime API and dispatches
# to our handler. Kept out of requirements.txt — it is image-only.
RUN pip install --no-cache-dir "awslambdaric>=3.0.0"

USER appuser
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["app.lambda_worker.handler"]

# ---------------------------------------------------------------------------
# api (default target): uvicorn everywhere; Lambda Web Adapter on Lambda.
# ---------------------------------------------------------------------------
FROM base AS api

# AWS Lambda Web Adapter: launched by the Lambda extensions mechanism, it
# translates function invocations into HTTP requests against uvicorn. Waits
# for AWS_LWA_READINESS_CHECK_PATH before accepting traffic.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
ENV AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_INVOKE_MODE=buffered

USER appuser
EXPOSE 8000

# Liveness only (no DB/Qdrant dependency): keeps the container from being killed
# during a transient dependency blip. External monitors use /health/ready.
# (docker-compose gates the frontend on this; Lambda ignores HEALTHCHECK.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status==200 else 1)"

# 2 web workers is a conservative default for a small VM. On Lambda the SAM
# template overrides this to a single worker (one invocation per environment).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
