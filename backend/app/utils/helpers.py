"""Shared utility functions."""

import os
import re
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def ensure_dir(path: str) -> str:
    """Ensure a directory exists and return the path."""
    os.makedirs(path, exist_ok=True)
    return path


def job_dir(job_id: str) -> str:
    """Get or create a job-specific working directory."""
    d = os.path.join(settings.tmp_dir, job_id)
    ensure_dir(d)
    return d


def job_output_dir(job_id: str) -> str:
    """Get or create a job-specific output directory."""
    d = os.path.join(settings.output_dir, job_id)
    ensure_dir(d)
    return d


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def estimate_duration(word_count: int, wpm: int = 150) -> float:
    """Estimate speech duration from word count."""
    return (word_count / wpm) * 60


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    return re.sub(r'[^\w\-.]', '_', name)[:60]


def get_font_path(font_name: str) -> str:
    """Get the full path to a font file."""
    path = os.path.join(settings.font_dir, f"{font_name}.ttf")
    if os.path.exists(path):
        return path
    # Fallback to system font
    for fallback in [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(fallback):
            return fallback
    return font_name


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def cleanup_tmp(job_id: str):
    """Clean up temporary files for a job."""
    import shutil
    d = os.path.join(settings.tmp_dir, job_id)
    if os.path.exists(d):
        try:
            shutil.rmtree(d)
        except Exception as e:
            logger.warning(f"Failed to cleanup tmp for {job_id}: {e}")


def parse_llm_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output.

    Handles common issues:
    - Markdown code fences (```json ... ```)
    - Trailing commas
    - Truncated JSON (auto-closes open brackets/braces)
    - Extra text before/after JSON
    """
    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract from first { onward
    first_brace = text.find("{")
    if first_brace == -1:
        raise ValueError(f"No JSON object found. First 200 chars: {raw[:200]}")

    json_str = text[first_brace:]

    # Fix trailing commas before } or ]
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    # Try parsing as-is (may have closing brace)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Handle TRUNCATED JSON: auto-close open brackets/braces
    json_str = _complete_truncated_json(json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Last resort: remove the last incomplete value and close
    # Find the last complete key-value pair or array element
    for trim in range(1, min(200, len(json_str))):
        candidate = json_str[:-trim]
        # Find a good cut point (after a comma, or after a complete value)
        if candidate.rstrip().endswith((",", "}", "]", '"', "e", "l")):
            # Remove trailing comma if present
            candidate = candidate.rstrip()
            if candidate.endswith(","):
                candidate = candidate[:-1]
            completed = _complete_truncated_json(candidate)
            try:
                return json.loads(completed)
            except json.JSONDecodeError:
                continue

    raise ValueError(
        f"Could not parse JSON from LLM response (len={len(raw)}). "
        f"First 200 chars: {raw[:200]}"
    )


def _complete_truncated_json(text: str) -> str:
    """Auto-close open brackets and braces in truncated JSON."""
    # Remove any trailing incomplete string (not closed with ")
    # Count quotes to see if we're inside a string
    in_string = False
    escape = False
    last_good = len(text)

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string

    # If we ended inside a string, close it
    if in_string:
        text = text + '"'

    # Remove trailing partial tokens after last complete structure
    # Trim back to last comma, brace, bracket, colon, or quote
    text = text.rstrip()
    while text and text[-1] not in '{}[],":\n' and not text[-1].isdigit() and text[-1] not in ('e', 'l', 'n'):
        text = text[:-1]

    # Remove trailing comma
    text = text.rstrip()
    if text.endswith(","):
        text = text[:-1]

    # Count open vs close brackets/braces
    stack = []
    in_str = False
    esc = False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            stack.append('}')
        elif ch == '[':
            stack.append(']')
        elif ch in ('}', ']'):
            if stack and stack[-1] == ch:
                stack.pop()

    # Close all open brackets/braces in reverse order
    closing = ''.join(reversed(stack))
    return text + closing


