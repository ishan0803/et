"""Unified Celery application configuration."""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "et_combined",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.video_tasks",
        "app.tasks.news_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=900,
    task_soft_time_limit=600,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=5,

    # Route tasks to specific queues
    task_routes={
        "app.tasks.video_tasks.*": {"queue": "video"},
        "app.tasks.news_tasks.*": {"queue": "news"},
    },

    # Scheduled tasks
    beat_schedule={
        "fetch-news-every-15-min": {
            "task": "app.tasks.news_tasks.fetch_and_cache_news",
            "schedule": settings.NEWS_FETCH_INTERVAL_MINUTES * 60,
            "options": {"queue": "news"},
        },
    },
)
