"""
Agent Orchestrator — The "Agentic AI" Core

This is what makes the project "agentic":
Instead of one function doing everything, we have a coordinator
that delegates to specialized agents and merges their results.

Flow:
1. Receive user ID
2. Load user profile (from Redis — fast)
3. Load news pool (from Redis cache or DB)
4. Run Personalizer Agent → filter & rank articles
5. Run Rewriter Agent → personalize content per article
6. Store result in Redis
7. Return personalized feed
"""

import json
import asyncio
from typing import List, Dict

from app.services.redis_service import (
    get_user_profile,
    get_cached_feed,
    cache_feed,
)
from app.services.news_service import rank_articles_for_user
from app.services.ai_service import rewrite_article_for_user
from app.config import settings

# Redis key where Celery stores the global news pool
NEWS_POOL_KEY = "news:pool"


async def build_personalized_feed(user_id: int, redis_client) -> List[Dict]:
    """
    Main orchestrator function.
    Builds a personalized news feed for a user end-to-end.

    Returns a list of personalized articles.
    """
    print(f"\n🤖 Orchestrator: Building feed for user {user_id}")

    # ── Step 1: Check if we already have a fresh cached feed ──
    cached = get_cached_feed(user_id)
    if cached:
        print(f"⚡ Cache hit — returning cached feed for user {user_id}")
        return cached

    # ── Step 2: Load user profile from Redis ──────────────────
    profile = get_user_profile(user_id)
    if not profile:
        print(f"⚠️  No profile found for user {user_id} — using default")
        profile = {"role": "student", "interests": [], "level": "beginner", "engagement": {}}

    print(f"👤 Profile loaded: role={profile['role']}, interests={profile['interests']}")

    # ── Step 3: Load news pool (fetched by Celery) ────────────
    raw_pool = redis_client.get(NEWS_POOL_KEY)
    if raw_pool:
        articles = json.loads(raw_pool)
    else:
        # Celery hasn't run yet (first startup) — fetch synchronously
        print("📰 No news pool in Redis — fetching fresh news now...")
        from app.services.news_service import fetch_all_feeds
        articles = await fetch_all_feeds()

    print(f"📦 News pool has {len(articles)} articles")

    # ── Step 4: Personalizer Agent ────────────────────────────
    # Score and rank articles based on user profile
    # MULTI-TIER FILTERING: Strict → good → any match
    top_articles = rank_articles_for_user(
        articles,
        profile,
        top_n=settings.MAX_ARTICLES_PER_FEED
    )
    
    print(f"🎯 Personalizer selected {len(top_articles)} articles")
    
    if not top_articles:
        print(f"⚠️  No articles available for user {user_id}")
        feed = []
        cache_feed(user_id, feed, ttl_seconds=900)
        return feed

    # ── Step 5: Rewriter Agent ────────────────────────────────
    # Rewrite each article in the user's language/style
    # We run these concurrently (asyncio.gather) to save time
    rewrite_tasks = [
        rewrite_article_for_user(article, profile)
        for article in top_articles
    ]
    personalized_articles = await asyncio.gather(*rewrite_tasks)
    print(f"✍️  Rewriter personalized {len(personalized_articles)} articles")

    # ── Step 6: Clean up for JSON response ───────────────────
    feed = []
    for article in personalized_articles:
        feed.append({
            "title":          article.get("title"),
            "url":            article.get("url"),
            "source":         article.get("source"),
            "category":       article.get("category"),
            "tags":           article.get("tags", []),
            "relevance_score": article.get("relevance_score", 0),
            "personalized":   article.get("personalized", {}),
            "ai_generated":   article.get("ai_generated", False),
            "published":      str(article.get("published", "")),
        })

    # ── Step 7: Cache the feed for 15 minutes ─────────────────
    cache_feed(user_id, feed, ttl_seconds=900)
    print(f"✅ Feed cached for user {user_id} (TTL: 15 min)\n")

    return feed
