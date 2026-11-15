FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and dashboard build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev nodejs npm && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail the image if Python 3.11 cannot parse the app (gunicorn boot SyntaxError).
RUN python -m compileall -q -x '(^|/)\.(venv|git)|node_modules|legacy|dashboard|landing-page|chrome-extension' .

# Always rebuild dashboard assets so ACR images never ship stale static.
RUN npm ci --prefix dashboard && npm run build --prefix dashboard

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    WEB_CONCURRENCY=2
EXPOSE 8080

# Web default: bind 0.0.0.0:$PORT via gunicorn uvicorn.workers.UvicornWorker (Azure ingress targetPort=8080).
# Worker/beat override command+args to celery — this entrypoint is not used there.
COPY scripts/web_entrypoint.sh /web_entrypoint.sh
RUN chmod +x /web_entrypoint.sh
ENTRYPOINT ["/web_entrypoint.sh"]
