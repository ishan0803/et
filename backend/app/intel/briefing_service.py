"""Generates intelligence briefings using Groq LLM (no Gemini)."""

from app.intel.llm_client import ask_llm

SYSTEM_PROMPT = """You are an Economic Times financial analyst.

Create a deep intelligence briefing from the provided articles.
Write it in detail and easy language for the user to understand.

Return ONLY valid JSON with the following exact structure:
{
  "briefing": {
    "Summary": "A concise overview",
    "Key Insights": ["Insight 1", "Insight 2"],
    "Market Impact": "Description of market impact",
    "What To Watch": "Future outlook",
    "Controversies / Concerns": "Controversies / Concerns"
  },
  "followups": ["Question 1", "Question 2", "Question 3"]
}

Synthesize across all articles."""


async def generate_briefing(articles: list[dict]):
    articles_text = ""
    for i, article in enumerate(articles):
        articles_text += f"""
Article {i+1}
Title: {article.get('title', '')}
Content: {article.get('content', '')}
"""

    user_prompt = f"Below are multiple articles about the SAME topic.\n\n{articles_text}"

    try:
        parsed = await ask_llm(SYSTEM_PROMPT, user_prompt)
        return {
            "briefing": parsed.get("briefing", {}),
            "followups": parsed.get("followups", []),
        }
    except Exception as e:
        print("Parsing error:", e)
        return {
            "briefing": {"Summary": "Failed to parse API response"},
            "followups": [],
        }
