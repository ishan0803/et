"""Celery tasks for video generation — with Redis caching."""

import json
import logging
import traceback

import redis

from app.celery_app import celery_app
from app.config import settings
from app.models.video import JobState
from app.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

_redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

VIDEO_CACHE_TTL = 86400  # 24 hours


def update_job_status(job_id: str, status: JobState, progress: float = 0.0,
                      message: str = "", video_url: str = None,
                      qa_report: dict = None, iteration: int = 0,
                      error: str = None):
    """Update job status in Redis."""
    data = {
        "job_id": job_id,
        "status": status.value,
        "progress": progress,
        "current_stage": status.value,
        "message": message,
        "video_url": video_url or "",
        "iteration": iteration,
        "error": error or "",
    }
    if qa_report:
        data["qa_report"] = json.dumps(qa_report)
    _redis.set(f"job:{job_id}", json.dumps(data), ex=3600)


def get_job_status(job_id: str) -> dict | None:
    """Get job status from Redis."""
    data = _redis.get(f"job:{job_id}")
    if data:
        result = json.loads(data)
        if "qa_report" in result and isinstance(result["qa_report"], str):
            try:
                result["qa_report"] = json.loads(result["qa_report"])
            except (json.JSONDecodeError, TypeError):
                result["qa_report"] = None
        return result
    return None


@celery_app.task(bind=True, name="app.tasks.video_tasks.generate_video")
def generate_video_task(self, job_id: str, topic: str, source_url: str = None,
                        voice_id: str = None, cache_key: str = None):
    """Main Celery task for video generation with caching."""
    logger.info(f"Starting video generation for job {job_id}: {topic}")

    def progress_callback(status: JobState, progress: float, message: str,
                          iteration: int = 0):
        update_job_status(job_id, status, progress, message, iteration=iteration)

    try:
        update_job_status(job_id, JobState.QUEUED, 0.0, "Job started")

        orchestrator = PipelineOrchestrator(
            job_id=job_id,
            topic=topic,
            source_url=source_url,
            voice_id=voice_id,
            progress_callback=progress_callback,
        )

        result = orchestrator.run()

        video_url = f"/output/{job_id}/final.mp4"
        update_job_status(
            job_id, JobState.COMPLETED, 1.0,
            "Video generated successfully!",
            video_url=video_url,
            qa_report=result.qa_report.model_dump() if result.qa_report else None,
            iteration=result.iterations,
        )

        # Cache the result for instant retrieval
        if cache_key:
            _redis.set(
                cache_key,
                json.dumps({"job_id": job_id, "video_url": video_url}),
                ex=VIDEO_CACHE_TTL,
            )
            logger.info(f"Cached video for key {cache_key}")

        logger.info(f"Job {job_id} completed successfully")
        return {"job_id": job_id, "video_url": video_url}

    except Exception as e:
        logger.error(f"Job {job_id} failed: {traceback.format_exc()}")
        update_job_status(
            job_id, JobState.FAILED, 0.0,
            f"Generation failed: {str(e)}",
            error=str(e),
        )
        raise
