"""Unified ET Platform — FastAPI Application."""

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.database import engine, Base
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    print("🚀 Starting ET Combined Platform...")

    # Create all database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables ready")

    # Trigger initial news fetch via Celery
    try:
        from app.tasks.news_tasks import fetch_and_cache_news
        fetch_and_cache_news.delay()
        print("📰 Triggered initial news fetch via Celery")
    except Exception as e:
        print(f"⚠️  Could not trigger Celery task: {e}")

    yield

    print("🛑 Shutting down ET Combined Platform...")
    await engine.dispose()


app = FastAPI(
    title="ET Combined Intelligence Platform",
    description="Unified API — Personalized News, Video Generation, and AI Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount output directory for video serving
os.makedirs(settings.output_dir, exist_ok=True)
app.mount("/output", StaticFiles(directory=settings.output_dir), name="output")

# ─── Register routes ──────────────────────────────────────────
from app.routes import auth, news, video, intel

app.include_router(auth.router)
app.include_router(news.router)
app.include_router(video.router)
app.include_router(intel.router)


# ─── Health checks ────────────────────────────────────────────
@app.get("/api/health", tags=["Health"])
async def health():
    import redis as redis_lib
    redis_ok = False
    try:
        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "running",
        "app": "ET Combined Intelligence Platform",
        "redis": "ok" if redis_ok else "unreachable",
    }
