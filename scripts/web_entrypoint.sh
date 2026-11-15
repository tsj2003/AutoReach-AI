#!/bin/sh
# Azure Container Apps ingress targetPort is 8080; honor PORT if set.
set -eu
PORT="${PORT:-8080}"
WORKERS="${WEB_CONCURRENCY:-2}"
echo "starting gunicorn on 0.0.0.0:${PORT} workers=${WORKERS}"
exec gunicorn asgi:app \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
