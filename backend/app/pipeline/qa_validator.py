"""QA validator using Gemini 2.5 Flash for quality scoring."""

import json
import logging
import time
from groq import Groq

from app.config import (
    settings, SCORING_WEIGHTS, QA_MINIMUM_SCORE,
    HARD_FAIL_CONDITIONS, VIDEO_MIN_DURATION, VIDEO_MAX_DURATION,
    MIN_SCENE_CHANGES,
)
from app.models import (
    Script, VisualPlan, VoiceResult,
    QAReport, QADimensionScore,
)
from app.utils.helpers import parse_llm_json

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """You are a strict quality assurance reviewer for AI-generated news videos. You evaluate video components on multiple dimensions and provide numerical scores with specific feedback.

Be critical but fair. A score of 0.9+ means broadcast quality. Score honestly."""


def validate_output(
    script: Script,
    visual_plan: VisualPlan,
    voice_result: VoiceResult,
    iteration: int = 0,
) -> QAReport:
    """Run QA validation on the pipeline outputs."""

    client = Groq(api_key=settings.groq_api_key)

    # Build the review payload
    review_data = {
        "script": {
            "topic": script.topic,
            "title": script.title,
            "total_words": script.total_word_count,
            "estimated_duration": script.estimated_duration,
            "segment_count": len(script.segments),
            "has_hook": any(s.is_hook for s in script.segments),
            "has_cta": any(s.is_cta for s in script.segments),
            "key_facts": script.key_facts,
            "segments": [{"id": s.segment_id, "text": s.text, "is_hook": s.is_hook,
                          "is_cta": s.is_cta, "is_transition": s.is_transition}
                         for s in script.segments],
        },
        "visual_plan": {
            "total_scenes": visual_plan.total_scenes,
            "total_duration": visual_plan.total_duration,
            "scenes": [{"id": s.scene_id, "headline": s.headline, "bullets": s.bullet_points,
                         "motion": s.motion_type.value, "query": s.search_query,
                         "has_chart": s.has_chart}
                        for s in visual_plan.scenes],
        },
        "voice": {
            "total_duration": voice_result.total_duration,
            "average_wpm": voice_result.average_wpm,
            "segment_count": len(voice_result.segments),
        },
    }

    prompt = f"""Review this AI-generated news video's components and score each dimension.

Review data:
{json.dumps(review_data, indent=2)}

Return a JSON object with this EXACT structure. ALWAYS produce a _thought_chain string to critically review the work step-by-step first.
{{
    "_thought_chain": "Step-by-step reasoning: 1. Evaluate accuracy 2. Check visuals 3. Check audio 4. Check pacing",
    "dimensions": [
        {{
            "dimension": "factual_accuracy",
            "score": 0.95,
            "feedback": "Specific feedback about factual accuracy"
        }},
        {{
            "dimension": "visual_alignment",
            "score": 0.88,
            "feedback": "Specific feedback about visual-narration alignment"
        }},
        {{
            "dimension": "engagement",
            "score": 0.90,
            "feedback": "Specific feedback about hook, pacing, and engagement"
        }},
        {{
            "dimension": "audio_quality",
            "score": 0.92,
            "feedback": "Specific feedback about voice quality and pacing"
        }},
        {{
            "dimension": "pacing",
            "score": 0.85,
            "feedback": "Specific feedback about overall pacing"
        }}
    ],
    "hard_fails": [],
    "recommendations": ["Specific improvement suggestions"]
}}

SCORING CRITERIA:
- factual_accuracy (weight 0.35): Are facts consistent? No hallucinations? Numbers accurate?
- visual_alignment (weight 0.25): Do visuals match narration? Are overlays meaningful?
- engagement (weight 0.20): Is there a strong hook? Good transitions? CTA present?
- audio_quality (weight 0.10): Is WPM in range (130-170)? No awkward pauses?
- pacing (weight 0.10): Is duration 60-120s? Good flow between segments?

HARD FAIL CONDITIONS (if any apply, add to hard_fails):
- "hallucinated_facts" — if any facts seem made up
- "missing_hook" — if no attention-grabbing opening
- "visual_mismatch" — if visuals don't match narration
- "audio_silence_gt_2s" — if there are silence gaps > 2 seconds
- "static_screen_gt_5s" — if any scene is static for > 5 seconds

Score each dimension 0.0 to 1.0. Be objective and critical."""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": QA_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )

            raw = response.choices[0].message.content.strip()
            data = parse_llm_json(raw)
            break
        except Exception as e:
            last_error = e
            logger.warning(f"QA validation attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_error

    # Build dimension scores
    dimension_scores = []
    for dim in data.get("dimensions", []):
        name = dim["dimension"]
        score = float(dim["score"])
        weight = SCORING_WEIGHTS.get(name, 0.0)
        dimension_scores.append(QADimensionScore(
            dimension=name,
            score=score,
            weight=weight,
            weighted_score=score * weight,
            feedback=dim.get("feedback", ""),
        ))

    # Calculate overall score
    overall_score = sum(d.weighted_score for d in dimension_scores)
    hard_fails = data.get("hard_fails", [])
    recommendations = data.get("recommendations", [])

    # Additional programmatic checks
    hard_fails.extend(_check_hard_fails(script, visual_plan, voice_result))

    passed = overall_score >= QA_MINIMUM_SCORE and len(hard_fails) == 0

    report = QAReport(
        overall_score=overall_score,
        passed=passed,
        dimension_scores=dimension_scores,
        hard_fail_triggered=list(set(hard_fails)),
        recommendations=recommendations,
        iteration=iteration,
    )

    logger.info(
        f"QA Report (iteration {iteration}): score={overall_score:.3f}, "
        f"passed={passed}, hard_fails={hard_fails}"
    )

    return report


def _check_hard_fails(script: Script, visual_plan: VisualPlan,
                       voice_result: VoiceResult) -> list[str]:
    """Programmatic hard-fail checks."""
    fails = []

    # Missing hook
    if not any(s.is_hook for s in script.segments):
        fails.append("missing_hook")

    # Duration out of range
    if voice_result.total_duration < VIDEO_MIN_DURATION * 0.7:
        fails.append("bad_pacing")
    if voice_result.total_duration > VIDEO_MAX_DURATION * 1.3:
        fails.append("bad_pacing")

    # Too few scenes
    if visual_plan.total_scenes < MIN_SCENE_CHANGES:
        fails.append("visual_mismatch")

    return fails
