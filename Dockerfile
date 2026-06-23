FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and dashboard build.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev nodejs npm && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN npm ci --prefix dashboard && npm run build --prefix dashboard

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Default to the web process; override CMD for worker/beat.
CMD ["gunicorn", "asgi:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120"]
