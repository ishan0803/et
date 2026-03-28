import feedparser
import numpy as np
from datetime import datetime
from dateutil import parser as dateparser
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

"""
NEWS SERVICE — TF-IDF SEMANTIC SCORING

WHY TF-IDF INSTEAD OF SENTENCE-TRANSFORMERS?
- sentence-transformers pulls PyTorch (~2GB) → 30min Docker build
- TF-IDF from scikit-learn installs in seconds, no model download
- Still genuinely semantic: rare/specific words score higher than
  common ones. "venture capital" in an article about startups scores
  higher than "the" appearing 50 times.

INTEREST EXPANSION:
- User types "AI" → we expand to 15 related terms automatically
- User types "startups" → expands to "funding", "venture", "unicorn" etc.
- This makes matching robust without keyword hardcoding

SCORING:
- Build a combined query from user interests + expanded terms
- TF-IDF vectorize all articles + the query
- Cosine similarity → 0.0 (unrelated) to 1.0 (identical topic)
- Threshold: >= 0.08 strong match, >= 0.04 fallback
  (TF-IDF scores are naturally lower than neural embeddings)
"""

# NEW
GOOGLE_RSS_BASE = "https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q="

ET_RSS_FEEDS = {
    "markets":    GOOGLE_RSS_BASE + "stock+market+India+NSE+BSE",
    "tech":       GOOGLE_RSS_BASE + "technology+AI+India",
    "startups":   GOOGLE_RSS_BASE + "startup+funding+India+venture+capital",
    "finance":    GOOGLE_RSS_BASE + "Indian+economy+finance+RBI",
    "healthcare": GOOGLE_RSS_BASE + "healthcare+pharma+biotech+India",
    "crypto":     GOOGLE_RSS_BASE + "cryptocurrency+bitcoin+blockchain+India",
    "general":    GOOGLE_RSS_BASE + "India+business+news",
}

# ── Interest expansion dictionary ────────────────────────────────
# When user says "AI", we also look for all these related terms.
# This is what makes it "semantic" — we understand what topics mean.
INTEREST_EXPANSION = {
    "ai":           ["artificial intelligence", "machine learning", "deep learning",
                     "LLM", "neural network", "GPT", "generative", "model",
                     "algorithm", "automation", "chatbot", "NLP"],
    "startups":     ["startup", "funding", "seed", "series", "venture capital",
                     "VC", "unicorn", "founder", "entrepreneur", "investment",
                     "raise", "valuation", "pitch", "accelerator", "incubator"],
    "markets":      ["stocks", "equity", "sensex", "nifty", "BSE", "NSE",
                     "shares", "trading", "market", "index", "rally", "bull",
                     "bear", "IPO", "listed"],
    "crypto":       ["bitcoin", "ethereum", "blockchain", "crypto", "web3",
                     "defi", "NFT", "token", "coin", "wallet", "exchange"],
    "finance":      ["RBI", "interest rate", "inflation", "GDP", "budget",
                     "economy", "fiscal", "monetary", "bank", "loan", "credit",
                     "debt", "revenue", "profit", "earnings"],
    "tech":         ["technology", "software", "SaaS", "cloud", "cybersecurity",
                     "app", "platform", "digital", "internet", "data", "API",
                     "developer", "code", "product"],
    "policy":       ["government", "regulation", "SEBI", "ministry", "law",
                     "compliance", "reform", "bill", "parliament", "scheme"],
    "investing":    ["portfolio", "mutual fund", "ETF", "dividend", "returns",
                     "asset", "wealth", "fund", "NAV", "SIP", "XIRR"],
    "ecommerce":    ["ecommerce", "e-commerce", "retail", "amazon", "flipkart",
                     "online shopping", "marketplace", "D2C", "logistics"],
    "healthcare":   ["health", "pharma", "medicine", "hospital", "drug",
                     "FDA", "clinical", "biotech", "medtech", "patient"],
}


def expand_interests(interests: List[str]) -> List[str]:
    """
    Take user's interest list and expand each to related terms.

    Example:
      ["AI", "startups"]
      → ["AI", "artificial intelligence", "machine learning", "LLM", ...
         "startup", "funding", "venture capital", "unicorn", ...]
    """
    expanded = list(interests)  # start with original interests

    for interest in interests:
        key = interest.lower()
        if key in INTEREST_EXPANSION:
            expanded.extend(INTEREST_EXPANSION[key])
        else:
            # Unknown interest — keep it as-is, TF-IDF will handle it
            expanded.append(interest)

    # Deduplicate while preserving order
    seen = set()
    result = []
    for term in expanded:
        if term.lower() not in seen:
            seen.add(term.lower())
            result.append(term)

    return result


def build_query(profile: Dict) -> str:
    """
    Build a rich text query from the user's profile.
    More words = better TF-IDF matching surface.

    Example output:
    "AI startups artificial intelligence machine learning LLM funding
     venture capital unicorn series student news articles"
    """
    interests   = profile.get("interests", [])
    role        = profile.get("role", "reader")
    expanded    = expand_interests(interests)

    # Combine everything into one query string
    query_parts = expanded + [role, "news", "articles", "India", "business"]
    return " ".join(query_parts)


def article_to_text(article: Dict) -> str:
    """
    Convert an article dict to a single string for TF-IDF.
    Title is repeated 3x to give it more weight over summary.
    """
    title   = article.get("title",   "")
    summary = article.get("summary", "")[:400]
    return f"{title} {title} {title} {summary}"


def parse_date(entry) -> datetime:
    """Safely parse publish date from RSS feed entry."""
    try:
        if hasattr(entry, "published"):
            return dateparser.parse(entry.published)
    except Exception:
        pass
    return datetime.utcnow()


async def fetch_all_feeds() -> List[Dict]:
    """
    Fetch articles from all ET RSS feeds.
    No keyword tagging — semantic scoring handles relevance.
    """
    all_articles = []

    for feed_name, feed_url in ET_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:15]:
                article = {
                    "title":     getattr(entry, "title",   ""),
                    "summary":   getattr(entry, "summary", ""),
                    "url":       getattr(entry, "link",    ""),
                    # NEW — Google RSS includes the publisher in the entry itself
                    "source": getattr(entry, "source", {}).get("title", feed_name.capitalize()) 
                        if hasattr(getattr(entry, "source", None), "get") 
                        else feed_name.capitalize(),
                    "category":  feed_name,
                    "tags":      [feed_name],  # just source feed, no keyword guessing
                    "published": parse_date(entry),
                }

                if article["title"] and article["url"]:
                    all_articles.append(article)

        except Exception as e:
            print(f"⚠️  Failed to fetch {feed_name} feed: {e}")
            continue

    print(f"✅  Fetched {len(all_articles)} articles from ET RSS feeds")
    return all_articles


def rank_articles_for_user(
    articles: List[Dict],
    profile:  Dict,
    top_n:    int = 10,
) -> List[Dict]:
    """
    Per-interest scoring — scores each interest separately,
    takes the MAX score across all interests per article.

    WHY THIS IS BETTER THAN ONE COMBINED QUERY:
    - Combined query "AI startups healthcare": an AI article scores ~0.04
      because it only matches 1 of 3 interests
    - Per-interest: same article scores 0.09 for "AI" alone → that's its score
    - Each article is judged by its BEST matching interest, not average match
    - Healthcare gets its own query → healthcare articles surface separately
    """
    if not articles:
        return []

    interests = profile.get("interests", [])
    role      = profile.get("role", "reader")

    # Prepare article texts once (reused for every interest query)
    article_texts = [article_to_text(a) for a in articles]

    # Track best score per article across all interest queries
    best_scores     = [0.0] * len(articles)
    best_match_for  = [""] * len(articles)   # which interest matched best

    # ── Score per interest separately ────────────────────────────
    for interest in interests:
        # Build a focused single-interest query
        expanded     = expand_interests([interest])
        query_parts  = expanded + [role, "news", "India", "business"]
        query        = " ".join(query_parts)

        print(f"\n🔍 Scoring for interest: '{interest}'")
        print(f"   Query: '{query[:70]}...'")

        # Fit TF-IDF on articles + this interest's query
        all_texts = article_texts + [query]
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            max_features=8000,
            sublinear_tf=True,
        )
        tfidf_matrix = vectorizer.fit_transform(all_texts)

        query_vec    = tfidf_matrix[-1]
        article_vecs = tfidf_matrix[:-1]
        similarities = cosine_similarity(article_vecs, query_vec).flatten()

        # Update best score for each article
        for i, score in enumerate(similarities):
            s = float(score)
            if s > best_scores[i]:
                best_scores[i]    = s
                best_match_for[i] = interest

    # ── Attach best scores to articles ───────────────────────────
    scored = []
    for article, score, matched_interest in zip(articles, best_scores, best_match_for):
        s = round(score, 4)
        if matched_interest:
            print(f"   [{s:.4f}] ({matched_interest}) {article['title'][:55]}")
        scored.append({
            **article,
            "relevance_score":  s,
            "matched_interest": matched_interest,   # visible in API response
        })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)

    # ── Filter ────────────────────────────────────────────────────
    STRONG_THRESHOLD   = 0.035
    FALLBACK_THRESHOLD = 0.02

    strong = [a for a in scored if a["relevance_score"] >= STRONG_THRESHOLD]

    if len(strong) >= 3:
        result = strong[:top_n]
    elif len(strong) > 0:
        fallback = [
            a for a in scored
            if FALLBACK_THRESHOLD <= a["relevance_score"] < STRONG_THRESHOLD
        ]
        result = (strong + fallback)[:top_n]
    else:
        print("⚠️  No threshold matches — returning top 5 by rank")
        result = scored[:5]

    print(f"\n🎯 Returning {len(result)} articles (from {len(articles)} total)")
    if result:
        print(f"   Score range: {result[-1]['relevance_score']:.4f} – "
              f"{result[0]['relevance_score']:.4f}")

    return result