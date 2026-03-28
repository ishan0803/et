"""Groq LLM client wrapper with two-tier model strategy.

- ask_llm()      → openai/gpt-oss-120b  (deep reasoning: extraction, analysis, briefing, Q&A)
- ask_llm_fast() → llama-3.3-70b-versatile  (worker/validation: query gen, relevance check, gap analysis)
"""

import json
import re
import os
from groq import AsyncGroq
from app.config import settings

_client = None

MODEL_DEEP = "openai/gpt-oss-120b"
MODEL_FAST = "llama-3.3-70b-versatile"


def _get_client() -> AsyncGroq:
    """Lazily init the async Groq client."""
    global _client
    if _client is None:
        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
        _client = AsyncGroq(api_key=api_key)
    return _client


def _clean_json(text: str) -> str:
    """Strip markdown fences and whitespace before parsing."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


async def _call(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> dict | list:
    """Internal: send a chat completion and return parsed JSON."""
    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    return json.loads(_clean_json(content))


async def ask_llm(system_prompt: str, user_prompt: str) -> dict | list:
    """Deep reasoning model (gpt-oss-120b) — for extraction, analysis, briefings, Q&A."""
    return await _call(MODEL_DEEP, system_prompt, user_prompt, temperature=0.3)


async def ask_llm_fast(system_prompt: str, user_prompt: str) -> dict | list:
    """Fast worker model (llama-3.3-70b) — for query generation, validation, gap checks."""
    return await _call(MODEL_FAST, system_prompt, user_prompt, temperature=0.5)
