"""SignalProcessor — pure computation: aggregates raw MCP data into typed signals.

No I/O, no LLM calls. All logic is deterministic and unit-testable.

Algorithm:
  1. Count skill occurrences across job postings (weight 1 each)
  2. Add GitHub trending repo topics (weight proportional to star velocity)
  3. Add social signal titles (weight 1 each)
  4. Skills with total count >= 3 are TrendDirection.RISING, otherwise STABLE
  5. Return top-N skills ordered by signal count descending
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from agents.market_intelligence.models import (
    IndustrySignal,
    JobPosting,
    SignalType,
    TrendDirection,
    TrendingSkill,
)

# ── Skill category lookup ────────────────────────────────────────────────────

_SKILL_CATEGORY: dict[str, str] = {
    # Languages
    "python": "language",
    "typescript": "language",
    "javascript": "language",
    "go": "language",
    "golang": "language",
    "rust": "language",
    "java": "language",
    "kotlin": "language",
    "scala": "language",
    "swift": "language",
    "c++": "language",
    "c#": "language",
    "ruby": "language",
    "php": "language",
    # Frameworks / Libraries
    "fastapi": "framework",
    "django": "framework",
    "flask": "framework",
    "react": "framework",
    "next.js": "framework",
    "nextjs": "framework",
    "langchain": "framework",
    "langgraph": "framework",
    "pytorch": "framework",
    "tensorflow": "framework",
    "spring": "framework",
    "express": "framework",
    "fastify": "framework",
    # Cloud / Platforms
    "docker": "platform",
    "kubernetes": "platform",
    "aws": "platform",
    "gcp": "platform",
    "azure": "platform",
    # Tools
    "terraform": "tool",
    "ansible": "tool",
    "kafka": "tool",
    "apache kafka": "tool",
    "spark": "tool",
    "apache spark": "tool",
    "redis": "tool",
    "postgresql": "tool",
    "git": "tool",
    "github": "tool",
    "ci/cd": "tool",
    # AI / ML
    "machine learning": "ai_ml",
    "deep learning": "ai_ml",
    "llm": "ai_ml",
    "llms": "ai_ml",
    "llm frameworks": "ai_ml",
    "ai agents": "ai_ml",
    "ai agent": "ai_ml",
    "multi-agent ai": "ai_ml",
    "prompt engineering": "ai_ml",
    "rag": "ai_ml",
    "serverless ml": "ai_ml",
    "rust for ai": "ai_ml",
}

_CANONICAL_NAME: dict[str, str] = {
    "fastapi": "FastAPI",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "llm": "LLM",
    "llms": "LLMs",
    "llm frameworks": "LLM Frameworks",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "ai agents": "AI Agents",
    "ai agent": "AI Agent",
    "multi-agent ai": "Multi-agent AI",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "golang": "Go",
    "apache kafka": "Apache Kafka",
    "apache spark": "Apache Spark",
    "ci/cd": "CI/CD",
    "rag": "RAG",
    "prompt engineering": "Prompt Engineering",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "serverless ml": "Serverless ML",
    "rust for ai": "Rust for AI",
    "postgresql": "PostgreSQL",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "redis": "Redis",
    "github": "GitHub",
    "webassembly": "WebAssembly",
}

# Minimum star velocity to add weight beyond 1
_GITHUB_STARS_PER_WEIGHT = 1_000


class SignalProcessor:
    """Aggregates raw MCP data into typed TrendingSkill and IndustrySignal objects.

    Stateless — create once and call as many times as needed.
    """

    def extract_trending_skills(
        self,
        job_postings: list[JobPosting],
        github_trends: list[dict[str, Any]],
        social_signals: list[dict[str, Any]],
        *,
        top_n: int = 15,
    ) -> list[TrendingSkill]:
        """Return the top-N trending skills ordered by signal count descending."""
        skill_counts: Counter[str] = Counter()
        skill_sources: dict[str, set[str]] = {}

        for posting in job_postings:
            for skill in posting.required_skills:
                key = skill.lower().strip()
                if not key:
                    continue
                skill_counts[key] += 1
                skill_sources.setdefault(key, set()).add("job_board")

        for item in github_trends:
            topic = str(item.get("topic", item.get("name", ""))).strip()
            if not topic:
                continue
            key = topic.lower()
            stars = int(item.get("stars_this_week", 0) or 0)
            weight = max(1, min(4, 1 + stars // _GITHUB_STARS_PER_WEIGHT))
            skill_counts[key] += weight
            skill_sources.setdefault(key, set()).add("github_trends")

        for item in social_signals:
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            key = title.lower()
            skill_counts[key] += 1
            skill_sources.setdefault(key, set()).add(
                str(item.get("_source", "social"))
            )

        trending: list[TrendingSkill] = []
        for raw_name, count in skill_counts.most_common(top_n):
            canonical = _canonical(raw_name)
            category = _categorise(raw_name)
            direction = TrendDirection.RISING if count >= 3 else TrendDirection.STABLE
            trending.append(
                TrendingSkill(
                    name=canonical,
                    category=category,
                    trend_direction=direction,
                    signal_count=count,
                    sources=sorted(skill_sources.get(raw_name, set())),
                    evidence=(
                        f"Mentioned in {count} market "
                        f"{'signal' if count == 1 else 'signals'}"
                    ),
                )
            )
        return trending

    def normalise_industry_signals(
        self,
        github_trends: list[dict[str, Any]],
        social_signals: list[dict[str, Any]],
        target_role: str,
        *,
        today: datetime | None = None,
    ) -> list[IndustrySignal]:
        """Return typed IndustrySignal objects sorted by relevance to ``target_role``."""
        today = today or datetime.now(UTC)
        today_date = today.date()
        role_keywords = _tokenise(target_role)
        signals: list[IndustrySignal] = []

        for item in github_trends:
            topic = str(item.get("topic", item.get("name", ""))).strip()
            if not topic:
                continue
            language = str(item.get("language", ""))
            stars = item.get("stars_this_week", 0) or 0
            summary = f"Trending on GitHub: {topic}"
            if stars:
                summary += f" (+{int(stars):,} stars this week)"
            if language:
                summary += f" · {language}"
            signals.append(
                IndustrySignal(
                    topic=topic,
                    signal_type=SignalType.GITHUB_TREND,
                    summary=summary,
                    source="GitHub Trends",
                    relevance_score=_relevance(topic, role_keywords),
                    url=item.get("url") or None,
                    freshness_date=today_date,
                )
            )

        for item in social_signals:
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            raw_source = str(item.get("_source", "social"))
            source_label = {
                "hackernews": "Hacker News",
                "reddit": "Reddit",
                "social_aggregate": "Social",
            }.get(raw_source, "Social")
            pts = item.get("points", item.get("upvotes", 0)) or 0
            summary = title
            if pts:
                summary += (
                    f" ({int(pts):,} "
                    f"{'upvotes' if raw_source == 'reddit' else 'points'})"
                )
            signals.append(
                IndustrySignal(
                    topic=title,
                    signal_type=SignalType.SOCIAL_SIGNAL,
                    summary=summary,
                    source=source_label,
                    relevance_score=_relevance(title, role_keywords),
                    url=item.get("url") or None,
                    freshness_date=today_date,
                )
            )

        signals.sort(key=lambda s: s.relevance_score, reverse=True)
        return signals


# ── Private helpers ──────────────────────────────────────────────────────────


def _canonical(raw: str) -> str:
    return _CANONICAL_NAME.get(raw.lower(), raw.title())


def _categorise(raw: str) -> str:
    return _SKILL_CATEGORY.get(raw.lower(), "tech")


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _relevance(topic: str, role_keywords: set[str]) -> float:
    """Keyword-overlap relevance score in [0, 1]."""
    if not role_keywords or not topic:
        return 0.0
    topic_tokens = _tokenise(topic)
    overlap = len(topic_tokens & role_keywords)
    return round(min(1.0, overlap / len(role_keywords)), 3)
