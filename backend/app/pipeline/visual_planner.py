"""Visual planner using Gemini 2.5 Flash."""

import json
import logging
import time
from groq import Groq

from app.config import settings, MIN_SCENE_CHANGES, MOTION_TYPES
from app.models import Script, VisualPlan, SceneVisual, MotionType
from app.utils.helpers import parse_llm_json

logger = logging.getLogger(__name__)

VISUAL_SYSTEM_PROMPT = """You are a professional video director planning visuals for a news broadcast video. You create scene-by-scene visual plans that are cinematic, engaging, and semantically matched to the narration.

RULES:
1. Each scene must have a UNIQUE visual — no repeated visuals consecutively
2. Every scene MUST include a short headline and exactly 3 bullet points summarizing the segment
3. Visuals must semantically match the script segment
4. Each scene must have at least one motion element (zoom, pan, or ken burns)
5. Include data chart scenes when numeric data is present
6. Scenes should feel like a professional news broadcast
7. Search queries MUST be highly specific to the geopolitical or financial subject (e.g. "US Capitol Building", "Iran Flag", "Naval Warship"). Avoid generic terms.
8. Vary motion types across scenes for visual interest
9. Headline should be punchy (1-5 words). Bullet points should be concise (5-10 words max)"""


def generate_visual_plan(script: Script, retry_context: str = None) -> VisualPlan:
    """Generate a visual plan from the script using Gemini."""

    client = Groq(api_key=settings.groq_api_key)

    segments_text = "\n".join([
        f"Segment {s.segment_id}: \"{s.text}\" (duration: {s.duration_estimate}s, "
        f"hook={s.is_hook}, cta={s.is_cta})"
        for s in script.segments
    ])

    numeric_info = ""
    if script.numeric_data:
        numeric_info = "\nNumeric data available for charts:\n" + json.dumps(script.numeric_data, indent=2)

    user_prompt = f"""Create a scene-by-scene visual plan for this news video script.

Topic: {script.topic}
Title: {script.title}

Script segments:
{segments_text}
{numeric_info}

{"REVISION NOTES: " + retry_context if retry_context else ""}

Return a JSON object with this EXACT structure. ALWAYS produce a _thought_chain string to describe your visual direction reasoning first.
{{
    "_thought_chain": "Step-by-step reasoning: 1. Match script themes 2. Select stock queries 3. Decide graph placements",
    "scenes": [
        {{
            "scene_id": 1,
            "segment_ids": [1],
            "visual_description": "Detailed description of what appears on screen",
            "search_query": "specific stock photo search terms",
            "headline": "KEY POINT",
            "bullet_points": ["Fact 1", "Fact 2", "Fact 3"],
            "motion_type": "ken_burns",
            "has_chart": false,
            "chart_data": null,
            "duration": 8.0
        }}
    ],
    "total_scenes": 8,
    "total_duration": 90.0
}}

MOTION TYPES: zoom_in, zoom_out, pan_left, pan_right, pan_up, ken_burns

For scenes with numeric data, set has_chart=true and include:
"chart_data": {{
    "chart_type": "bar",
    "title": "Chart title",
    "data_labels": ["Label 1", "Label 2"],
    "data_values": [10, 20],
    "highlight_index": 1,
    "unit": "%"
}}

REQUIREMENTS:
- Minimum {MIN_SCENE_CHANGES} scenes
- Each scene covers 1-2 script segments
- No two consecutive scenes should have similar search queries
- Headline and bullet points should be uniquely generated for every scene
- Vary the motion types across scenes
- CRITICAL: For images, Search queries MUST be literal, physical nouns showing real-world objects or scenes, and MUST BE HIGHLY RELEVANT to the specific story (e.g. "US Capitol building", "Iran military ships", "Tehran city"). Do NOT use generic abstract metaphors like "meeting", "rope", "cable", or "handshake".
- CRITICAL: For charts, you MUST use the EXACT numeric data given in the `Numeric data available for charts` section. Do NOT hallucinate data, invent fictional percentages, or extrapolate. If the article says 20%, use 20.
- AGENTIC CHART LOGIC: You must dynamically select the best `chart_type` based on the data:
  * "stat_highlight": Use this when there is ONLY ONE critical number/statistic (e.g. "28 days", "1 Million"). Do NOT use "bar" for single values!
  * "bar": Use for comparing 2-5 distinct categorical values.
  * "pie": Use ONLY for percentages that add up to exactly 100%.
  * "line": Use for trends across time (e.g. 3+ temporal data points)."""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": VISUAL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=8192,
                response_format={"type": "json_object"}
            )

            raw = response.choices[0].message.content.strip()
            logger.info(f"Visual plan raw response length: {len(raw)}")
            data = parse_llm_json(raw)
            
            scenes = []
            for scene_data in data["scenes"]:
                # Validate motion type
                motion = scene_data.get("motion_type", "ken_burns")
                try:
                    motion_type = MotionType(motion)
                except ValueError:
                    motion_type = MotionType.KEN_BURNS

                scenes.append(SceneVisual(
                    scene_id=scene_data["scene_id"],
                    segment_ids=scene_data["segment_ids"],
                    visual_description=scene_data["visual_description"],
                    search_query=scene_data["search_query"],
                    headline=scene_data.get("headline", "BREAKING NEWS"),
                    bullet_points=scene_data.get("bullet_points", ["Key details developing", "More updates soon", "Stay tuned"]),
                    motion_type=motion_type,
                    has_chart=scene_data.get("has_chart", False),
                    chart_config=scene_data.get("chart_data"),
                    duration=scene_data["duration"],
                ))
            
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Visual plan attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_error

    plan = VisualPlan(
        scenes=scenes,
        total_scenes=len(scenes),
        total_duration=sum(s.duration for s in scenes),
    )

    _validate_visual_plan(plan, script)
    return plan


def _validate_visual_plan(plan: VisualPlan, script: Script):
    """Validate the visual plan."""
    if plan.total_scenes < MIN_SCENE_CHANGES:
        logger.warning(f"Too few scenes: {plan.total_scenes} < {MIN_SCENE_CHANGES}")

    # Check headline uniqueness
    headlines = [s.headline for s in plan.scenes]
    if len(set(headlines)) < len(headlines) * 0.7:
        logger.warning("Many duplicate headlines detected")

    # Check consecutive visual repetition
    for i in range(1, len(plan.scenes)):
        if plan.scenes[i].search_query == plan.scenes[i-1].search_query:
            logger.warning(f"Consecutive scenes {i-1} and {i} have same search query")

    logger.info(
        f"Visual plan validated: {plan.total_scenes} scenes, "
        f"{plan.total_duration:.1f}s total"
    )
