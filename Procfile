web: gunicorn asgi:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker: celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2 -Q engine,maintenance,standard-agents
beat: celery -A celery_worker.celery_app beat --loglevel=info
