"""SkillExtractor — aggregate skill mentions from all CV sections.

Collects skills from three sources without any LLM call:
  1. ``ParsedCV.raw_skills``         — explicit skills section
  2. ``ExperienceEntry.responsibilities`` — keyword scan of job descriptions
  3. ``ProjectEntry.technologies``   — tech stack listed per project

Deduplicates case-insensitively and returns a flat list of raw skill strings
ready for SkillNormaliser.

Design: stateless, no I/O, no LLM. Fast and fully synchronous.
"""
from __future__ import annotations

from opentelemetry.trace import Status, StatusCode

from agents.core.logging import get_logger
from agents.core.observability import CV_SKILLS_EXTRACTED_TOTAL, get_tracer
from agents.cv_analysis.models import ParsedCV

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.skill_extractor")

# Curated set of technology keywords to scan from free-text sections.
# Ordered longer-first prevents substring false-positives where possible.
_TECH_KEYWORDS: frozenset[str] = frozenset({
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust",
    "C++", "C#", "Ruby", "Swift", "Kotlin", "Scala", "R", "MATLAB",
    "SQL", "NoSQL", "Bash", "Shell",
    # Frontend
    "React", "Vue", "Angular", "Next.js", "Svelte", "HTML", "CSS", "Tailwind",
    # Backend
    "FastAPI", "Django", "Flask", "Spring Boot", "Spring", "Rails",
    "Laravel", "Express", "Node.js",
    # Databases
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Cassandra", "DynamoDB", "BigQuery", "Snowflake", "SQLite",
    # Cloud / infra
    "AWS", "GCP", "Azure", "Kubernetes", "Docker", "Terraform",
    "Ansible", "Pulumi", "Helm",
    # CI/CD / tooling
    "GitHub Actions", "Jenkins", "CircleCI", "GitLab CI", "ArgoCD",
    "Git", "Linux", "Nginx",
    # Messaging / streaming
    "Kafka", "RabbitMQ", "Celery", "Pub/Sub",
    # Data / ML
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy",
    "Apache Spark", "Airflow", "MLflow", "dbt", "Weights & Biases",
    "LangChain", "LangGraph",
    # APIs
    "GraphQL", "REST", "gRPC", "OpenAPI",
})


class SkillExtractor:
    """Collect and deduplicate skill mentions from all CV sections.

    Stateless — instantiate once and call ``extract()`` for each CV.
    """

    def extract(
        self,
        parsed_cv: ParsedCV,
        *,
        correlation_id: str = "",
    ) -> list[str]:
        """Return a deduplicated list of skill strings from all CV sections."""
        with _tracer.start_as_current_span("cv.skill_extraction") as span:
            span.set_attribute("correlation_id", correlation_id)

            seen: set[str] = set()
            skills: list[str] = []

            def _add(s: str, source: str) -> None:
                key = s.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    skills.append(s.strip())
                    CV_SKILLS_EXTRACTED_TOTAL.labels(source=source).inc()

            for skill in parsed_cv.raw_skills:
                _add(skill, "skills_section")

            for entry in parsed_cv.experience:
                combined = " ".join(entry.responsibilities)
                for keyword in _scan_keywords(combined):
                    _add(keyword, "experience")

            for project in parsed_cv.projects:
                for tech in project.technologies:
                    _add(tech, "projects")

            span.set_attribute("total_skills", len(skills))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "cv.skills_extracted",
                total=len(skills),
                correlation_id=correlation_id,
            )
            return skills


# ── Helpers ────────────────────────────────────────────────────────────────


def _scan_keywords(text: str) -> list[str]:
    """Return known technology keywords found in ``text`` (case-insensitive)."""
    text_lower = text.lower()
    return [kw for kw in _TECH_KEYWORDS if kw.lower() in text_lower]
