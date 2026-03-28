"""Autonomous Scraping Agent."""

import asyncio
import uuid
from app.intel.llm_client import ask_llm_fast
from app.intel.scraper import scrape_topic
from app.models.intel import ArticleInput

AGENT_SYSTEM_PROMPT = """You are an autonomous AI Scraping Agent.
You will receive a topic and the current state of gathered articles. 

You must return a JSON response depending on the action required:

IF Action == 'Generate Queries':
{
  "action": "search",
  "queries": ["keyword1 keyword2", "keyword3"]
}
IMPORTANT: Queries MUST be short keyword-only terms (1-3 words max). 
Do NOT use full sentences, questions, or long phrases.
Good: "RBI rate cut", "Adani Hindenburg"
Bad: "What is the impact of RBI rate cuts on the Indian economy?"

IF Action == 'Evaluate Articles':
{
  "action": "evaluate",
  "kept_articles": ["id1", "id2"]
}

IF Action == 'Analyze Gaps':
{
  "action": "analyze",
  "gaps_found": true/false,
  "reasoning": "Explain why gaps exist or not."
}
"""


class ScrapingAgent:
    def __init__(self, topic: str):
        self.topic = topic
        self.saved_articles = []
        self.seen_urls = set()
        self.max_iterations = 2

    async def run(self) -> list[ArticleInput]:
        """Execute the agentic scraping loop."""
        print(f"🕵️ Agent started for topic: {self.topic}")

        for iteration in range(self.max_iterations):
            print(f"🔄 Iteration {iteration+1}/{self.max_iterations}")

            queries = await self._generate_queries(iteration)

            new_articles = []
            for query in queries:
                print(f"🔍 Scraping: {query}")
                scraped = await scrape_topic(query, max_articles=4)
                await asyncio.sleep(1.0)
                for art in scraped:
                    if art["url"] not in self.seen_urls:
                        art["temp_id"] = str(uuid.uuid4())
                        self.seen_urls.add(art["url"])
                        new_articles.append(art)

            if new_articles:
                relevant_ids = await self._evaluate_relevance(new_articles)
                for art in new_articles:
                    if art["temp_id"] in relevant_ids:
                        self.saved_articles.append(art)

            if iteration < self.max_iterations - 1:
                has_gaps = await self._analyze_gaps()
                if not has_gaps:
                    print("✅ Sufficient data collected. Short-circuiting loop.")
                    break
                else:
                    await asyncio.sleep(2.0)

        final_list = []
        for art in self.saved_articles:
            final_list.append(ArticleInput(
                id=art.get("temp_id", str(uuid.uuid4())),
                title=art.get("title", "Untitled"),
                content=art.get("content", ""),
                url=art.get("url", ""),
                date=art.get("date", "Unknown"),
            ))

        print(f"🎯 Agent finished. Total articles: {len(final_list)}")
        return final_list

    async def _generate_queries(self, iteration: int) -> list[str]:
        prompt = f"Topic: {self.topic}\nIteration: {iteration}\nCurrently Saved Articles: {len(self.saved_articles)}\n\nPlease generate 2 search queries."
        if iteration == 0:
            prompt += "\nAssume we are just starting. Provide broad initial queries."
        else:
            prompt += "\nLook for specific, contrarian, or missing perspectives based on the topic."

        res = await ask_llm_fast(AGENT_SYSTEM_PROMPT, prompt)
        return res.get("queries", [self.topic])

    async def _evaluate_relevance(self, articles: list[dict]) -> list[str]:
        texts = "".join([f"ID: {a['temp_id']} | Title: {a['title']}\n" for a in articles])
        prompt = f"Topic: {self.topic}\nArticles to evaluate:\n{texts}\n\nReturn 'action': 'evaluate' and a list of 'kept_articles' IDs that closely match the topic."
        res = await ask_llm_fast(AGENT_SYSTEM_PROMPT, prompt)
        return res.get("kept_articles", [])

    async def _analyze_gaps(self) -> bool:
        if len(self.saved_articles) < 3:
            return True

        titles = [a["title"] for a in self.saved_articles]
        prompt = f"Topic: {self.topic}\nSaved Article Titles:\n{titles}\n\nAre there critical missing angles or lack of volume? Reply with action: analyze and gaps_found true/false."
        res = await ask_llm_fast(AGENT_SYSTEM_PROMPT, prompt)
        return res.get("gaps_found", True)
