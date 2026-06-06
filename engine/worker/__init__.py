"""
Distributed execution layer (production).

celery_app — the Celery application + tasks. Used only when REDIS_URL is set.
Dev mode runs ticks inline via the cockpit; this module is the scale-out path.
"""

from engine.worker.celery_app import celery_app  # noqa: F401

__all__ = ["celery_app"]
