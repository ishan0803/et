from groq import Groq
from app.config import settings
import json
import re
import asyncio

# Optional Redis (if you already have service)
try:
    from app.services.redis_service import redis_client
except:
    redis_client = None


# ─────────────────────────────────────────────
# 🔧 GROQ SETUP
# ─────────────────────────────────────────────

client = None

if settings.GROQ_API_KEY:
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        print("✅ Groq AI connected")
    except Exception as e:
        print(f"⚠️ Groq setup failed: {e}")
else:
    print("⚠️ No GROQ_API_KEY found — using mock AI")


# ─────────────────────────────────────────────
# 🧠 PROMPTS (IMPROVED)
# ─────────────────────────────────────────────

def build_prompt(article, profile):
    role = profile.get("role", "student")
    level = profile.get("level", "beginner")
    interests = ", ".join(profile.get("interests", []))
    if not interests:
        interests = "general business trends"

    return f"""
You are an AI-powered personalized news assistant.

User Profile:
- Role: {role}
- Experience Level: {level}
- Interests: {interests}

News Article:
Title: {article.get("title")}
Summary: {article.get("summary", "")[:500]}

CRITICAL INSTRUCTIONS:
1. MUST explicitly mention the user's interests: {interests}
2. MUST explain the concrete impact on {interests} (not generic)
3. MUST provide specific, actionable insights tailored to their role
4. NEVER use generic phrases: "this is useful", "this is important", "this helps understand", "this is significant"
5. ALWAYS ground explanations in how it directly affects their {interests}
6. Generate responses that are specific to {interests}, not vague or broadly applicable

OUTPUT STRICTLY IN JSON:

For STUDENT:
{{
  "headline": "...",
  "simple_explanation": "... (in 1-2 sentences, specific to {interests})",
  "why_it_matters": "Directly impacts {interests} because... (specific mechanism, not generic)",
  "key_takeaway": "... (concrete, actionable insight for someone interested in {interests})",
  "why_this_article": "Relevant to {interests} because..."
}}

For INVESTOR:
{{
  "headline": "...",
  "market_impact": "... (specific sectors related to {interests})",
  "stocks_to_watch": "... (companies directly tied to {interests})",
  "investor_action": "Because of {interests}, consider... (specific action)",
  "why_this_article": "Relevant to {interests} because..."
}}

For FOUNDER:
{{
  "headline": "...",
  "startup_relevance": "For founders focused on {interests}: ... (specific relevance)",
  "opportunity_or_threat": "... (concrete effect on {interests} businesses)",
  "action_for_founders": "For {interests} startups: ... (specific action to take)",
  "why_this_article": "Relevant to {interests} because..."
}}
"""


# ─────────────────────────────────────────────
# 🚀 MAIN FUNCTION
# ─────────────────────────────────────────────

async def rewrite_article_for_user(article: dict, profile: dict) -> dict:
    role = profile.get("role", "student")

    # 🔥 Redis Cache (huge performance boost)
    cache_key = f"ai:{role}:{article.get('title')[:50]}"

    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return {
                **article,
                "personalized": json.loads(cached),
                "ai_generated": True,
                "cached": True
            }

    # Build prompt
    prompt = build_prompt(article, profile)

    # Call AI
    if client:
        result = await _call_groq(prompt, article, role)
    else:
        result = _mock_rewrite(article, role, profile)

    # Store in cache
    if redis_client and result.get("personalized"):
        redis_client.setex(cache_key, 3600, json.dumps(result["personalized"]))

    return result


# ─────────────────────────────────────────────
# 🤖 GROQ CALL
# ─────────────────────────────────────────────

async def _call_groq(prompt: str, article: dict, role: str) -> dict:
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # you can switch to gpt-oss-120b if available
            messages=[
                {"role": "system", "content": "You generate personalized news insights."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )

        text = response.choices[0].message.content.strip()

        # Extract JSON safely
        json_match = re.search(r'\{.*\}', text, re.DOTALL)

        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parsed = {
                "headline": article.get("title"),
                "error": "JSON parsing failed",
                "raw_output": text[:300]
            }

        return {
            **article,
            "personalized": parsed,
            "ai_generated": True,
        }

    except Exception as e:
        print(f"⚠️ Groq error: {e}")
        return _mock_rewrite(article, role, {})


# ─────────────────────────────────────────────
# 🧪 MOCK FALLBACK (SMART)
# ─────────────────────────────────────────────

def _mock_rewrite(article: dict, role: str, profile: dict) -> dict:
    title = article.get("title", "")
    summary = article.get("summary", "")
    interests = ", ".join(profile.get("interests", [])) or "general business trends"

    base = {
        "headline": title,
        "why_this_article": f"Directly relevant to your focus on {interests}."
    }

    mock = {
        "student": {
            **base,
            "simple_explanation": f"This news affects {interests} by: {summary[:150]}",
            "why_it_matters": f"For your {interests} focus, the key impact is: {summary[:180]}",
            "key_takeaway": f"To advance in {interests}, you should track: {title[:60]}."
        },

        "investor": {
            **base,
            "market_impact": f"For {interests} investors: {summary[:160]}",
            "stocks_to_watch": f"Companies operating in {interests} sector should be monitored.",
            "investor_action": f"Given {interests} dynamics, evaluate entry opportunities based on this trend."
        },

        "founder": {
            **base,
            "startup_relevance": f"For {interests} startups: {summary[:160]}",
            "opportunity_or_threat": f"This directly shifts the {interests} landscape by affecting...",
            "action_for_founders": f"If building in {interests}, adjust positioning because: {summary[:120]}"
        }
    }

    return {
        **article,
        "personalized": mock.get(role, mock["student"]),
        "ai_generated": False,
    }