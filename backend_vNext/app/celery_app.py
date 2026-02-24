"""
Celery application configuration for background task processing.

Uses Redis as the message broker for reliable task queuing.
"""

from celery import Celery

from app.config import settings


# Create Celery application
celery_app = Celery(
    "backend_vnext",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.extraction_tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Requeue task if worker dies
    task_time_limit=3600,  # 1 hour hard limit per task
    task_soft_time_limit=3000,  # 50 minute soft limit (for cleanup)

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_concurrency=1,  # Single worker for sequential execution

    # Retry settings
    task_default_retry_delay=60,  # 1 minute retry delay
    task_max_retries=3,

    # Task routing (optional - for future scaling)
    task_routes={
        "app.tasks.extraction_tasks.*": {"queue": "extraction"},
    },
)


def get_celery_app() -> Celery:
    """Get the Celery application instance."""
    return celery_app
