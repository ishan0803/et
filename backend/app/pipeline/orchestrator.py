"""Pipeline orchestrator — coordinates the full video generation pipeline."""

import logging
from typing import Callable, Optional

from app.models import (
    Script, VisualPlan, VoiceResult, QAReport,
    PipelineResult, JobState,
)
from app.pipeline.script_generator import generate_script
from app.pipeline.visual_planner import generate_visual_plan
from app.pipeline.image_sourcer import source_images
from app.pipeline.data_viz import generate_data_visuals
from app.pipeline.voice_generator import generate_voice
from app.pipeline.video_composer import compose_video
from app.pipeline.qa_validator import validate_output
from app.pipeline.reflection import get_repair_strategy, should_continue_reflection

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[JobState, float, str, int], None]


class PipelineOrchestrator:
    """Orchestrates the full video generation pipeline with reflection loop."""

    def __init__(
        self,
        job_id: str,
        topic: str,
        source_url: Optional[str] = None,
        voice_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.job_id = job_id
        self.topic = topic
        self.source_url = source_url
        self.voice_id = voice_id
        self.progress_callback = progress_callback or (lambda *_: None)

        self.script: Optional[Script] = None
        self.visual_plan: Optional[VisualPlan] = None
        self.voice_result: Optional[VoiceResult] = None
        self.scene_images: dict[int, str] = {}
        self.chart_images: dict[int, str] = {}
        self.qa_report: Optional[QAReport] = None
        self.scraped_content = None

    def run(self) -> PipelineResult:
        """Run the full pipeline with reflection loop."""
        iteration = 0
        video_path = ""

        while True:
            try:
                # Stage 0: Scrape Content
                if self.source_url and not self.scraped_content:
                    self._update_progress(
                        JobState.QUEUED, 0.05,
                        "Scraping article content and high-quality images...", iteration
                    )
                    from app.pipeline.content_scraper import scrape_article
                    self.scraped_content = scrape_article(self.source_url)

                # Stage 1: Generate Script
                if self.script is None or (self.qa_report and not self.qa_report.passed):
                    self._update_progress(
                        JobState.GENERATING_SCRIPT, 0.1,
                        f"Generating script (iteration {iteration + 1})...",
                        iteration
                    )
                    retry_ctx = None
                    if self.qa_report:
                        strategy = get_repair_strategy(self.qa_report)
                        if strategy["rerun_script"]:
                            retry_ctx = strategy["script_context"]

                    scraped_text = self.scraped_content.text if self.scraped_content else None
                    self.script = generate_script(
                        self.topic, self.source_url, scraped_text, retry_ctx
                    )
                    logger.info(f"Script generated: {self.script.total_word_count} words")

                # Stage 2: Generate Visual Plan
                rerun_visual = False
                if self.qa_report and not self.qa_report.passed:
                    strategy = get_repair_strategy(self.qa_report)
                    rerun_visual = strategy["rerun_visual_plan"]

                if self.visual_plan is None or rerun_visual:
                    self._update_progress(
                        JobState.PLANNING_VISUALS, 0.25,
                        "Planning visual scenes...", iteration
                    )
                    visual_ctx = None
                    if self.qa_report and rerun_visual:
                        visual_ctx = strategy["visual_context"]

                    self.visual_plan = generate_visual_plan(
                        self.script, visual_ctx
                    )
                    logger.info(f"Visual plan: {self.visual_plan.total_scenes} scenes")

                    # Stage 3: Source Images
                    self._update_progress(
                        JobState.SOURCING_IMAGES, 0.4,
                        "Processing source article images or downloading from Pexels...", iteration
                    )
                    scraped_imgs = self.scraped_content.image_urls if self.scraped_content else None
                    self.scene_images = source_images(
                        self.visual_plan, self.job_id, scraped_imgs
                    )
                    logger.info(f"Sourced {len(self.scene_images)} images")

                    # Stage 4: Generate Data Visualizations
                    self._update_progress(
                        JobState.GENERATING_CHARTS, 0.5,
                        "Generating data visualizations...", iteration
                    )
                    self.chart_images = generate_data_visuals(
                        self.script, self.visual_plan, self.job_id
                    )
                    logger.info(f"Generated {len(self.chart_images)} charts")

                # Stage 5: Generate Voice
                rerun_voice = False
                if self.qa_report and not self.qa_report.passed:
                    strategy = get_repair_strategy(self.qa_report)
                    rerun_voice = strategy["rerun_voice"]

                if self.voice_result is None or rerun_voice:
                    self._update_progress(
                        JobState.GENERATING_VOICE, 0.6,
                        "Generating narration with ElevenLabs...", iteration
                    )
                    self.voice_result = generate_voice(
                        self.script, self.job_id, self.voice_id
                    )
                    logger.info(f"Voice: {self.voice_result.total_duration:.1f}s")

                # Stage 6: Compose Video
                self._update_progress(
                    JobState.COMPOSING_VIDEO, 0.75,
                    "Composing final video with effects...", iteration
                )
                video_path = compose_video(
                    self.script, self.visual_plan, self.voice_result,
                    self.scene_images, self.chart_images, self.job_id,
                )
                logger.info(f"Video composed: {video_path}")

                # Stage 7: QA Validation
                self._update_progress(
                    JobState.RUNNING_QA, 0.9,
                    f"Running quality validation (iteration {iteration + 1})...",
                    iteration
                )
                self.qa_report = validate_output(
                    self.script, self.visual_plan, self.voice_result, iteration
                )

                # Check if we need to reflect (Temporarily disabled for speed)
                # if should_continue_reflection(iteration, self.qa_report):
                #     iteration += 1
                #     self._update_progress(
                #         JobState.REFLECTING, 0.95,
                #         f"Quality score: {self.qa_report.overall_score:.2f}. "
                #         f"Reflecting and improving (iteration {iteration + 1})...",
                #         iteration
                #     )
                #     logger.info(
                #         f"Reflection iteration {iteration}: "
                #         f"score={self.qa_report.overall_score:.3f}"
                #     )
                #     continue
                # else:
                #     break

                # Disable iterations for now — just return the first output
                break

            except Exception as e:
                logger.error(f"Pipeline error at iteration {iteration}: {e}")
                raise

        return PipelineResult(
            job_id=self.job_id,
            video_path=video_path,
            script=self.script,
            visual_plan=self.visual_plan,
            voice_result=self.voice_result,
            qa_report=self.qa_report,
            iterations=iteration + 1,
        )

    def _update_progress(self, state: JobState, progress: float,
                         message: str, iteration: int = 0):
        """Update progress via callback."""
        self.progress_callback(state, progress, message, iteration)
