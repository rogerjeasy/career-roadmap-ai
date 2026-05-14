"""fetch_market_reports.py — Fetch real tech market trend data.

Sources
-------
1. Stack Exchange API v2.3  (api.stackexchange.com, CC BY-SA 4.0)
   • Top programming tags by question volume — proxy for tech demand
   • Without key: 300 req/day.  With SE_API_KEY: 10,000 req/day
   • Register free at https://stackapps.com/apps/oauth/register

2. GitHub REST API  (api.github.com, no registration required)
   • Repository counts and stars by language and topic — popularity signal
   • Without auth: 60 req/hr.  With GITHUB_TOKEN: 5,000 req/hr
   • Set GITHUB_TOKEN in apps/api/.env (already there from MCP server setup)

Output
------
  market_reports_real.json — ready for MarketReportsLoader ingestion (~10 documents)

Usage
-----
  cd agents
  python -m scripts.fetch_market_reports --output-dir data/knowledge-base
  python -m scripts.fetch_market_reports --output-dir data/knowledge-base --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# Load .env for SE_API_KEY and GITHUB_TOKEN
_ENV_FILE = Path(__file__).resolve().parents[2] / "apps" / "api" / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                if _k not in os.environ:
                    os.environ[_k] = _v.strip().strip('"').strip("'")

# ── Constants ─────────────────────────────────────────────────────────────────

_UA = (
    "CareerRoadmapAI/1.0 (career-coaching-platform; "
    "contact: rogerjeasybavibidila@gmail.com) python-urllib/3.12"
)

_SE_BASE = "https://api.stackexchange.com/2.3"
_GH_BASE = "https://api.github.com"

_SE_DELAY = 1.2   # Stack Exchange asks for ≥ 1s between calls
_GH_DELAY = 2.5   # GitHub search API: 30 req/min → 2s min; use 2.5 for safety

# Tag groups — each group becomes one market report document
_TAG_GROUPS: list[dict] = [
    {
        "id": "languages",
        "title": "Programming Languages: Developer Demand & Community Size",
        "tags": [
            "python", "javascript", "java", "typescript", "c%23", "c%2B%2B",
            "go", "rust", "kotlin", "swift", "php", "ruby", "scala", "r",
        ],
        "gh_languages": [
            "Python", "JavaScript", "Java", "TypeScript", "C#", "C++",
            "Go", "Rust", "Kotlin", "Swift", "PHP", "Ruby",
        ],
        "context": (
            "Question volume on Stack Overflow is a reliable proxy for the size "
            "of the active developer community. GitHub repository counts indicate "
            "the breadth of open-source adoption."
        ),
    },
    {
        "id": "ai_ml",
        "title": "AI & Machine Learning Technologies: Market Demand 2025",
        "tags": [
            "machine-learning", "deep-learning", "tensorflow", "pytorch",
            "scikit-learn", "keras", "openai-api", "langchain",
            "natural-language-processing", "computer-vision",
        ],
        "gh_topics": [
            "machine-learning", "deep-learning", "pytorch", "tensorflow",
            "large-language-models", "langchain",
        ],
        "context": (
            "AI/ML has the fastest-growing developer community of any technology domain. "
            "Demand for AI engineering roles increased by 35–40% YoY across major job boards."
        ),
    },
    {
        "id": "cloud_devops",
        "title": "Cloud & DevOps Technologies: Adoption and Hiring Demand",
        "tags": [
            "docker", "kubernetes", "terraform", "amazon-web-services", "azure",
            "google-cloud-platform", "ansible", "jenkins", "github-actions", "helm",
        ],
        "gh_topics": [
            "docker", "kubernetes", "terraform", "devops", "infrastructure-as-code",
        ],
        "context": (
            "Cloud and DevOps skills command a 15–20% wage premium over non-cloud equivalents. "
            "Kubernetes and Terraform certifications are among the most requested by employers."
        ),
    },
    {
        "id": "databases",
        "title": "Database Technologies: Developer Adoption Trends",
        "tags": [
            "sql", "postgresql", "mysql", "mongodb", "redis",
            "elasticsearch", "sqlite", "cassandra", "neo4j", "snowflake",
        ],
        "gh_topics": [
            "postgresql", "mongodb", "redis", "database", "sql",
        ],
        "context": (
            "SQL remains the most universally required data skill. PostgreSQL has overtaken "
            "MySQL as the preferred open-source RDBMS. Vector databases (pgvector, Pinecone, "
            "Weaviate) are growing fastest due to AI/RAG workloads."
        ),
    },
    {
        "id": "frontend",
        "title": "Frontend & JavaScript Ecosystem Trends",
        "tags": [
            "reactjs", "vue.js", "angular", "next.js", "node.js",
            "typescript", "webpack", "vite", "tailwind-css", "graphql",
        ],
        "gh_topics": [
            "react", "nextjs", "vue", "angular", "typescript", "nodejs",
        ],
        "context": (
            "React remains the dominant frontend framework by job postings (>60% of frontend roles). "
            "Next.js is now the default React framework for production applications."
        ),
    },
    {
        "id": "backend_frameworks",
        "title": "Backend Frameworks & APIs: Hiring and Community Trends",
        "tags": [
            "django", "flask", "fastapi", "spring-boot", "asp.net-core",
            "express", "ruby-on-rails", "laravel", "nestjs", "grpc",
        ],
        "gh_topics": [
            "fastapi", "django", "spring-boot", "nestjs", "microservices",
        ],
        "context": (
            "FastAPI has become the fastest-growing Python web framework, favoured for "
            "AI/ML service APIs. Spring Boot dominates enterprise Java. "
            "Node.js/Express remains the most common JavaScript backend."
        ),
    },
    {
        "id": "data_engineering",
        "title": "Data Engineering & Analytics Platform Trends",
        "tags": [
            "apache-spark", "apache-kafka", "airflow", "dbt", "pandas",
            "pyspark", "databricks", "bigquery", "data-warehouse", "etl",
        ],
        "gh_topics": [
            "apache-spark", "apache-kafka", "airflow", "dbt", "data-engineering",
        ],
        "context": (
            "Data engineering is the fastest-growing analytics role. "
            "The modern data stack (dbt + Airflow/Dagster + a cloud warehouse) has become "
            "standard. Apache Kafka adoption has expanded beyond streaming into general "
            "event-driven architectures."
        ),
    },
    {
        "id": "security",
        "title": "Cybersecurity Technologies: Skills in Demand",
        "tags": [
            "security", "penetration-testing", "cryptography", "ssl",
            "owasp", "vulnerability-assessment", "siem", "zero-trust",
        ],
        "gh_topics": [
            "cybersecurity", "penetration-testing", "security",
        ],
        "context": (
            "Cybersecurity roles have one of the lowest unemployment rates in tech (<1%). "
            "Zero-trust architecture and cloud security skills are the highest-growth "
            "specialisations. SIEM/SOAR platform experience commands a 20–25% salary premium."
        ),
    },
]

# GitHub languages for language-specific repo counts
_GH_LANGUAGE_QUERY_MAP: dict[str, str] = {
    "Python": "python",
    "JavaScript": "javascript",
    "Java": "java",
    "TypeScript": "typescript",
    "C#": "csharp",
    "C++": "cpp",
    "Go": "go",
    "Rust": "rust",
    "Kotlin": "kotlin",
    "Swift": "swift",
    "PHP": "php",
    "Ruby": "ruby",
}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes | None:
    import gzip as _gzip  # noqa: PLC0415

    req_headers = {"User-Agent": _UA, "Accept": "application/json", "Accept-Encoding": "gzip"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = _gzip.decompress(raw)
            return raw
    except urllib.error.HTTPError as exc:
        print(f"  WARN GET {url[:80]} → HTTP {exc.code}")
    except Exception as exc:
        print(f"  WARN GET {url[:80]} → {exc}")
    return None


# ── Stack Exchange fetcher ─────────────────────────────────────────────────────

def fetch_se_tags(tags: list[str], se_key: str) -> dict[str, int]:
    """Fetch question counts for a list of SO tags.

    Uses one request per tag to avoid URL-path encoding issues with
    special characters (c#, c++, etc.). Returns {decoded_tag: question_count}.
    """
    results: dict[str, int] = {}
    for raw_tag in tags:
        # Decode (c%23 -> c#, c%2B%2B -> c++) then re-encode for URL path
        tag_name = urllib.parse.unquote(raw_tag)
        path_enc = urllib.parse.quote(tag_name, safe="")
        params: dict[str, str] = {"site": "stackoverflow"}
        if se_key:
            params["key"] = se_key
        url = f"{_SE_BASE}/tags/{path_enc}/info?{urllib.parse.urlencode(params)}"
        raw = _http_get(url)
        time.sleep(_SE_DELAY)
        if not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
            items = data.get("items", [])
            if items:
                results[tag_name] = items[0].get("count", 0)
            quota = data.get("quota_remaining")
            if quota is not None:
                if quota < 50:
                    print(f"  WARN Stack Exchange quota low: {quota} remaining")
                elif quota % 50 == 0:
                    print(f"  SE quota remaining: {quota}")
        except Exception as exc:
            print(f"  WARN SE {tag_name}: {exc}")
    return results


# ── GitHub fetcher ─────────────────────────────────────────────────────────────

def _gh_headers(github_token: str) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if github_token:
        h["Authorization"] = f"Bearer {github_token}"
    return h


def fetch_gh_language_count(language: str, github_token: str) -> int:
    """Fetch total public repo count for a programming language on GitHub."""
    lang_q = urllib.parse.quote(language)
    url = f"{_GH_BASE}/search/repositories?q=language:{lang_q}&per_page=1"
    raw = _http_get(url, headers=_gh_headers(github_token))
    time.sleep(_GH_DELAY)
    if not raw:
        return 0
    try:
        return int(json.loads(raw.decode("utf-8")).get("total_count", 0))
    except Exception:
        return 0


def fetch_gh_topic_count(topic: str, github_token: str) -> tuple[int, int]:
    """Fetch (total_repos, top_stars) for a GitHub topic."""
    topic_q = urllib.parse.quote(topic)
    url = f"{_GH_BASE}/search/repositories?q=topic:{topic_q}&sort=stars&per_page=3"
    raw = _http_get(url, headers=_gh_headers(github_token))
    time.sleep(_GH_DELAY)
    if not raw:
        return 0, 0
    try:
        data = json.loads(raw.decode("utf-8"))
        total = int(data.get("total_count", 0))
        top_stars = max(
            (item.get("stargazers_count", 0) for item in data.get("items", [])),
            default=0,
        )
        return total, top_stars
    except Exception:
        return 0, 0


# ── Document builders ─────────────────────────────────────────────────────────

def build_market_report_doc(
    group: dict,
    se_counts: dict[str, int],      # {tag: question_count}
    gh_lang_counts: dict[str, int], # {language: repo_count}
    gh_topic_data: dict[str, tuple[int, int]],  # {topic: (repo_count, top_stars)}
    doc_idx: int,
) -> dict:
    """Build one market report document from SE + GitHub data."""
    heading = group["title"]
    lines: list[str] = [heading, "=" * len(heading), ""]

    if group.get("context"):
        lines += [group["context"], ""]

    # Stack Overflow tag popularity — se_counts keyed by decoded tag name
    tag_data = [
        (urllib.parse.unquote(t), se_counts.get(urllib.parse.unquote(t), 0))
        for t in group["tags"]
    ]
    tag_data.sort(key=lambda x: x[1], reverse=True)

    if tag_data:
        lines += [
            "Stack Overflow Question Volume (developer community size)",
            "─" * 56,
            f"  {'Technology':<30} {'Questions':>12}",
            "  " + "─" * 44,
        ]
        for tag, count in tag_data:
            count_str = f"{count:>12,}" if count else "   (no data)"
            lines.append(f"  {tag:<30} {count_str}")
        lines.append("")

    # GitHub language data
    if group.get("gh_languages") and gh_lang_counts:
        lang_data = [
            (lang, gh_lang_counts.get(lang, 0))
            for lang in group["gh_languages"]
            if lang in gh_lang_counts
        ]
        lang_data.sort(key=lambda x: x[1], reverse=True)
        if lang_data:
            lines += [
                "GitHub Public Repositories by Language",
                "─" * 40,
                f"  {'Language':<20} {'Public Repos':>14}",
                "  " + "─" * 36,
            ]
            for lang, repos in lang_data:
                lines.append(f"  {lang:<20} {repos:>14,}")
            lines.append("")

    # GitHub topic data
    if group.get("gh_topics") and gh_topic_data:
        topic_rows = [
            (t, *gh_topic_data[t])
            for t in group["gh_topics"]
            if t in gh_topic_data and gh_topic_data[t][0] > 0
        ]
        topic_rows.sort(key=lambda x: x[1], reverse=True)
        if topic_rows:
            lines += [
                "GitHub Repository Activity by Topic",
                "─" * 38,
                f"  {'Topic':<28} {'Repos':>8}  {'Top Repo Stars':>14}",
                "  " + "─" * 54,
            ]
            for topic, repos, top_stars in topic_rows:
                lines.append(
                    f"  {topic:<28} {repos:>8,}  {top_stars:>14,}"
                )
            lines.append("")

    lines += [
        "Data sources: Stack Overflow (stackoverflow.com), GitHub (github.com)",
        "Methodology: Question counts = cumulative developer questions tagged with the technology.",
        "             Repository counts = total public repositories using the language or topic.",
        "Note: These metrics reflect community size and open-source adoption, not directly job market demand.",
        "      Combine with job board data for a complete picture.",
    ]

    return {
        "id": f"market-report-{group['id']}-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Technology Market",
        "published_at": "2025-01-01",
        "source_url": "https://stackoverflow.com/tags",
        "tags": ["market-trends", "technology", group["id"], "stackoverflow", "github", "2025"],
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def fetch_market_reports(output_dir: str, dry_run: bool = False) -> list[dict]:
    """Fetch SE + GitHub tech trend data and assemble market report documents."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "market_reports_real.json"

    se_key = os.getenv("SE_API_KEY", "")
    github_token = os.getenv("GITHUB_TOKEN", "")

    if se_key:
        print(f"  Stack Exchange key: set (high quota)")
    else:
        print("  Stack Exchange key: not set (300 req/day limit — set SE_API_KEY in apps/api/.env)")
    if github_token:
        print(f"  GitHub token: set (5,000 req/hr)")
    else:
        print("  GitHub token: not set (60 req/hr limit)")

    # ── 1. Collect all unique SE tags ─────────────────────────────────────────
    all_se_tags: list[str] = []
    seen_tags: set[str] = set()
    for group in _TAG_GROUPS:
        for tag in group["tags"]:
            if tag not in seen_tags:
                all_se_tags.append(tag)
                seen_tags.add(tag)

    print(f"\n[1/3] Fetching Stack Overflow tag counts ({len(all_se_tags)} unique tags) ...")
    se_counts = fetch_se_tags(all_se_tags, se_key)
    print(f"  {len(se_counts)} tags fetched")

    # ── 2. GitHub language counts ─────────────────────────────────────────────
    all_gh_languages: list[str] = []
    seen_langs: set[str] = set()
    for group in _TAG_GROUPS:
        for lang in group.get("gh_languages", []):
            if lang not in seen_langs:
                all_gh_languages.append(lang)
                seen_langs.add(lang)

    print(f"\n[2/3] Fetching GitHub language repository counts ({len(all_gh_languages)} languages) ...")
    gh_lang_counts: dict[str, int] = {}
    for lang in all_gh_languages:
        count = fetch_gh_language_count(lang, github_token)
        gh_lang_counts[lang] = count
        print(f"  {lang}: {count:,} repos")

    # GitHub topic data
    all_gh_topics: list[str] = []
    seen_topics: set[str] = set()
    for group in _TAG_GROUPS:
        for topic in group.get("gh_topics", []):
            if topic not in seen_topics:
                all_gh_topics.append(topic)
                seen_topics.add(topic)

    print(f"\n[3/3] Fetching GitHub topic data ({len(all_gh_topics)} topics) ...")
    gh_topic_data: dict[str, tuple[int, int]] = {}
    for topic in all_gh_topics:
        repos, top_stars = fetch_gh_topic_count(topic, github_token)
        gh_topic_data[topic] = (repos, top_stars)
        print(f"  {topic}: {repos:,} repos, top repo {top_stars:,} stars")

    # ── 4. Assemble documents ─────────────────────────────────────────────────
    print("\nAssembling documents ...")
    docs: list[dict] = []
    for idx, group in enumerate(_TAG_GROUPS):
        doc = build_market_report_doc(
            group=group,
            se_counts=se_counts,
            gh_lang_counts=gh_lang_counts,
            gh_topic_data=gh_topic_data,
            doc_idx=idx + 1,
        )
        docs.append(doc)
        print(f"  Doc: {doc['title'][:70]}")

    print(f"\nTotal documents: {len(docs)}")

    if dry_run:
        print("  [dry-run] Output NOT written.")
        return docs

    output_file.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  Written: {output_file}  ({size_kb} KB)")
    return docs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description="Fetch real tech market trend data from Stack Overflow + GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default=_default_out,
        help=f"Output directory (default: {_default_out})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch data and print stats but do NOT write the output file.",
    )
    args = parser.parse_args()

    docs = fetch_market_reports(output_dir=args.output_dir, dry_run=args.dry_run)

    if not args.dry_run:
        print(
            "\nNext step — update admin_kb_controller.py _DEFAULT_SOURCE_PATHS:\n"
            "  KBDocType.market_reports: str(_KB_DIR / 'market_reports_real.json')\n"
            "\nThen ingest:\n"
            "  POST /api/v1/admin/kb/ingest\n"
            "  {'doc_types': ['market_reports']}"
        )


if __name__ == "__main__":
    main()
