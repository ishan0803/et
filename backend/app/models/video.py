"""Pydantic models for the entire video generation pipeline."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────

class MotionType(str, Enum):
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    KEN_BURNS = "ken_burns"


class TransitionType(str, Enum):
    CROSSFADE = "crossfade"
    SLIDE_LEFT = "slide_left"
    FADE_BLACK = "fade_black"


class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    STAT_HIGHLIGHT = "stat_highlight"


class JobState(str, Enum):
    QUEUED = "queued"
    GENERATING_SCRIPT = "generating_script"
    PLANNING_VISUALS = "planning_visuals"
    SOURCING_IMAGES = "sourcing_images"
    GENERATING_CHARTS = "generating_charts"
    GENERATING_VOICE = "generating_voice"
    COMPOSING_VIDEO = "composing_video"
    RUNNING_QA = "running_qa"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Script Models ───────────────────────────────────────────────────

class ScriptSegment(BaseModel):
    """A single narration segment."""
    segment_id: int
    text: str = Field(..., description="Narration text, max 15 words per sentence")
    duration_estimate: float = Field(..., description="Estimated duration in seconds")
    is_hook: bool = False
    is_cta: bool = False
    is_transition: bool = False
    emphasis_words: list[str] = Field(default_factory=list)


class Script(BaseModel):
    """Full generated script."""
    topic: str
    title: str
    segments: list[ScriptSegment]
    total_word_count: int
    estimated_duration: float
    key_facts: list[str] = Field(default_factory=list)
    numeric_data: list[dict] = Field(default_factory=list, description="Extracted numbers/stats for charts")


# ─── Visual Plan Models ──────────────────────────────────────────────

class ChartConfig(BaseModel):
    """Configuration for a data chart."""
    chart_type: ChartType
    title: str
    data_labels: list[str]
    data_values: list[float]
    highlight_index: Optional[int] = None
    highlight_label: Optional[str] = None
    unit: str = ""


class SceneVisual(BaseModel):
    """Visual instructions for a single scene."""
    scene_id: int
    segment_ids: list[int] = Field(..., description="IDs of script segments covered")
    visual_description: str = Field(..., description="Detailed description of what to show")
    search_query: str = Field(..., description="Pexels search query (max 3 words)")
    motion_type: MotionType
    has_chart: bool = Field(False, description="Whether to show a data chart instead of image")
    chart_config: Optional[ChartConfig] = None
    headline: str = Field(..., description="Short headline for the right text panel (max 30 chars)")
    bullet_points: list[str] = Field(..., description="3 bullet points summarizing the scene for the text panel")
    duration: float = Field(..., description="Estimated duration in seconds")


class VisualPlan(BaseModel):
    """Full visual plan mapping script to scenes."""
    scenes: list[SceneVisual]
    total_scenes: int
    total_duration: float


# ─── Data Visualization Models ───────────────────────────────────────

class DataChart(BaseModel):
    """A data visualization chart."""
    chart_id: int
    chart_type: ChartType
    title: str
    data_labels: list[str]
    data_values: list[float]
    highlight_index: Optional[int] = None
    highlight_label: Optional[str] = None
    unit: str = ""
    image_path: Optional[str] = None


# ─── Voice Models ────────────────────────────────────────────────────

class VoiceSegment(BaseModel):
    """Generated audio for a script segment."""
    segment_id: int
    audio_path: str
    duration: float
    wpm: float


class VoiceResult(BaseModel):
    """Full voice generation result."""
    segments: list[VoiceSegment]
    combined_audio_path: str
    main_audio_path: str
    cta_audio_path: str
    main_duration: float
    cta_duration: float
    total_duration: float
    average_wpm: float


# ─── QA Models ───────────────────────────────────────────────────────

class QADimensionScore(BaseModel):
    """Score for a single QA dimension."""
    dimension: str
    score: float
    weight: float
    weighted_score: float
    feedback: str


class QAReport(BaseModel):
    """Full QA validation report."""
    overall_score: float
    passed: bool
    dimension_scores: list[QADimensionScore]
    hard_fail_triggered: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    iteration: int = 0


# ─── API Models ──────────────────────────────────────────────────────

class JobRequest(BaseModel):
    """API request to generate a video."""
    topic: str = Field(..., min_length=5, max_length=500, description="News topic to generate video for")
    source_url: Optional[str] = Field(None, description="Optional source article URL")
    voice_id: Optional[str] = None


class JobResponse(BaseModel):
    """API response after submitting a job."""
    job_id: str
    status: JobState
    message: str


class JobStatus(BaseModel):
    """Job status response."""
    job_id: str
    status: JobState
    progress: float = Field(0.0, ge=0.0, le=1.0)
    current_stage: str = ""
    message: str = ""
    video_url: Optional[str] = None
    qa_report: Optional[QAReport] = None
    iteration: int = 0
    error: Optional[str] = None


class PipelineResult(BaseModel):
    """Result of the full pipeline."""
    job_id: str
    video_path: str
    script: Script
    visual_plan: VisualPlan
    voice_result: VoiceResult
    qa_report: QAReport
    iterations: int
