"""Pydantic data models for the Industry News MCP server."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NewsSource(StrEnum):
    NEWSAPI = "NewsAPI"
    RSS = "RSS"


class NewsArticle(BaseModel):
    """A single news article from any source."""

    id: str
    title: str
    description: str | None = None
    content: str | None = None
    url: str
    source_name: str
    news_source: NewsSource
    published_at: str | None = None
    author: str | None = None
    image_url: str | None = None
    topics: list[str] = Field(default_factory=list)

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "author": self.author,
            "image_url": self.image_url,
            "topics": self.topics,
        }


class DigestSection(BaseModel):
    topic: str
    summary: str
    articles: list[dict[str, Any]]


class WeeklyDigest(BaseModel):
    sections: list[DigestSection]
    total_articles: int
    sources_queried: list[str]
    generated_at: str

    def model_dump_api(self) -> dict[str, Any]:
        return {
            "sections": [
                {
                    "topic": s.topic,
                    "summary": s.summary,
                    "articles": s.articles,
                }
                for s in self.sections
            ],
            "total_articles": self.total_articles,
            "sources_queried": self.sources_queried,
            "generated_at": self.generated_at,
        }


# ── Tool input / output schemas ────────────────────────────────────────────────


class SearchNewsParams(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    language: str = Field(default="en", min_length=2, max_length=5)
    from_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")
    limit: int = Field(default=20, ge=1, le=50)
    sources: list[NewsSource] = Field(default_factory=list)


class SearchNewsResult(BaseModel):
    articles: list[dict[str, Any]]
    total_count: int
    query: str
    sources_queried: list[str]
    fetched_at: str


class GetWeeklyDigestParams(BaseModel):
    topics: list[str] = Field(default_factory=list, max_length=10)
    industry: str = Field(default="technology", max_length=100)
    language: str = Field(default="en", min_length=2, max_length=5)
