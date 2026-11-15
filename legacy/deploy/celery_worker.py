"""
Celery worker entrypoint for AutoReach-AI.
Usage:
    celery -A celery_worker.celery worker --loglevel=info
    celery -A celery_worker.celery beat --loglevel=info
"""

from app import create_app
from app.celery_app import make_celery

flask_app = create_app()
celery = make_celery(flask_app)

# Import tasks so Celery discovers them
import app.tasks  # noqa: F401
