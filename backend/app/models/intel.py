"""Pydantic models for the intelligence hub (story arc & news navigator)."""

from pydantic import BaseModel, Field
from typing import Optional


class ArticleInput(BaseModel):
    id: str
    title: str
    content: str
    url: Optional[str] = None
    date: Optional[str] = None


class StoryRequest(BaseModel):
    topic: str
    articles: list[ArticleInput]


class TimelineEvent(BaseModel):
    event_id: str
    title: str
    date: str
    summary: str
    sentiment: str = Field(description="positive | negative | neutral")
    entities: list[str] = []
    source_articles: list[str] = []
    stance: Optional[str] = None


class KeyPlayer(BaseModel):
    name: str
    role: str


class SentimentOverview(BaseModel):
    trend: list[str] = []
    overall: str = Field(description="positive | negative | mixed | neutral")


class ContrarianInsights(BaseModel):
    mainstream: str
    contrarian: list[str] = []


class StoryArcResponse(BaseModel):
    story_summary: str
    timeline: list[TimelineEvent] = []
    key_players: list[KeyPlayer] = []
    sentiment_overview: SentimentOverview
    contrarian_insights: ContrarianInsights
    what_to_watch: list[str] = []
    articles: list[ArticleInput] = []
