"""News feed routes — personalized news endpoints."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.agents.orchestrator import build_personalized_feed
from app.services.redis_service import redis_client, update_engagement
from app.clerk_auth import get_clerk_user_id
from app.routes.auth import get_or_create_user

router = APIRouter(prefix="/api/news", tags=["News Feed"])


@router.get("/feed")
async def get_personalized_feed(
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized news feed for authenticated user."""
    try:
        user = await get_or_create_user(clerk_id, db)
        feed = await build_personalized_feed(user.id, redis_client)
        return {
            "user_id": user.id,
            "article_count": len(feed),
            "articles": feed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feed generation failed: {str(e)}")


@router.post("/engage")
async def record_engagement(
    article_category: str,
    action: str = "read",
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Record user engagement with an article."""
    user = await get_or_create_user(clerk_id, db)

    if action in ("read", "click"):
        update_engagement(user.id, article_category, delta=0.1)
        message = f"Boosted interest in '{article_category}'"
    elif action == "skip":
        update_engagement(user.id, article_category, delta=-0.05)
        message = f"Reduced interest in '{article_category}'"
    else:
        message = "Unknown action — no change"

    return {"status": "ok", "message": message}


@router.delete("/feed/cache")
async def invalidate_feed_cache(
    clerk_id: str = Depends(get_clerk_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Clear cached feed to regenerate fresh."""
    user = await get_or_create_user(clerk_id, db)
    redis_client.delete(f"feed:{user.id}")
    return {"status": "ok", "message": "Cache cleared"}


@router.get("/pool/status")
async def news_pool_status():
    """Debug endpoint — shows news pool status."""
    import json
    raw = redis_client.get("news:pool")
    if raw:
        articles = json.loads(raw)
        return {
            "status": "populated",
            "count": len(articles),
            "ttl_seconds": redis_client.ttl("news:pool"),
        }
    return {"status": "empty", "message": "Celery has not fetched news yet"}
