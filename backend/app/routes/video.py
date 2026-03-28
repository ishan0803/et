"""Video generation routes with Redis caching."""

import uuid
import hashlib
import json
import logging

from fastapi import APIRouter, HTTPException
from app.config import settings
from app.models.video import JobRequest, JobResponse, JobStatus, JobState
from app.tasks.video_tasks import generate_video_task, get_job_status
from app.services.redis_service import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["Video Studio"])

VIDEO_CACHE_TTL = 86400  # 24 hours


def _cache_key(topic: str, source_url: str = None) -> str:
    """Generate a deterministic cache key for a video request."""
    raw = f"{topic}|{source_url or ''}"
    return f"video:cache:{hashlib.md5(raw.encode()).hexdigest()}"


@router.post("/generate", response_model=JobResponse)
async def generate_video(request: JobRequest):
    """Submit a video generation job. Checks Redis cache first."""

    # Validate API keys
    if not settings.groq_api_key:
        raise HTTPException(400, "GROQ_API_KEY not configured")
    if not settings.elevenlabs_api_key:
        raise HTTPException(400, "ELEVENLABS_API_KEY not configured")
    if not settings.pexels_api_key:
        raise HTTPException(400, "PEXELS_API_KEY not configured")

    # Check video cache
    cache_key = _cache_key(request.topic, request.source_url)
    cached = redis_client.get(cache_key)
    if cached:
        cached_data = json.loads(cached)
        logger.info(f"Video cache hit for: {request.topic[:50]}")
        return JobResponse(
            job_id=cached_data["job_id"],
            status=JobState.COMPLETED,
            message=f"Video retrieved from cache",
        )

    # Generate new video
    job_id = str(uuid.uuid4())
    logger.info(f"New video job {job_id}: {request.topic}")

    generate_video_task.apply_async(
        kwargs={
            "job_id": job_id,
            "topic": request.topic,
            "source_url": request.source_url,
            "voice_id": request.voice_id,
            "cache_key": cache_key,
        },
        queue="video",
    )

    return JobResponse(
        job_id=job_id,
        status=JobState.QUEUED,
        message=f"Job queued for processing: {request.topic}",
    )


@router.get("/status/{job_id}", response_model=JobStatus)
async def job_status(job_id: str):
    """Get the status of a video generation job."""
    data = get_job_status(job_id)
    if not data:
        raise HTTPException(404, f"Job {job_id} not found")

    return JobStatus(
        job_id=data["job_id"],
        status=JobState(data["status"]),
        progress=data.get("progress", 0.0),
        current_stage=data.get("current_stage", ""),
        message=data.get("message", ""),
        video_url=data.get("video_url") or None,
        qa_report=data.get("qa_report"),
        iteration=data.get("iteration", 0),
        error=data.get("error") or None,
    )


@router.get("/download/{job_id}")
async def download_video(job_id: str):
    """Download the generated video."""
    import os
    from fastapi.responses import FileResponse

    data = get_job_status(job_id)
    if not data:
        raise HTTPException(404, f"Job {job_id} not found")
    if data["status"] != JobState.COMPLETED.value:
        raise HTTPException(400, "Video not ready yet")

    video_path = os.path.join(settings.output_dir, job_id, "final.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(404, "Video file not found")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"news_video_{job_id[:8]}.mp4",
    )
