"""SkillNormaliser — map raw skill strings to a canonical SkillGraph.

Two-pass normalisation:
  Pass 1 — dictionary lookup: resolve common aliases/abbreviations locally,
            with no LLM call and no latency cost.
  Pass 2 — LLM batch call: categorise and canonicalise everything that the
            dictionary does not cover.  Falls back gracefully (skills kept
            as-is under category "other") when the LLM is unavailable.

Produces a ``SkillGraph`` of ``SkillNode`` objects ready for ReadinessScorer.

Design: stateless, injectable LLM client, OTel + Prometheus observability.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import CV_NORMALISE_DURATION, CV_NORMALISE_TOTAL, get_tracer
from agents.cv_analysis.models import SkillGraph, SkillNode

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.skill_normaliser")

# ── Alias dictionary ────────────────────────────────────────────────────────
# Keys: lowercase normalised raw names. Values: (canonical_name, category).

_ALIAS_MAP: dict[str, tuple[str, str]] = {
    # Programming languages
    "js": ("JavaScript", "programming_language"),
    "javascript": ("JavaScript", "programming_language"),
    "typescript": ("TypeScript", "programming_language"),
    "ts": ("TypeScript", "programming_language"),
    "py": ("Python", "programming_language"),
    "python": ("Python", "programming_language"),
    "golang": ("Go", "programming_language"),
    "go": ("Go", "programming_language"),
    "c++": ("C++", "programming_language"),
    "cpp": ("C++", "programming_language"),
    "c#": ("C#", "programming_language"),
    "csharp": ("C#", "programming_language"),
    "java": ("Java", "programming_language"),
    "kotlin": ("Kotlin", "programming_language"),
    "swift": ("Swift", "programming_language"),
    "ruby": ("Ruby", "programming_language"),
    "rust": ("Rust", "programming_language"),
    "scala": ("Scala", "programming_language"),
    "r": ("R", "programming_language"),
    "sql": ("SQL", "database"),
    "bash": ("Bash", "tool"),
    "shell": ("Bash", "tool"),
    "shell scripting": ("Bash", "tool"),
    # Frontend
    "react": ("React", "framework"),
    "react.js": ("React", "framework"),
    "reactjs": ("React", "framework"),
    "vue": ("Vue.js", "framework"),
    "vue.js": ("Vue.js", "framework"),
    "angular": ("Angular", "framework"),
    "next": ("Next.js", "framework"),
    "next.js": ("Next.js", "framework"),
    "nextjs": ("Next.js", "framework"),
    # Backend
    "node": ("Node.js", "framework"),
    "node.js": ("Node.js", "framework"),
    "nodejs": ("Node.js", "framework"),
    "fastapi": ("FastAPI", "framework"),
    "django": ("Django", "framework"),
    "flask": ("Flask", "framework"),
    "spring": ("Spring", "framework"),
    "spring boot": ("Spring Boot", "framework"),
    "rails": ("Ruby on Rails", "framework"),
    "express": ("Express.js", "framework"),
    "expressjs": ("Express.js", "framework"),
    # Databases
    "postgres": ("PostgreSQL", "database"),
    "postgresql": ("PostgreSQL", "database"),
    "mysql": ("MySQL", "database"),
    "mongo": ("MongoDB", "database"),
    "mongodb": ("MongoDB", "database"),
    "redis": ("Redis", "database"),
    "elasticsearch": ("Elasticsearch", "database"),
    "cassandra": ("Cassandra", "database"),
    "dynamodb": ("DynamoDB", "database"),
    "bigquery": ("BigQuery", "database"),
    "snowflake": ("Snowflake", "database"),
    # Cloud
    "aws": ("AWS", "platform"),
    "amazon web services": ("AWS", "platform"),
    "gcp": ("GCP", "platform"),
    "google cloud": ("GCP", "platform"),
    "google cloud platform": ("GCP", "platform"),
    "azure": ("Azure", "platform"),
    "microsoft azure": ("Azure", "platform"),
    # Containers / infra
    "k8s": ("Kubernetes", "tool"),
    "kubernetes": ("Kubernetes", "tool"),
    "docker": ("Docker", "tool"),
    "terraform": ("Terraform", "tool"),
    "ansible": ("Ansible", "tool"),
    "helm": ("Helm", "tool"),
    "pulumi": ("Pulumi", "tool"),
    # CI/CD
    "github actions": ("GitHub Actions", "tool"),
    "jenkins": ("Jenkins", "tool"),
    "circleci": ("CircleCI", "tool"),
    "gitlab ci": ("GitLab CI", "tool"),
    "argocd": ("ArgoCD", "tool"),
    # Messaging
    "kafka": ("Apache Kafka", "tool"),
    "apache kafka": ("Apache Kafka", "tool"),
    "rabbitmq": ("RabbitMQ", "tool"),
    "celery": ("Celery", "tool"),
    # Data / ML
    "tensorflow": ("TensorFlow", "framework"),
    "tf": ("TensorFlow", "framework"),
    "pytorch": ("PyTorch", "framework"),
    "sklearn": ("scikit-learn", "framework"),
    "scikit-learn": ("scikit-learn", "framework"),
    "scikit learn": ("scikit-learn", "framework"),
    "pandas": ("Pandas", "framework"),
    "numpy": ("NumPy", "framework"),
    "spark": ("Apache Spark", "framework"),
    "apache spark": ("Apache Spark", "framework"),
    "airflow": ("Apache Airflow", "tool"),
    "apache airflow": ("Apache Airflow", "tool"),
    "mlflow": ("MLflow", "tool"),
    "dbt": ("dbt", "tool"),
    "weights & biases": ("Weights & Biases", "tool"),
    "wandb": ("Weights & Biases", "tool"),
    "langchain": ("LangChain", "framework"),
    "langgraph": ("LangGraph", "framework"),
    # APIs / protocols
    "graphql": ("GraphQL", "tool"),
    "rest": ("REST APIs", "domain"),
    "rest api": ("REST APIs", "domain"),
    "restful": ("REST APIs", "domain"),
    "grpc": ("gRPC", "tool"),
    "openapi": ("OpenAPI", "tool"),
    "swagger": ("OpenAPI", "tool"),
    # Tooling
    "git": ("Git", "tool"),
    "linux": ("Linux", "platform"),
    "nginx": ("Nginx", "tool"),
}

_SYSTEM_PROMPT = """\
You are a skill taxonomy classifier. For each skill in the provided list, return a
JSON array where every element has these exact keys:
  "raw"       — the original skill string, unchanged
  "canonical" — the canonical display name (e.g. "JS" → "JavaScript")
  "category"  — exactly one of:
                  programming_language | framework | database | platform |
                  tool | soft_skill | domain | certification | other

Respond with ONLY a valid JSON array — no prose, no markdown fences.
"""


class SkillNormaliser:
    """Normalise raw skill strings to a canonical ``SkillGraph``.

    Inject a custom ``llm`` in tests to avoid real Anthropic API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.validator_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def normalise(
        self,
        raw_skills: list[str],
        *,
        correlation_id: str = "",
    ) -> SkillGraph:
        """Normalise ``raw_skills`` and return a ``SkillGraph``.

        Skills resolved by the alias dictionary are handled locally (fast path).
        Remaining unknowns are batch-sent to the LLM. On LLM failure, unknowns
        are kept as-is under category "other" (graceful degradation).
        """
        with _tracer.start_as_current_span("cv.skill_normalise") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("raw_skill_count", len(raw_skills))
            t0 = time.monotonic()

            nodes: list[SkillNode] = []
            unknown: list[str] = []

            for raw in raw_skills:
                entry = _ALIAS_MAP.get(raw.lower().strip())
                if entry:
                    canonical, category = entry
                    nodes.append(SkillNode(name=raw, canonical_name=canonical, category=category))
                else:
                    unknown.append(raw)

            if unknown:
                try:
                    llm_nodes = await self._normalise_with_llm(unknown, correlation_id)
                    nodes.extend(llm_nodes)
                    CV_NORMALISE_TOTAL.labels(status="llm").inc()
                except Exception as exc:
                    span.record_exception(exc)
                    logger.warning(
                        "cv.skill_normalise_llm_failed",
                        error=str(exc),
                        fallback_count=len(unknown),
                        correlation_id=correlation_id,
                    )
                    nodes.extend(
                        SkillNode(name=raw, canonical_name=raw, category="other")
                        for raw in unknown
                    )
                    CV_NORMALISE_TOTAL.labels(status="fallback").inc()
            else:
                CV_NORMALISE_TOTAL.labels(status="dict_only").inc()

            duration = time.monotonic() - t0
            CV_NORMALISE_DURATION.observe(duration)
            graph = SkillGraph(nodes=nodes)

            span.set_attribute("resolved_count", len(nodes))
            span.set_attribute("llm_resolved_count", len(unknown))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "cv.skills_normalised",
                total=len(nodes),
                dict_resolved=len(nodes) - len(unknown),
                llm_resolved=len(unknown),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return graph

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _normalise_with_llm(
        self, skills: list[str], correlation_id: str
    ) -> list[SkillNode]:
        skill_list = "\n".join(f"- {s}" for s in skills)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=skill_list),
            ]
        )
        raw_list: Any = json.loads(str(response.content))
        if not isinstance(raw_list, list):
            raise ValueError(f"Expected JSON array, got {type(raw_list).__name__}")

        result: list[SkillNode] = []
        for item in raw_list:
            try:
                result.append(
                    SkillNode(
                        name=str(item.get("raw", "")),
                        canonical_name=str(item.get("canonical") or item.get("raw", "")),
                        category=str(item.get("category", "other")),
                    )
                )
            except (KeyError, TypeError):
                pass
        return result
