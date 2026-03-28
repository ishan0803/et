"""Generate forward-looking predictions from the full story context."""

from app.intel.llm_client import ask_llm

SYSTEM_PROMPT = """You are a strategic analyst. Based on the story context provided, generate 3-5 forward-looking insights — things to watch for next.

Return a JSON object:
{
  "predictions": [
    "Prediction or insight 1",
    "Prediction or insight 2",
    "Prediction or insight 3"
  ]
}
Be specific, actionable, and insightful. Avoid generic statements."""


async def generate_predictions(topic: str, story_summary: str, events_summary: str) -> list[str]:
    """Generate what-to-watch-next predictions."""
    user_prompt = (
        f"Topic: {topic}\n\n"
        f"Story Summary: {story_summary}\n\n"
        f"Key Events:\n{events_summary}"
    )
    result = await ask_llm(SYSTEM_PROMPT, user_prompt)
    return result.get("predictions", [])
