"""Celery tasks for news fetching."""

import json
import asyncio
import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.news_tasks.fetch_and_cache_news")
def fetch_and_cache_news(self):
    """Fetch latest news from RSS feeds and store in Redis."""
    import redis as redis_lib

    try:
        logger.info("🔄 Celery: Fetching fresh news from RSS feeds...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from app.services.news_service import fetch_all_feeds
        articles = loop.run_until_complete(fetch_all_feeds())
        loop.close()

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        r.setex("news:pool", 1800, json.dumps(articles, default=str))

        logger.info(f"✅ Celery: Cached {len(articles)} articles in Redis")
        return {"status": "success", "count": len(articles)}

    except Exception as exc:
        logger.error(f"❌ Celery fetch failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
