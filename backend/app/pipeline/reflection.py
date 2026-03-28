"""Reflection and repair loop for pipeline quality improvement."""

import logging
from app.config import MAX_REFLECTION_ITERATIONS, REPAIR_STRATEGIES
from app.models import QAReport

logger = logging.getLogger(__name__)


def get_repair_strategy(qa_report: QAReport) -> dict:
    """Analyze QA report and determine what to repair."""
    repairs = {
        "rerun_script": False,
        "rerun_visual_plan": False,
        "rerun_voice": False,
        "script_context": "",
        "visual_context": "",
    }

    if qa_report.passed:
        return repairs

    # Check hard fails
    for fail in qa_report.hard_fail_triggered:
        if fail in ("missing_hook", "hallucinated_facts"):
            repairs["rerun_script"] = True
            repairs["script_context"] += f"HARD FAIL: {fail}. "
        elif fail == "visual_mismatch":
            repairs["rerun_visual_plan"] = True
            repairs["visual_context"] += f"HARD FAIL: {fail}. "
        elif fail == "bad_pacing":
            repairs["rerun_script"] = True
            repairs["script_context"] += "Script pacing is off. Adjust total word count. "

    # Check low dimension scores
    for dim in qa_report.dimension_scores:
        if dim.score < 0.8:
            strategy_key = _map_dimension_to_strategy(dim.dimension)
            if strategy_key:
                strategy = REPAIR_STRATEGIES.get(strategy_key, "")
                if strategy in ("rewrite_hook_and_transitions", "adjust_script_length"):
                    repairs["rerun_script"] = True
                    repairs["script_context"] += f"Low {dim.dimension} ({dim.score:.2f}): {dim.feedback}. "
                elif strategy == "regenerate_visual_plan":
                    repairs["rerun_visual_plan"] = True
                    repairs["visual_context"] += f"Low {dim.dimension} ({dim.score:.2f}): {dim.feedback}. "
                elif strategy == "regenerate_voice":
                    repairs["rerun_voice"] = True

    # Build human-readable context for repair prompts
    if qa_report.recommendations:
        context = " ".join(qa_report.recommendations[:3])
        if repairs["rerun_script"]:
            repairs["script_context"] += f"Recommendations: {context}"
        if repairs["rerun_visual_plan"]:
            repairs["visual_context"] += f"Recommendations: {context}"

    logger.info(
        f"Repair strategy: script={repairs['rerun_script']}, "
        f"visual={repairs['rerun_visual_plan']}, voice={repairs['rerun_voice']}"
    )

    return repairs


def _map_dimension_to_strategy(dimension: str) -> str | None:
    """Map a QA dimension to a repair strategy key."""
    mapping = {
        "engagement": "low_engagement",
        "visual_alignment": "visual_mismatch",
        "pacing": "bad_pacing",
        "audio_quality": "low_audio_quality",
        "factual_accuracy": "low_engagement",  # Rewrite script for factual issues
    }
    return mapping.get(dimension)


def should_continue_reflection(iteration: int, qa_report: QAReport) -> bool:
    """Determine if another reflection iteration is needed."""
    if qa_report.passed:
        logger.info(f"QA passed at iteration {iteration}")
        return False

    if iteration >= MAX_REFLECTION_ITERATIONS:
        logger.warning(
            f"Max reflection iterations ({MAX_REFLECTION_ITERATIONS}) reached. "
            f"Score: {qa_report.overall_score:.3f}"
        )
        return False

    return True
