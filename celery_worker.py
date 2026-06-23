"""
Celery worker entrypoint for the AutoReach engine (production).

Usage:
    celery -A celery_worker.celery_app worker --loglevel=info -Q engine,maintenance
    celery -A celery_worker.celery_app beat --loglevel=info
"""

from engine.worker import celery_app  # noqa: F401
import engine.tasks  # noqa: F401,E402  # register HITL dispatch task
