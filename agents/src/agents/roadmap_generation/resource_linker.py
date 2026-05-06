"""ResourceLinker — links curated learning resources to roadmap phases.

Matching strategy (in priority order):
  1. RAG chunks whose metadata contains resource fields → converted to Resource
  2. Catalog lookup per skill in phase.skills_to_acquire
  3. Deduplication by (title, provider) pair

Returns at most ``max_per_phase`` resources per phase.
"""
from __future__ import annotations

from typing import Any

from agents.core.context import RagChunk
from agents.core.logging import get_logger
from agents.core.observability import ROADMAP_RESOURCE_LINK_TOTAL
from agents.roadmap_generation.models import DifficultyLevel, Phase, Resource, ResourceType

logger = get_logger(__name__)

# ── Curated catalog ──────────────────────────────────────────────────────────
# Keyed by lowercase skill name. Each entry is a list so multiple resources
# can be linked per skill.

_CATALOG: dict[str, list[Resource]] = {
    "python": [
        Resource(
            title="Python for Everybody Specialization",
            resource_type=ResourceType.COURSE,
            provider="Coursera / University of Michigan",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["python", "programming"],
            url="https://www.coursera.org/specializations/python",
            estimated_hours=40.0,
            is_free=False,
            description="Comprehensive Python fundamentals — audit for free.",
        ),
        Resource(
            title="Automate the Boring Stuff with Python",
            resource_type=ResourceType.BOOK,
            provider="Al Sweigart (free online)",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["python", "automation"],
            url="https://automatetheboringstuff.com",
            estimated_hours=20.0,
            is_free=True,
        ),
    ],
    "typescript": [
        Resource(
            title="TypeScript Official Handbook",
            resource_type=ResourceType.DOCUMENTATION,
            provider="Microsoft",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["typescript", "javascript"],
            url="https://www.typescriptlang.org/docs/handbook/",
            estimated_hours=8.0,
            is_free=True,
        ),
    ],
    "javascript": [
        Resource(
            title="The Odin Project — JavaScript Path",
            resource_type=ResourceType.TUTORIAL,
            provider="The Odin Project",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["javascript", "frontend"],
            url="https://www.theodinproject.com/paths/full-stack-javascript",
            estimated_hours=50.0,
            is_free=True,
        ),
    ],
    "go": [
        Resource(
            title="A Tour of Go",
            resource_type=ResourceType.TUTORIAL,
            provider="Google / golang.org",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["go", "golang"],
            url="https://go.dev/tour/",
            estimated_hours=5.0,
            is_free=True,
        ),
        Resource(
            title="Go by Example",
            resource_type=ResourceType.TUTORIAL,
            provider="Mark McGranaghan",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["go"],
            url="https://gobyexample.com",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "rust": [
        Resource(
            title="The Rust Programming Language",
            resource_type=ResourceType.BOOK,
            provider="Mozilla Foundation",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["rust", "systems"],
            url="https://doc.rust-lang.org/book/",
            estimated_hours=30.0,
            is_free=True,
        ),
    ],
    "fastapi": [
        Resource(
            title="FastAPI Official Tutorial",
            resource_type=ResourceType.DOCUMENTATION,
            provider="Sebastián Ramírez",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["fastapi", "python", "api"],
            url="https://fastapi.tiangolo.com/tutorial/",
            estimated_hours=6.0,
            is_free=True,
        ),
    ],
    "react": [
        Resource(
            title="React Official Docs — Learn React",
            resource_type=ResourceType.DOCUMENTATION,
            provider="Meta",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["react", "javascript", "frontend"],
            url="https://react.dev/learn",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "next.js": [
        Resource(
            title="Next.js Official Tutorial",
            resource_type=ResourceType.TUTORIAL,
            provider="Vercel",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["next.js", "react", "frontend"],
            url="https://nextjs.org/learn",
            estimated_hours=6.0,
            is_free=True,
        ),
    ],
    "langchain": [
        Resource(
            title="LangChain Documentation",
            resource_type=ResourceType.DOCUMENTATION,
            provider="LangChain",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["langchain", "llm", "ai"],
            url="https://python.langchain.com/docs/",
            estimated_hours=8.0,
            is_free=True,
        ),
    ],
    "docker": [
        Resource(
            title="Docker Official Get Started",
            resource_type=ResourceType.TUTORIAL,
            provider="Docker Inc.",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["docker", "containers", "devops"],
            url="https://docs.docker.com/get-started/",
            estimated_hours=4.0,
            is_free=True,
        ),
    ],
    "kubernetes": [
        Resource(
            title="Kubernetes Official Tutorials",
            resource_type=ResourceType.TUTORIAL,
            provider="CNCF / kubernetes.io",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["kubernetes", "k8s", "devops"],
            url="https://kubernetes.io/docs/tutorials/",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "aws": [
        Resource(
            title="AWS Cloud Practitioner Essentials",
            resource_type=ResourceType.COURSE,
            provider="AWS Training",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["aws", "cloud"],
            url="https://explore.skillbuilder.aws/learn/course/external/view/elearning/134/aws-cloud-practitioner-essentials",
            estimated_hours=6.0,
            is_free=True,
        ),
    ],
    "gcp": [
        Resource(
            title="Google Cloud Skills Boost",
            resource_type=ResourceType.COURSE,
            provider="Google Cloud",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["gcp", "cloud"],
            url="https://www.cloudskillsboost.google",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "terraform": [
        Resource(
            title="HashiCorp Terraform Tutorials",
            resource_type=ResourceType.TUTORIAL,
            provider="HashiCorp",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["terraform", "iac", "devops"],
            url="https://developer.hashicorp.com/terraform/tutorials",
            estimated_hours=6.0,
            is_free=True,
        ),
    ],
    "postgresql": [
        Resource(
            title="PostgreSQL Tutorial",
            resource_type=ResourceType.TUTORIAL,
            provider="postgresqltutorial.com",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["postgresql", "sql", "database"],
            url="https://www.postgresqltutorial.com",
            estimated_hours=8.0,
            is_free=True,
        ),
    ],
    "machine learning": [
        Resource(
            title="Machine Learning Specialization",
            resource_type=ResourceType.COURSE,
            provider="Coursera / DeepLearning.AI",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["machine learning", "ml", "python"],
            url="https://www.coursera.org/specializations/machine-learning-introduction",
            estimated_hours=70.0,
            is_free=False,
            description="Andrew Ng's ML Specialization — audit for free.",
        ),
        Resource(
            title="fast.ai — Practical Deep Learning",
            resource_type=ResourceType.COURSE,
            provider="fast.ai",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["deep learning", "machine learning", "python"],
            url="https://course.fast.ai",
            estimated_hours=40.0,
            is_free=True,
        ),
    ],
    "llm": [
        Resource(
            title="Short Courses — Building with LLMs",
            resource_type=ResourceType.COURSE,
            provider="DeepLearning.AI",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["llm", "ai", "prompt engineering"],
            url="https://www.deeplearning.ai/short-courses/",
            estimated_hours=6.0,
            is_free=True,
        ),
    ],
    "rag": [
        Resource(
            title="LangChain RAG Tutorial",
            resource_type=ResourceType.TUTORIAL,
            provider="LangChain",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["rag", "llm", "langchain"],
            url="https://python.langchain.com/docs/tutorials/rag/",
            estimated_hours=3.0,
            is_free=True,
        ),
    ],
    "git": [
        Resource(
            title="Pro Git",
            resource_type=ResourceType.BOOK,
            provider="Scott Chacon & Ben Straub",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["git", "version control"],
            url="https://git-scm.com/book/en/v2",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "system design": [
        Resource(
            title="System Design Primer",
            resource_type=ResourceType.TUTORIAL,
            provider="Donne Martin (GitHub)",
            difficulty=DifficultyLevel.ADVANCED,
            tags=["system design", "architecture"],
            url="https://github.com/donnemartin/system-design-primer",
            estimated_hours=20.0,
            is_free=True,
        ),
    ],
}

# Normalise common aliases to catalog keys
_ALIASES: dict[str, str] = {
    "golang": "go",
    "nextjs": "next.js",
    "postgres": "postgresql",
    "ml": "machine learning",
    "llms": "llm",
    "deep learning": "machine learning",
    "k8s": "kubernetes",
    "prompt engineering": "llm",
}


class ResourceLinker:
    """Links curated learning resources to roadmap phases.

    Stateless — create once and call as many times as needed.
    """

    def link(
        self,
        phases: list[Phase],
        rag_chunks: list[RagChunk],
        trending_skills: list[dict],
        *,
        max_per_phase: int = 3,
    ) -> list[Resource]:
        """Return deduplicated resources covering all phases, RAG-first."""
        seen: set[tuple[str, str]] = set()
        resources: list[Resource] = []

        # Trending skill names boost catalog coverage
        trending_names = [s.get("name", "") for s in trending_skills[:5]]

        for phase in phases:
            count = 0
            phase_skills = phase.skills_to_acquire + trending_names

            # RAG chunks (personalised context, highest priority)
            for chunk in rag_chunks:
                if count >= max_per_phase:
                    break
                resource = _chunk_to_resource(chunk, phase_skills)
                if resource is None:
                    continue
                key = _dedup_key(resource)
                if key not in seen:
                    seen.add(key)
                    resources.append(resource)
                    ROADMAP_RESOURCE_LINK_TOTAL.labels(source="rag").inc()
                    count += 1

            # Catalog resources
            for skill in phase.skills_to_acquire:
                if count >= max_per_phase:
                    break
                catalog_key = _ALIASES.get(skill.lower(), skill.lower())
                for r in _CATALOG.get(catalog_key, []):
                    if count >= max_per_phase:
                        break
                    key = _dedup_key(r)
                    if key not in seen:
                        seen.add(key)
                        resources.append(r)
                        ROADMAP_RESOURCE_LINK_TOTAL.labels(source="catalog").inc()
                        count += 1

        logger.info("roadmap.resources_linked", resource_count=len(resources))
        return resources


# ── Helpers ──────────────────────────────────────────────────────────────────


def _dedup_key(r: Resource) -> tuple[str, str]:
    return (r.title.lower(), r.provider.lower())


def _chunk_to_resource(chunk: RagChunk, skills: list[str]) -> Resource | None:
    """Convert a RAG chunk to a Resource if its metadata is sufficient."""
    meta = chunk.metadata
    title = str(meta.get("title") or "").strip() or chunk.content[:60].strip()
    provider = str(meta.get("provider") or meta.get("source") or chunk.source).strip()
    if not title or not provider:
        return None

    raw_type = str(meta.get("resource_type", "tutorial")).lower()
    try:
        r_type = ResourceType(raw_type)
    except ValueError:
        r_type = ResourceType.TUTORIAL

    raw_diff = str(meta.get("difficulty", "intermediate")).lower()
    try:
        difficulty = DifficultyLevel(raw_diff)
    except ValueError:
        difficulty = DifficultyLevel.INTERMEDIATE

    hours_raw = meta.get("estimated_hours")
    estimated_hours: float | None = float(hours_raw) if hours_raw else None

    return Resource(
        title=title,
        resource_type=r_type,
        provider=provider,
        difficulty=difficulty,
        tags=[s for s in skills[:3] if s],
        url=str(meta.get("url") or "") or None,
        estimated_hours=estimated_hours,
        is_free=bool(meta.get("is_free", True)),
        description=str(meta.get("description") or chunk.content[:200]),
    )
