"""SQLAlchemy models for users and articles."""

from sqlalchemy import Column, Integer, String, JSON, DateTime, func
from app.database import Base


class User(Base):
    """User profiles — linked to Clerk user IDs."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    clerk_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)

    # Personalization fields
    role = Column(String, default="student")
    interests = Column(JSON, default=list)
    level = Column(String, default="beginner")
    engagement = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Article(Base):
    """Stored news articles from RSS feeds."""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    summary = Column(String)
    url = Column(String, unique=True)
    source = Column(String)
    category = Column(String)
    published = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
