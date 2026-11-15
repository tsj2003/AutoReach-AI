"""
Celery application factory for AutoReach-AI.
Configures Celery with Redis broker and Flask app context binding.
"""

import os
from celery import Celery


def make_celery(app=None):
    """Create a Celery instance configured for AutoReach."""
    celery = Celery(
        'autoreach',
        broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    )

    celery.conf.update(
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        result_expires=86400,
        task_routes={
            'app.tasks.run_campaign_batch': {'queue': 'campaigns'},
            'app.tasks.check_replies_task': {'queue': 'campaigns'},
            'app.tasks.reset_daily_counters': {'queue': 'maintenance'},
        },
        beat_schedule={
            'reset-daily-counters': {
                'task': 'app.tasks.reset_daily_counters',
                'schedule': 86400.0,  # Once per day
            },
        },
    )

    if app:
        celery.conf.update(app.config)

        class ContextTask(celery.Task):
            abstract = True

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

    return celery
