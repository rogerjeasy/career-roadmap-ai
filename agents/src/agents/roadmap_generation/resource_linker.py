"""ResourceLinker — links curated learning resources to roadmap phases.

Matching strategy (in priority order):
  1. RAG chunks whose metadata contains resource fields → converted to Resource
  2. Catalog lookup per skill in phase.skills_to_acquire
  3. LLM-generated resources for skills with no catalog/RAG coverage
     (Claude → OpenAI → DeepSeek; skipped gracefully if all fail)
  4. Deduplication by (title, provider) pair

Returns at most ``max_per_phase`` resources per phase.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from agents.core.context import RagChunk
from agents.core.logging import get_logger
from agents.core.observability import ROADMAP_RESOURCE_LINK_TOTAL
from agents.roadmap_generation.models import DifficultyLevel, Phase, Resource, ResourceType

logger = get_logger(__name__)

# ── Curated catalog ──────────────────────────────────────────────────────────

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
    "communication": [
        Resource(
            title="Crucial Conversations",
            resource_type=ResourceType.BOOK,
            provider="Kerry Patterson et al. (McGraw-Hill)",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["communication", "soft skills"],
            url=None,
            estimated_hours=6.0,
            is_free=False,
            description="Techniques for high-stakes conversations — universally applicable.",
        ),
    ],
    "leadership": [
        Resource(
            title="The Manager's Path",
            resource_type=ResourceType.BOOK,
            provider="Camille Fournier (O'Reilly)",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["leadership", "management", "career"],
            url=None,
            estimated_hours=8.0,
            is_free=False,
            description="A guide from IC to engineering manager and beyond.",
        ),
    ],
    "sql": [
        Resource(
            title="SQLZoo — Interactive SQL Tutorial",
            resource_type=ResourceType.TUTORIAL,
            provider="SQLZoo",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["sql", "database"],
            url="https://sqlzoo.net",
            estimated_hours=10.0,
            is_free=True,
        ),
    ],
    "data analysis": [
        Resource(
            title="Python for Data Analysis",
            resource_type=ResourceType.BOOK,
            provider="Wes McKinney (O'Reilly)",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["data analysis", "pandas", "python"],
            url=None,
            estimated_hours=20.0,
            is_free=False,
            description="Definitive guide to pandas and data wrangling.",
        ),
    ],
    "finance": [
        Resource(
            title="CFA Institute — Free Learning Resources",
            resource_type=ResourceType.COURSE,
            provider="CFA Institute",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["finance", "fintech", "investment"],
            url="https://www.cfainstitute.org/membership/professional-development/refresher-readings",
            estimated_hours=30.0,
            is_free=True,
            description="Professional-grade financial analysis curriculum.",
        ),
    ],
    "product management": [
        Resource(
            title="Inspired: How to Create Tech Products Customers Love",
            resource_type=ResourceType.BOOK,
            provider="Marty Cagan (Wiley)",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["product management", "product", "tech"],
            url=None,
            estimated_hours=8.0,
            is_free=False,
        ),
    ],
    "cybersecurity": [
        Resource(
            title="TryHackMe — Free Learning Paths",
            resource_type=ResourceType.TUTORIAL,
            provider="TryHackMe",
            difficulty=DifficultyLevel.BEGINNER,
            tags=["cybersecurity", "hacking", "security"],
            url="https://tryhackme.com",
            estimated_hours=40.0,
            is_free=True,
        ),
    ],
    "networking": [
        Resource(
            title="Computer Networking: A Top-Down Approach",
            resource_type=ResourceType.BOOK,
            provider="Kurose & Ross (Pearson)",
            difficulty=DifficultyLevel.INTERMEDIATE,
            tags=["networking", "tcp/ip", "protocols"],
            url=None,
            estimated_hours=30.0,
            is_free=False,
            description="Standard university textbook — used worldwide.",
        ),
    ],
}

_ALIASES: dict[str, str] = {
    "golang": "go",
    "nextjs": "next.js",
    "postgres": "postgresql",
    "ml": "machine learning",
    "llms": "llm",
    "deep learning": "machine learning",
    "k8s": "kubernetes",
    "prompt engineering": "llm",
    "data science": "machine learning",
    "cloud computing": "aws",
    "azure": "aws",
    "soft skills": "communication",
    "people skills": "communication",
    "project management": "product management",
    "infosec": "cybersecurity",
    "network": "networking",
}

# LLM system prompt for resource generation
_RESOURCE_GEN_SYSTEM = """\
You are a career learning resource expert with comprehensive knowledge of training materials
across every professional domain and country worldwide. Recommend high-quality, specific,
real learning resources for a career transition.

OUTPUT — valid JSON only (no code fences, no markdown):
{
  "resources": [
    {
      "title": "Exact book/course/tutorial title",
      "resource_type": "course|book|tutorial|documentation|certification|community|video",
      "provider": "Publisher, platform, or author",
      "difficulty": "beginner|intermediate|advanced",
      "tags": ["skill1", "skill2"],
      "url": "https://exact-url.com or null if uncertain",
      "estimated_hours": 20.0,
      "is_free": false,
      "description": "One sentence: what this teaches and why it matters for the role"
    }
  ]
}

RULES:
1. Only recommend real, verifiable resources — do NOT invent titles or authors
2. Include at least one book per skill (title + author + publisher/year)
3. Include at least one online course per skill (Coursera, edX, Udemy, Pluralsight, LinkedIn Learning, etc.)
4. Include at least one free resource per skill (official docs, open-source tutorial, free course)
5. Mix beginner → advanced to support learners at different stages
6. Set url=null if you are not confident of the exact URL — never invent a URL
7. Prefer globally accessible resources (not region-locked where possible)
8. For non-technical skills (communication, leadership, finance), include industry-standard books
9. description must be one sentence explaining the value for someone transitioning to the target role
"""


class ResourceLinker:
    """Links curated learning resources to roadmap phases.

    Stateless — create once and call as many times as needed.
    The ``link`` method is async to support LLM-generated resources for uncovered skills.
    """

    async def link(
        self,
        phases: list[Phase],
        rag_chunks: list[RagChunk],
        trending_skills: list[dict],
        *,
        target_role: str = "",
        max_per_phase: int = 5,
    ) -> list[Resource]:
        """Return deduplicated resources covering all phases, RAG → catalog → LLM."""
        seen: set[tuple[str, str]] = set()
        resources: list[Resource] = []
        trending_names = [s.get("name", "") for s in trending_skills[:5]]

        for phase in phases:
            count = 0
            phase_skills = phase.skills_to_acquire + trending_names

            # 1. RAG chunks (personalised context, highest priority)
            for chunk in rag_chunks:
                if count >= max_per_phase:
                    break
                resource = _chunk_to_resource(chunk, phase_skills)
                if resource is None:
                    continue
                key = _dedup_key(resource)
                if key not in seen:
                    seen.add(key)
                    resources.append(dataclasses.replace(resource, phase_index=phase.index))
                    ROADMAP_RESOURCE_LINK_TOTAL.labels(source="rag").inc()
                    count += 1

            # 2. Catalog resources
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
                        resources.append(dataclasses.replace(r, phase_index=phase.index))
                        ROADMAP_RESOURCE_LINK_TOTAL.labels(source="catalog").inc()
                        count += 1

            # 3. LLM-generated resources for skills without catalog/RAG coverage
            if count < max_per_phase:
                uncovered = _find_uncovered_skills(phase.skills_to_acquire, seen)
                if uncovered:
                    llm_resources = await _generate_llm_resources(
                        uncovered,
                        phase.difficulty.value,
                        target_role,
                        phase.index,
                    )
                    for r in llm_resources:
                        if count >= max_per_phase:
                            break
                        key = _dedup_key(r)
                        if key not in seen:
                            seen.add(key)
                            resources.append(r)
                            ROADMAP_RESOURCE_LINK_TOTAL.labels(source="llm").inc()
                            count += 1

        logger.info("roadmap.resources_linked", resource_count=len(resources))
        return resources


# ── Helpers ──────────────────────────────────────────────────────────────────


def _dedup_key(r: Resource) -> tuple[str, str]:
    return (r.title.lower(), r.provider.lower())


def _find_uncovered_skills(skills: list[str], seen_keys: set[tuple[str, str]]) -> list[str]:
    """Return skills that have no catalog match and no RAG resource already added."""
    uncovered: list[str] = []
    for skill in skills:
        catalog_key = _ALIASES.get(skill.lower(), skill.lower())
        has_catalog = catalog_key in _CATALOG
        if not has_catalog:
            uncovered.append(skill)
    return uncovered[:6]  # cap to avoid over-sized LLM requests


async def _generate_llm_resources(
    skills: list[str],
    difficulty: str,
    target_role: str,
    phase_index: int,
) -> list[Resource]:
    """Generate resources for skills not covered by the static catalog."""
    from agents.config import agent_settings  # local import to avoid circular

    if not agent_settings.fallback_llm_enabled:
        return []

    # Only call the LLM if at least one provider is configured
    has_openai = agent_settings.openai_api_key is not None
    has_deepseek = agent_settings.deepseek_api_key is not None
    # Claude is always the primary — even without OpenAI/DeepSeek we try
    try:
        from agents.core.llm_provider import llm_generate  # local import

        user_prompt = (
            f"Target role: {target_role or 'professional transition'}\n"
            f"Phase difficulty: {difficulty}\n"
            f"Skills needing resources: {', '.join(skills)}\n\n"
            f"For each skill listed above, recommend 2-3 high-quality, real learning resources. "
            f"Include at least one book and one online course per skill. "
            f"Mix free and paid options. Focus on resources relevant to someone "
            f"transitioning to the '{target_role}' role."
        )

        raw_content, provider = await llm_generate(
            _RESOURCE_GEN_SYSTEM,
            user_prompt,
            max_tokens=3000,
            temperature=0.1,
            primary_model=agent_settings.roadmap_generation_model,
            label="resource_linker.llm_gen",
        )
        parsed = json.loads(raw_content)
        raw_resources: list[dict] = parsed.get("resources", [])
        result: list[Resource] = []
        for r in raw_resources:
            res = _parse_llm_resource(r, phase_index)
            if res:
                result.append(res)
        logger.info(
            "resource_linker.llm_resources_generated",
            skill_count=len(skills),
            resource_count=len(result),
            provider=provider,
        )
        return result
    except Exception as exc:
        logger.warning("resource_linker.llm_gen_failed", error=str(exc))
        return []


def _parse_llm_resource(raw: dict[str, Any], phase_index: int) -> Resource | None:
    title = str(raw.get("title") or "").strip()
    provider = str(raw.get("provider") or "").strip()
    if not title or not provider:
        return None

    raw_type = str(raw.get("resource_type", "course")).lower()
    try:
        r_type = ResourceType(raw_type)
    except ValueError:
        r_type = ResourceType.COURSE

    raw_diff = str(raw.get("difficulty", "intermediate")).lower()
    try:
        difficulty = DifficultyLevel(raw_diff)
    except ValueError:
        difficulty = DifficultyLevel.INTERMEDIATE

    hours_raw = raw.get("estimated_hours")
    estimated_hours: float | None = float(hours_raw) if hours_raw else None

    url = str(raw.get("url") or "") or None

    return Resource(
        title=title,
        resource_type=r_type,
        provider=provider,
        difficulty=difficulty,
        tags=[str(t) for t in raw.get("tags", []) if t][:5],
        url=url,
        estimated_hours=estimated_hours,
        is_free=bool(raw.get("is_free", False)),
        description=str(raw.get("description") or ""),
        phase_index=phase_index,
    )


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
