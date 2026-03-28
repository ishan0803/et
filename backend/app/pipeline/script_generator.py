"""Script generator using Gemini 2.5 Flash."""

import json
import logging
import time
from groq import Groq

from app.config import (
    settings, VIDEO_MIN_DURATION, VIDEO_MAX_DURATION,
    MAX_SENTENCE_WORDS, MIN_WPM, MAX_WPM,
    TRANSITION_INTERVAL_SEC, HOOK_WITHIN_SECONDS,
)
from app.models import Script, ScriptSegment
from app.utils.helpers import count_words, estimate_duration, parse_llm_json

logger = logging.getLogger(__name__)

SCRIPT_SYSTEM_PROMPT = """You are a professional news video scriptwriter. You write scripts for short-form vertical (9:16) news videos. Your scripts are engaging, factual, and designed for maximum viewer retention.

RULES:
1. Start with a powerful hook in the FIRST 2 sentences that grabs attention immediately
2. Every sentence must be 15 words or fewer
3. Use simple, clear language — no jargon
4. Include transition phrases every ~15 seconds of content
5. End with a clear call to action (subscribe, follow, share)
6. Total script duration must be between 60-120 seconds when read at 150 WPM
7. Extract all numeric data, statistics, and percentages for chart generation
8. Mark emphasis words that should be stressed in narration
9. Each segment should be 2-4 sentences covering one key point
10. Use active voice and present tense where possible"""


def generate_script(topic: str, source_url: str = None, scraped_text: str = None, retry_context: str = None) -> Script:
    """Generate a news video script using Gemini 2.5 Flash."""

    client = Groq(api_key=settings.groq_api_key)

    context_prompt = ""
    if scraped_text:
        context_prompt = f"Here is the exact article content to adapt:\n{scraped_text}\n"
    elif source_url:
        context_prompt = f"Source article: {source_url}\n"
    else:
        context_prompt = "Research this topic using your knowledge.\n"

    user_prompt = f"""Write a news video script about: {topic}

{context_prompt}
{"REVISION NOTES: " + retry_context if retry_context else ""}

Return a JSON object with this EXACT structure. ALWAYS produce a _thought_chain string to reason through your logic before writing.
{{
    "_thought_chain": "Step-by-step reasoning: 1. Core angle 2. Hook 3. Segments 4. CTA",
    "topic": "{topic}",
    "title": "Short catchy title for the video (max 8 words)",
    "segments": [
        {{
            "segment_id": 1,
            "text": "The narration text for this segment",
            "duration_estimate": 5.0,
            "is_hook": true,
            "is_cta": false,
            "is_transition": false,
            "emphasis_words": ["key", "words"]
        }}
    ],
    "total_word_count": 250,
    "estimated_duration": 90,
    "key_facts": ["Fact 1", "Fact 2"],
    "numeric_data": [
        {{
            "label": "Description",
            "value": 42,
            "unit": "%",
            "context": "What this number represents"
        }}
    ]
}}

IMPORTANT:
- Target 160-200 words total (for STRICTLY 60-110 seconds at ~150 WPM)
- Video MUST NOT exceed 120 seconds under any circumstances
- Include 5-8 segments
- First segment MUST be the hook (is_hook: true)
- Last segment MUST be CTA (is_cta: true)
- At least 1 segment should be a transition (is_transition: true)
- Extract ALL numbers and statistics into numeric_data array
- Each segment text should be 2-3 sentences, each sentence <= 15 words"""

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=8192,
                response_format={"type": "json_object"}
            )

            raw = response.choices[0].message.content.strip()
            logger.info(f"Script generation raw response length: {len(raw)}")

            data = parse_llm_json(raw)
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Script generation attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_error

    # Build typed model
    segments = [ScriptSegment(**seg) for seg in data["segments"]]

    # Calculate actual word count and duration
    total_words = sum(count_words(seg.text) for seg in segments)
    est_duration = estimate_duration(total_words, 150)

    script = Script(
        topic=data.get("topic", topic),
        title=data.get("title", topic[:50]),
        segments=segments,
        total_word_count=total_words,
        estimated_duration=est_duration,
        key_facts=data.get("key_facts", []),
        numeric_data=data.get("numeric_data", []),
    )

    # Validate
    _validate_script(script)

    return script


def _validate_script(script: Script):
    """Post-script validation checks."""
    # Duration check
    if script.estimated_duration < VIDEO_MIN_DURATION * 0.8:
        logger.warning(f"Script too short: {script.estimated_duration:.1f}s")
    if script.estimated_duration > VIDEO_MAX_DURATION * 1.2:
        logger.warning(f"Script too long: {script.estimated_duration:.1f}s")

    # Hook check
    if not any(s.is_hook for s in script.segments):
        logger.warning("No hook segment found, marking first segment as hook")
        script.segments[0].is_hook = True

    # CTA check
    if not any(s.is_cta for s in script.segments):
        logger.warning("No CTA segment found, marking last segment as CTA")
        script.segments[-1].is_cta = True

    # Sentence length check
    for seg in script.segments:
        sentences = [s.strip() for s in seg.text.split('.') if s.strip()]
        for sentence in sentences:
            wc = count_words(sentence)
            if wc > MAX_SENTENCE_WORDS + 5:
                logger.warning(f"Long sentence ({wc} words): {sentence[:50]}...")

    logger.info(
        f"Script validated: {script.total_word_count} words, "
        f"{script.estimated_duration:.1f}s, {len(script.segments)} segments"
    )
