"""Detect contrarian perspectives from aggregated stances."""

from app.intel.llm_client import ask_llm

SYSTEM_PROMPT = """You are a media analyst specializing in identifying contrarian perspectives.
Given a list of article stances about a topic, identify:
1. The dominant mainstream narrative
2. Any minority or contrarian viewpoints that differ from the mainstream

Return a JSON object:
{
  "mainstream": "Description of the dominant narrative shared by most articles",
  "contrarian": ["Contrarian viewpoint 1", "Contrarian viewpoint 2"]
}
If all stances are similar, return an empty contrarian list and explain the consensus in mainstream."""


async def detect_contrarian(topic: str, stances: list[str]) -> dict:
    """Identify mainstream vs contrarian viewpoints."""
    user_prompt = f"Topic: {topic}\n\nArticle stances:\n"
    for i, stance in enumerate(stances, 1):
        user_prompt += f"{i}. {stance}\n"

    return await ask_llm(SYSTEM_PROMPT, user_prompt)
