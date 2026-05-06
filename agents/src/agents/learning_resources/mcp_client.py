"""MCP client abstraction for learning resources course catalog calls.

Provides:
  MCPClientProtocol  — structural typing interface (Protocol)
  HttpMCPClient      — production JSON-RPC 2.0 over HTTP (requires httpx)
  StubMCPClient      — realistic mock data for tests / unconfigured servers

The agent depends only on MCPClientProtocol; the concrete class is injected
at construction time, keeping the agent fully decoupled from transport.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agents.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class MCPClientProtocol(Protocol):
    """Structural interface for MCP course catalog calls.

    Agents depend on this protocol, not a concrete class.
    ``StubMCPClient`` satisfies it without subclassing.
    """

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Call a named tool on a registered MCP server and return the result dict."""
        ...


class HttpMCPClient:
    """Production MCP client using JSON-RPC 2.0 over HTTP.

    Server URLs are passed as a registry dict:
      {"course_catalog": "http://mcp-course-catalog:3002"}

    Requires ``httpx`` — add to pyproject.toml if absent.
    """

    def __init__(
        self,
        server_registry: dict[str, str],
        timeout_seconds: float = 30.0,
    ) -> None:
        self._registry = server_registry
        self._timeout = timeout_seconds

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        import httpx

        base_url = self._registry.get(server_id)
        if not base_url:
            raise ValueError(f"MCP server '{server_id}' not registered")

        request_body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": tool,
            "params": params,
        }
        t0 = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    base_url,
                    json=request_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Correlation-ID": correlation_id,
                    },
                )
                resp.raise_for_status()
                body: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning(
                "mcp_lr.call_failed",
                server_id=server_id,
                tool=tool,
                error=str(exc),
                correlation_id=correlation_id,
            )
            raise

        if "error" in body:
            err = body["error"]
            raise RuntimeError(
                f"MCP error [{err.get('code', -1)}]: {err.get('message', 'unknown')}"
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "mcp_lr.call_ok",
            server_id=server_id,
            tool=tool,
            latency_ms=latency_ms,
            correlation_id=correlation_id,
        )
        return body.get("result", {})


class StubMCPClient:
    """Realistic stub MCP client for tests and unconfigured environments.

    Returns plausible course data without any network calls.
    Inject a custom ``StubMCPClient`` in tests to control returned data precisely.
    """

    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        if server_id == "course_catalog" and tool == "course.search":
            return _stub_course_search(params)
        return {"courses": [], "total_count": 0, "fetched_at": datetime.now(UTC).isoformat()}


# ── Stub data helpers ─────────────────────────────────────────────────────────

_SKILL_CATALOG: dict[str, list[dict[str, Any]]] = {
    "python": [
        {
            "id": "py-001",
            "title": "Python for Everybody Specialisation",
            "provider": "Coursera / UMich",
            "skill_tags": ["python", "programming", "data"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 35.0,
            "cost_usd": 0.0,
            "quality_score": 0.93,
            "url": "https://coursera.org/specializations/python",
            "description": "Foundational Python programming from scratch.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "py-002",
            "title": "Complete Python Bootcamp: From Zero to Hero",
            "provider": "Udemy",
            "skill_tags": ["python", "oop", "data structures", "algorithms"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 22.0,
            "cost_usd": 19.99,
            "quality_score": 0.89,
            "url": "https://udemy.com/course/complete-python-bootcamp",
            "description": "Comprehensive Python bootcamp covering OOP, data structures, and algorithms.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "py-003",
            "title": "Fluent Python — 2nd Edition",
            "provider": "O'Reilly",
            "skill_tags": ["python", "asyncio", "decorators", "generators", "type hints"],
            "level": "advanced",
            "format": "book",
            "duration_hours": 30.0,
            "cost_usd": 0.0,
            "quality_score": 0.96,
            "url": "https://oreilly.com/library/view/fluent-python-2nd/9781492056348",
            "description": "Deep dive into Python's data model, metaprogramming, and async.",
            "freshness_year": 2022,
            "source": "stub",
        },
    ],
    "kubernetes": [
        {
            "id": "k8s-001",
            "title": "Kubernetes for Absolute Beginners",
            "provider": "Udemy",
            "skill_tags": ["kubernetes", "docker", "containers", "devops"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 6.0,
            "cost_usd": 19.99,
            "quality_score": 0.90,
            "url": "https://udemy.com/course/kubernetes-for-absolute-beginners",
            "description": "Hands-on introduction to Kubernetes concepts and CLI.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "k8s-002",
            "title": "Certified Kubernetes Administrator (CKA)",
            "provider": "Linux Foundation / KodeKloud",
            "skill_tags": ["kubernetes", "cka", "cluster administration", "networking"],
            "level": "advanced",
            "format": "course",
            "duration_hours": 20.0,
            "cost_usd": 0.0,
            "quality_score": 0.94,
            "url": "https://kodekloud.com/courses/certified-kubernetes-administrator-cka",
            "description": "Full CKA exam prep with labs and practice tests.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "k8s-003",
            "title": "Kubernetes in Action — 2nd Edition",
            "provider": "Manning",
            "skill_tags": ["kubernetes", "microservices", "helm", "operators"],
            "level": "intermediate",
            "format": "book",
            "duration_hours": 25.0,
            "cost_usd": 49.99,
            "quality_score": 0.95,
            "url": "https://www.manning.com/books/kubernetes-in-action-second-edition",
            "description": "Comprehensive guide to running containerised apps on Kubernetes.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "docker": [
        {
            "id": "doc-001",
            "title": "Docker & Kubernetes: The Practical Guide",
            "provider": "Udemy",
            "skill_tags": ["docker", "kubernetes", "containers", "ci/cd"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 24.0,
            "cost_usd": 19.99,
            "quality_score": 0.91,
            "url": "https://udemy.com/course/docker-kubernetes-the-practical-guide",
            "description": "Build, ship, and run containerised applications with Docker and K8s.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "doc-002",
            "title": "Docker Official Documentation",
            "provider": "Docker",
            "skill_tags": ["docker", "dockerfile", "compose", "networking"],
            "level": "beginner",
            "format": "article",
            "duration_hours": 5.0,
            "cost_usd": 0.0,
            "quality_score": 0.85,
            "url": "https://docs.docker.com",
            "description": "Official Docker documentation covering all core concepts.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
    "pytorch": [
        {
            "id": "pt-001",
            "title": "Deep Learning with PyTorch",
            "provider": "Coursera / DeepLearning.AI",
            "skill_tags": ["pytorch", "deep learning", "neural networks", "cnn", "rnn"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 40.0,
            "cost_usd": 0.0,
            "quality_score": 0.93,
            "url": "https://coursera.org/learn/deep-neural-networks-with-pytorch",
            "description": "Hands-on deep learning with PyTorch from IBM.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "pt-002",
            "title": "PyTorch Official Tutorials",
            "provider": "PyTorch",
            "skill_tags": ["pytorch", "tensors", "autograd", "training loops"],
            "level": "beginner",
            "format": "article",
            "duration_hours": 8.0,
            "cost_usd": 0.0,
            "quality_score": 0.90,
            "url": "https://pytorch.org/tutorials",
            "description": "Official PyTorch tutorials from beginner to advanced.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "pt-003",
            "title": "Practical Deep Learning for Coders",
            "provider": "fast.ai",
            "skill_tags": ["pytorch", "fastai", "computer vision", "nlp", "transformers"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 30.0,
            "cost_usd": 0.0,
            "quality_score": 0.94,
            "url": "https://course.fast.ai",
            "description": "Top-down practical deep learning with PyTorch and fastai.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
    "machine learning": [
        {
            "id": "ml-001",
            "title": "Machine Learning Specialisation",
            "provider": "Coursera / DeepLearning.AI",
            "skill_tags": ["machine learning", "supervised learning", "neural networks", "python"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 60.0,
            "cost_usd": 0.0,
            "quality_score": 0.96,
            "url": "https://coursera.org/specializations/machine-learning-introduction",
            "description": "Andrew Ng's updated ML specialisation covering modern techniques.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "ml-002",
            "title": "Hands-On Machine Learning with Scikit-Learn, Keras & TensorFlow",
            "provider": "O'Reilly",
            "skill_tags": ["machine learning", "scikit-learn", "tensorflow", "keras"],
            "level": "intermediate",
            "format": "book",
            "duration_hours": 40.0,
            "cost_usd": 59.99,
            "quality_score": 0.95,
            "url": "https://oreilly.com/library/view/hands-on-machine-learning/9781098125967",
            "description": "Definitive practical guide to ML with Python libraries.",
            "freshness_year": 2023,
            "source": "stub",
        },
    ],
    "deep learning": [
        {
            "id": "dl-001",
            "title": "Deep Learning Specialisation",
            "provider": "Coursera / DeepLearning.AI",
            "skill_tags": ["deep learning", "neural networks", "cnn", "rnn", "transformers"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 80.0,
            "cost_usd": 0.0,
            "quality_score": 0.97,
            "url": "https://coursera.org/specializations/deep-learning",
            "description": "Five-course specialisation covering all aspects of modern deep learning.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "aws": [
        {
            "id": "aws-001",
            "title": "AWS Certified Solutions Architect – Associate",
            "provider": "A Cloud Guru",
            "skill_tags": ["aws", "cloud", "ec2", "s3", "rds", "vpc"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 42.0,
            "cost_usd": 0.0,
            "quality_score": 0.92,
            "url": "https://acloudguru.com/course/aws-certified-solutions-architect-associate",
            "description": "Comprehensive SAA-C03 exam prep with hands-on labs.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "aws-002",
            "title": "Ultimate AWS Certified Developer",
            "provider": "Udemy",
            "skill_tags": ["aws", "lambda", "api gateway", "dynamodb", "cdk"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 28.0,
            "cost_usd": 19.99,
            "quality_score": 0.91,
            "url": "https://udemy.com/course/aws-certified-developer-associate-dva-c01",
            "description": "AWS DVA-C02 exam preparation with real-world examples.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
    "fastapi": [
        {
            "id": "fapi-001",
            "title": "FastAPI Official Documentation & Tutorial",
            "provider": "FastAPI",
            "skill_tags": ["fastapi", "python", "rest api", "pydantic", "async"],
            "level": "intermediate",
            "format": "article",
            "duration_hours": 8.0,
            "cost_usd": 0.0,
            "quality_score": 0.93,
            "url": "https://fastapi.tiangolo.com/tutorial",
            "description": "Comprehensive tutorial covering all FastAPI features.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "fapi-002",
            "title": "Building Python Microservices with FastAPI",
            "provider": "Packt",
            "skill_tags": ["fastapi", "microservices", "docker", "postgresql", "redis"],
            "level": "advanced",
            "format": "book",
            "duration_hours": 15.0,
            "cost_usd": 39.99,
            "quality_score": 0.86,
            "url": "https://packtpub.com/product/building-python-microservices-with-fastapi",
            "description": "Production-grade microservices with FastAPI, Docker, and PostgreSQL.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "langchain": [
        {
            "id": "lc-001",
            "title": "LangChain for LLM Application Development",
            "provider": "DeepLearning.AI",
            "skill_tags": ["langchain", "llm", "agents", "rag", "prompt engineering"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 4.0,
            "cost_usd": 0.0,
            "quality_score": 0.91,
            "url": "https://deeplearning.ai/short-courses/langchain-for-llm-application-development",
            "description": "Build LLM applications using LangChain with Harrison Chase.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "lc-002",
            "title": "LangChain Official Documentation",
            "provider": "LangChain",
            "skill_tags": ["langchain", "langgraph", "agents", "tools", "memory"],
            "level": "intermediate",
            "format": "article",
            "duration_hours": 6.0,
            "cost_usd": 0.0,
            "quality_score": 0.88,
            "url": "https://python.langchain.com/docs",
            "description": "Official LangChain documentation covering chains, agents, and RAG.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
    "mlops": [
        {
            "id": "mlops-001",
            "title": "Machine Learning Engineering for Production (MLOps)",
            "provider": "Coursera / DeepLearning.AI",
            "skill_tags": ["mlops", "model deployment", "monitoring", "data pipeline", "ci/cd"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 40.0,
            "cost_usd": 0.0,
            "quality_score": 0.92,
            "url": "https://coursera.org/specializations/machine-learning-engineering-for-production-mlops",
            "description": "Four-course MLOps specialisation covering production ML systems.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "mlops-002",
            "title": "Designing Machine Learning Systems",
            "provider": "O'Reilly",
            "skill_tags": ["mlops", "feature engineering", "model monitoring", "system design"],
            "level": "advanced",
            "format": "book",
            "duration_hours": 20.0,
            "cost_usd": 59.99,
            "quality_score": 0.95,
            "url": "https://oreilly.com/library/view/designing-machine-learning/9781098107956",
            "description": "Comprehensive guide to building reliable ML systems by Chip Huyen.",
            "freshness_year": 2022,
            "source": "stub",
        },
    ],
    "terraform": [
        {
            "id": "tf-001",
            "title": "Terraform: Getting Started",
            "provider": "HashiCorp Learn",
            "skill_tags": ["terraform", "iac", "aws", "infrastructure"],
            "level": "beginner",
            "format": "article",
            "duration_hours": 5.0,
            "cost_usd": 0.0,
            "quality_score": 0.90,
            "url": "https://developer.hashicorp.com/terraform/tutorials",
            "description": "Official HashiCorp tutorials for Terraform fundamentals.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "tf-002",
            "title": "Terraform — From Beginner to Master",
            "provider": "Udemy",
            "skill_tags": ["terraform", "modules", "state management", "aws", "gcp"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 12.0,
            "cost_usd": 19.99,
            "quality_score": 0.88,
            "url": "https://udemy.com/course/terraform-beginner-to-advanced",
            "description": "Comprehensive Terraform with AWS and GCP real-world examples.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
    "sql": [
        {
            "id": "sql-001",
            "title": "The Complete SQL Bootcamp",
            "provider": "Udemy",
            "skill_tags": ["sql", "postgresql", "database", "joins", "window functions"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 9.0,
            "cost_usd": 19.99,
            "quality_score": 0.91,
            "url": "https://udemy.com/course/the-complete-sql-bootcamp",
            "description": "Master SQL with PostgreSQL — from basics to advanced queries.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": "sql-002",
            "title": "Mode SQL Tutorial",
            "provider": "Mode",
            "skill_tags": ["sql", "analytics", "aggregation", "subqueries"],
            "level": "intermediate",
            "format": "article",
            "duration_hours": 4.0,
            "cost_usd": 0.0,
            "quality_score": 0.87,
            "url": "https://mode.com/sql-tutorial",
            "description": "Interactive SQL tutorial with real datasets.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "system design": [
        {
            "id": "sd-001",
            "title": "Grokking Modern System Design",
            "provider": "Educative.io",
            "skill_tags": ["system design", "distributed systems", "scalability", "caching"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 30.0,
            "cost_usd": 0.0,
            "quality_score": 0.92,
            "url": "https://educative.io/courses/grokking-modern-system-design-interview",
            "description": "Structured system design preparation for senior engineers.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "sd-002",
            "title": "System Design Primer",
            "provider": "GitHub",
            "skill_tags": ["system design", "scalability", "load balancing", "microservices"],
            "level": "intermediate",
            "format": "article",
            "duration_hours": 15.0,
            "cost_usd": 0.0,
            "quality_score": 0.94,
            "url": "https://github.com/donnemartin/system-design-primer",
            "description": "Open-source guide to designing large-scale systems.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "kafka": [
        {
            "id": "kfk-001",
            "title": "Apache Kafka Series — Learn Apache Kafka for Beginners",
            "provider": "Udemy",
            "skill_tags": ["kafka", "streaming", "event-driven", "producers", "consumers"],
            "level": "beginner",
            "format": "course",
            "duration_hours": 11.0,
            "cost_usd": 19.99,
            "quality_score": 0.92,
            "url": "https://udemy.com/course/apache-kafka",
            "description": "Complete Kafka introduction by Conduktor team.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ],
    "react": [
        {
            "id": "rc-001",
            "title": "React — The Complete Guide",
            "provider": "Udemy",
            "skill_tags": ["react", "hooks", "redux", "typescript", "next.js"],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 49.0,
            "cost_usd": 19.99,
            "quality_score": 0.91,
            "url": "https://udemy.com/course/react-the-complete-guide-incl-redux",
            "description": "Dive in and learn React.js from scratch — hooks, Redux, and more.",
            "freshness_year": 2025,
            "source": "stub",
        },
        {
            "id": "rc-002",
            "title": "React Official Documentation",
            "provider": "React",
            "skill_tags": ["react", "jsx", "components", "hooks", "context"],
            "level": "beginner",
            "format": "article",
            "duration_hours": 6.0,
            "cost_usd": 0.0,
            "quality_score": 0.93,
            "url": "https://react.dev/learn",
            "description": "Official React documentation — beginner to advanced.",
            "freshness_year": 2025,
            "source": "stub",
        },
    ],
}


def _stub_course_search(params: dict[str, Any]) -> dict[str, Any]:
    """Return stub courses matching the requested skill."""
    skill_raw = str(params.get("skill", "")).lower().strip()
    limit = int(params.get("limit", 5))

    courses = _SKILL_CATALOG.get(skill_raw)

    if not courses:
        # Partial match — try to find a key that contains the skill word
        for key, key_courses in _SKILL_CATALOG.items():
            if skill_raw in key or key in skill_raw:
                courses = key_courses
                break

    if not courses:
        # Generic fallback for unknown skills
        courses = _generic_courses(skill_raw)

    return {
        "courses": courses[:limit],
        "total_count": len(courses),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _generic_courses(skill: str) -> list[dict[str, Any]]:
    """Generate generic stub courses for skills not in the catalog."""
    title_cased = skill.title()
    return [
        {
            "id": f"gen-{skill[:8]}-001",
            "title": f"Introduction to {title_cased}",
            "provider": "Udemy",
            "skill_tags": [skill],
            "level": "beginner",
            "format": "course",
            "duration_hours": 12.0,
            "cost_usd": 19.99,
            "quality_score": 0.78,
            "url": None,
            "description": f"Beginner-friendly introduction to {title_cased}.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": f"gen-{skill[:8]}-002",
            "title": f"Mastering {title_cased}",
            "provider": "Coursera",
            "skill_tags": [skill],
            "level": "intermediate",
            "format": "course",
            "duration_hours": 25.0,
            "cost_usd": 0.0,
            "quality_score": 0.80,
            "url": None,
            "description": f"Intermediate {title_cased} course with hands-on projects.",
            "freshness_year": 2024,
            "source": "stub",
        },
        {
            "id": f"gen-{skill[:8]}-003",
            "title": f"Advanced {title_cased} Techniques",
            "provider": "Pluralsight",
            "skill_tags": [skill],
            "level": "advanced",
            "format": "course",
            "duration_hours": 15.0,
            "cost_usd": 29.99,
            "quality_score": 0.82,
            "url": None,
            "description": f"Advanced {title_cased} for experienced practitioners.",
            "freshness_year": 2024,
            "source": "stub",
        },
    ]
