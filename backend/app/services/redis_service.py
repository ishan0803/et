"""Redis service — shared cache for feeds, profiles, and video results."""

import redis
import json
from app.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_user_profile(user_id: int) -> dict | None:
    """Fetch user profile from Redis."""
    raw = redis_client.get(f"user:{user_id}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            import ast
            try:
                return ast.literal_eval(raw)
            except Exception:
                print(f"❌ Failed to parse user profile for {user_id}")
                return None
    return None


def get_cached_feed(user_id: int) -> list | None:
    """Get a pre-built feed from Redis."""
    raw = redis_client.get(f"feed:{user_id}")
    if raw:
        return json.loads(raw)
    return None


def cache_feed(user_id: int, feed: list, ttl_seconds: int = 900):
    """Save a user's personalized feed in Redis (15 min TTL)."""
    redis_client.setex(
        f"feed:{user_id}",
        ttl_seconds,
        json.dumps(feed, default=str),
    )


def update_engagement(user_id: int, category: str, delta: float = 0.1):
    """Update user engagement scores for a category."""
    raw = redis_client.get(f"user:{user_id}")
    if not raw:
        return

    try:
        profile = json.loads(raw)
    except Exception:
        import ast
        profile = ast.literal_eval(raw)

    engagement = profile.get("engagement", {})
    current = engagement.get(category, 0.5)
    engagement[category] = min(1.0, max(0.0, current + delta))
    profile["engagement"] = engagement

    redis_client.setex(f"user:{user_id}", 86400, json.dumps(profile))
    redis_client.delete(f"feed:{user_id}")
