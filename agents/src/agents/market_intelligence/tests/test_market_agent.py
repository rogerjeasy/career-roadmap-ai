"""Tests for the Market Intelligence Agent.

Covers:
  - _parse_postings / _parse_salary helpers: valid data, missing fields, empty input
  - SignalProcessor: skill extraction counts, github weighting, social signals,
    industry signal normalisation, relevance scoring
  - TrendSummariser: LLM success path, fallback on failure, empty data
  - MarketAgent: full pipeline, partial MCP failures, country extraction,
    output shape, progress events, BaseAgent.run() contract

All LLM and MCP calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.market_intelligence.job_board_fetcher import (
    JobBoardFetcher,
    _parse_postings,
    _to_int,
)
from agents.market_intelligence.market_agent import (
    MarketAgent,
    _collect_data_sources,
    _extract_country,
    _serialise,
    _serialise_posting,
    _serialise_salary,
    _serialise_signal,
    _serialise_skill,
)
from agents.market_intelligence.models import (
    IndustrySignal,
    JobPosting,
    MarketIntelligenceResult,
    SalaryBenchmark,
    SignalType,
    TrendDirection,
    TrendingSkill,
)
from agents.market_intelligence.salary_fetcher import SalaryFetcher, _parse_salary
from agents.market_intelligence.signal_processor import (
    SignalProcessor,
    _canonical,
    _categorise,
    _relevance,
)
from agents.market_intelligence.trend_fetcher import TrendFetcher
from agents.market_intelligence.trend_summariser import (
    TrendSummariser,
    _build_user_prompt,
    _fallback_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def trend_summariser(mock_llm: AsyncMock) -> TrendSummariser:
    return TrendSummariser(llm=mock_llm)


@pytest.fixture
def signal_processor() -> SignalProcessor:
    return SignalProcessor()


@pytest.fixture
def sample_job_postings() -> list[JobPosting]:
    return [
        JobPosting(
            title="Senior ML Engineer",
            company="TechCorp",
            location="Zurich, CH",
            required_skills=["Python", "Kubernetes", "FastAPI", "PyTorch"],
            source="LinkedIn",
            posted_date=date(2026, 5, 1),
            salary_min=100_000,
            salary_max=140_000,
            currency="CHF",
            url="https://example.com/job/1",
        ),
        JobPosting(
            title="Senior ML Engineer",
            company="DataFlow GmbH",
            location="Basel, CH",
            required_skills=["Python", "Kubernetes", "Apache Kafka", "Terraform"],
            source="Indeed",
            posted_date=date(2026, 5, 2),
            salary_min=95_000,
            salary_max=130_000,
            currency="CHF",
            url="https://example.com/job/2",
        ),
        JobPosting(
            title="Senior ML Engineer",
            company="AI Ventures",
            location="Bern, CH",
            required_skills=["Python", "FastAPI", "LangChain", "AWS"],
            source="Glassdoor",
            salary_min=105_000,
            salary_max=145_000,
            currency="CHF",
        ),
    ]


@pytest.fixture
def sample_salary() -> SalaryBenchmark:
    return SalaryBenchmark(
        role="Senior ML Engineer",
        country="CH",
        median_annual=115_000,
        p25_annual=92_000,
        p75_annual=143_750,
        currency="CHF",
        source="Levels.fyi + Glassdoor",
        freshness_date=date(2026, 5, 5),
    )


@pytest.fixture
def sample_trending_skills() -> list[TrendingSkill]:
    return [
        TrendingSkill(
            name="Python",
            category="language",
            trend_direction=TrendDirection.RISING,
            signal_count=8,
            sources=["job_board", "github_trends"],
            evidence="Mentioned in 8 market signals",
        ),
        TrendingSkill(
            name="Kubernetes",
            category="platform",
            trend_direction=TrendDirection.RISING,
            signal_count=5,
            sources=["github_trends", "job_board"],
            evidence="Mentioned in 5 market signals",
        ),
        TrendingSkill(
            name="FastAPI",
            category="framework",
            trend_direction=TrendDirection.RISING,
            signal_count=4,
            sources=["job_board"],
            evidence="Mentioned in 4 market signals",
        ),
    ]


@pytest.fixture
def sample_industry_signals() -> list[IndustrySignal]:
    return [
        IndustrySignal(
            topic="LangChain",
            signal_type=SignalType.GITHUB_TREND,
            summary="Trending on GitHub: LangChain (+4,200 stars this week) · Python",
            source="GitHub Trends",
            relevance_score=0.5,
            url=None,
            freshness_date=date(2026, 5, 5),
        ),
        IndustrySignal(
            topic="Ask HN: What skills matter most for AI engineers?",
            signal_type=SignalType.SOCIAL_SIGNAL,
            summary="Ask HN: What skills matter most for AI engineers? (450 points)",
            source="Hacker News",
            relevance_score=0.3,
            url="https://news.ycombinator.com/stub-1",
            freshness_date=date(2026, 5, 5),
        ),
    ]


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _make_context(
    target_role: str = "Senior ML Engineer",
    location: str | None = "Zurich, CH",
    skills: list[str] | None = None,
) -> AgentContext:
    profile = UserProfileSnapshot(
        target_role=target_role,
        location=location,
        skills=skills or ["Python", "FastAPI", "Docker"],
    )
    return AgentContext(
        task_id="task-mkt-001",
        session_id="sess-mkt-001",
        user_id="user-mkt-001",
        correlation_id="corr-mkt-001",
        stream_channel="channel-mkt-test",
        user_profile=profile,
    )


# ── _parse_postings ───────────────────────────────────────────────────────────


class TestParsePostings:
    def test_parses_full_posting(self):
        raw = {
            "postings": [
                {
                    "title": "ML Engineer",
                    "company": "ACME Corp",
                    "location": "Zurich, CH",
                    "required_skills": ["Python", "Docker"],
                    "source": "LinkedIn",
                    "posted_date": "2026-05-01",
                    "salary_min": 90000,
                    "salary_max": 130000,
                    "currency": "CHF",
                    "url": "https://example.com",
                }
            ]
        }
        postings = _parse_postings(raw)
        assert len(postings) == 1
        p = postings[0]
        assert p.title == "ML Engineer"
        assert p.company == "ACME Corp"
        assert p.required_skills == ["Python", "Docker"]
        assert p.posted_date == date(2026, 5, 1)
        assert p.salary_min == 90_000
        assert p.salary_max == 130_000
        assert p.currency == "CHF"
        assert p.url == "https://example.com"

    def test_skips_entry_without_title(self):
        raw = {"postings": [{"company": "ACME", "required_skills": ["Python"]}]}
        assert _parse_postings(raw) == []

    def test_handles_missing_optional_fields(self):
        raw = {
            "postings": [
                {"title": "Engineer", "company": "X", "location": "", "source": "Indeed"}
            ]
        }
        postings = _parse_postings(raw)
        assert len(postings) == 1
        assert postings[0].posted_date is None
        assert postings[0].salary_min is None
        assert postings[0].url is None

    def test_handles_invalid_date_gracefully(self):
        raw = {
            "postings": [
                {
                    "title": "Dev",
                    "company": "X",
                    "source": "Y",
                    "posted_date": "not-a-date",
                    "required_skills": [],
                }
            ]
        }
        postings = _parse_postings(raw)
        assert postings[0].posted_date is None

    def test_empty_postings_list(self):
        assert _parse_postings({"postings": []}) == []

    def test_empty_raw_dict(self):
        assert _parse_postings({}) == []

    def test_non_dict_item_skipped(self):
        raw = {"postings": ["not-a-dict", None, {"title": "Eng", "source": "X"}]}
        postings = _parse_postings(raw)
        assert len(postings) == 1


class TestToInt:
    def test_none_returns_none(self):
        assert _to_int(None) is None

    def test_int_value(self):
        assert _to_int(90000) == 90_000

    def test_string_int(self):
        assert _to_int("90000") == 90_000

    def test_invalid_string_returns_none(self):
        assert _to_int("n/a") is None


# ── _parse_salary ─────────────────────────────────────────────────────────────


class TestParseSalary:
    def test_parses_full_salary(self):
        raw = {
            "role": "ML Engineer",
            "country": "CH",
            "median_annual": 115_000,
            "p25_annual": 92_000,
            "p75_annual": 143_750,
            "currency": "CHF",
            "source": "Levels.fyi",
            "freshness_date": "2026-05-05",
        }
        benchmark = _parse_salary("ML Engineer", "CH", raw)
        assert benchmark is not None
        assert benchmark.median_annual == 115_000
        assert benchmark.currency == "CHF"
        assert benchmark.freshness_date == date(2026, 5, 5)

    def test_empty_raw_returns_none(self):
        assert _parse_salary("ML Engineer", "CH", {}) is None

    def test_handles_missing_freshness_date(self):
        raw = {
            "median_annual": 100_000,
            "p25_annual": 80_000,
            "p75_annual": 120_000,
            "currency": "USD",
            "source": "Glassdoor",
        }
        benchmark = _parse_salary("Engineer", "US", raw)
        assert benchmark is not None
        assert benchmark.freshness_date is None

    def test_role_and_country_fallback_to_params(self):
        raw = {"median_annual": 80_000, "currency": "EUR", "source": "X"}
        benchmark = _parse_salary("Dev", "DE", raw)
        assert benchmark is not None
        assert benchmark.role == "Dev"
        assert benchmark.country == "DE"


# ── SignalProcessor ───────────────────────────────────────────────────────────


class TestSignalProcessorExtractSkills:
    def test_counts_job_posting_skills(
        self,
        signal_processor: SignalProcessor,
        sample_job_postings: list[JobPosting],
    ):
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, [], []
        )
        names = [s.name for s in skills]
        assert "Python" in names  # appears 3 times

    def test_python_has_highest_count(
        self,
        signal_processor: SignalProcessor,
        sample_job_postings: list[JobPosting],
    ):
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, [], []
        )
        top = skills[0]
        assert top.name == "Python"
        assert top.signal_count == 3

    def test_github_trends_add_weight(self, signal_processor: SignalProcessor):
        github = [
            {"topic": "Kubernetes", "stars_this_week": 4000},
        ]
        skills = signal_processor.extract_trending_skills([], github, [])
        k8s = next(s for s in skills if s.name == "Kubernetes")
        assert k8s.signal_count >= 4  # 1 + 4000//1000 = 5

    def test_rising_direction_when_count_gte_3(
        self, signal_processor: SignalProcessor, sample_job_postings: list[JobPosting]
    ):
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, [], []
        )
        python_skill = next(s for s in skills if s.name == "Python")
        assert python_skill.trend_direction == TrendDirection.RISING

    def test_stable_direction_when_count_lt_3(self, signal_processor: SignalProcessor):
        postings = [
            JobPosting(
                title="Dev",
                company="X",
                location="",
                required_skills=["Scala"],
                source="Y",
            )
        ]
        skills = signal_processor.extract_trending_skills(postings, [], [])
        scala = next(s for s in skills if "Scala" in s.name)
        assert scala.trend_direction == TrendDirection.STABLE

    def test_sources_populated(
        self, signal_processor: SignalProcessor, sample_job_postings: list[JobPosting]
    ):
        github = [{"topic": "Python", "stars_this_week": 2000}]
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, github, []
        )
        python_skill = next(s for s in skills if s.name == "Python")
        assert "job_board" in python_skill.sources
        assert "github_trends" in python_skill.sources

    def test_top_n_respected(
        self, signal_processor: SignalProcessor, sample_job_postings: list[JobPosting]
    ):
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, [], [], top_n=2
        )
        assert len(skills) <= 2

    def test_empty_inputs_return_empty(self, signal_processor: SignalProcessor):
        assert signal_processor.extract_trending_skills([], [], []) == []

    def test_social_signals_contribute(self, signal_processor: SignalProcessor):
        social = [
            {"title": "Rust", "_source": "hackernews"},
            {"title": "Rust", "_source": "reddit"},
            {"title": "Rust", "_source": "social_aggregate"},
        ]
        skills = signal_processor.extract_trending_skills([], [], social)
        rust = next(s for s in skills if "Rust" in s.name)
        assert rust.signal_count == 3

    def test_evidence_string_includes_count(
        self, signal_processor: SignalProcessor, sample_job_postings: list[JobPosting]
    ):
        skills = signal_processor.extract_trending_skills(
            sample_job_postings, [], []
        )
        python_skill = next(s for s in skills if s.name == "Python")
        assert "3" in python_skill.evidence


class TestSignalProcessorIndustrySignals:
    def test_github_trend_signal_type(self, signal_processor: SignalProcessor):
        github = [{"topic": "LangChain", "stars_this_week": 4200, "language": "Python"}]
        signals = signal_processor.normalise_industry_signals(github, [], "ML Engineer")
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.GITHUB_TREND
        assert signals[0].source == "GitHub Trends"
        assert "LangChain" in signals[0].summary
        assert "4,200" in signals[0].summary

    def test_social_signal_type(self, signal_processor: SignalProcessor):
        social = [{"title": "Python is great", "points": 500, "_source": "hackernews"}]
        signals = signal_processor.normalise_industry_signals([], social, "Engineer")
        assert signals[0].signal_type == SignalType.SOCIAL_SIGNAL
        assert signals[0].source == "Hacker News"
        assert "500" in signals[0].summary

    def test_reddit_source_label(self, signal_processor: SignalProcessor):
        social = [{"title": "Rust topic", "upvotes": 300, "_source": "reddit"}]
        signals = signal_processor.normalise_industry_signals([], social, "Dev")
        assert signals[0].source == "Reddit"
        assert "upvotes" in signals[0].summary

    def test_signals_sorted_by_relevance_descending(self, signal_processor: SignalProcessor):
        github = [
            {"topic": "Python ML engineering tips", "stars_this_week": 1000},
            {"topic": "CSS art project", "stars_this_week": 100},
        ]
        signals = signal_processor.normalise_industry_signals(
            github, [], "ML Engineer"
        )
        assert signals[0].relevance_score >= signals[-1].relevance_score

    def test_empty_topic_skipped(self, signal_processor: SignalProcessor):
        github = [{"topic": "", "stars_this_week": 100}]
        signals = signal_processor.normalise_industry_signals(github, [], "Dev")
        assert signals == []

    def test_freshness_date_set(self, signal_processor: SignalProcessor):
        github = [{"topic": "FastAPI", "stars_this_week": 500}]
        fixed = datetime(2026, 5, 5, 12, 0, 0)
        signals = signal_processor.normalise_industry_signals(
            github, [], "Engineer", today=fixed
        )
        assert signals[0].freshness_date == date(2026, 5, 5)


class TestSignalProcessorHelpers:
    def test_canonical_known_skill(self):
        assert _canonical("fastapi") == "FastAPI"
        assert _canonical("kubernetes") == "Kubernetes"
        assert _canonical("aws") == "AWS"

    def test_canonical_unknown_skill_title_case(self):
        assert _canonical("some new tool") == "Some New Tool"

    def test_categorise_known_language(self):
        assert _categorise("python") == "language"
        assert _categorise("rust") == "language"

    def test_categorise_known_platform(self):
        assert _categorise("kubernetes") == "platform"
        assert _categorise("docker") == "platform"

    def test_categorise_ai_ml(self):
        assert _categorise("llm") == "ai_ml"
        assert _categorise("machine learning") == "ai_ml"

    def test_categorise_unknown_defaults_to_tech(self):
        assert _categorise("some-obscure-thing") == "tech"

    def test_relevance_zero_for_empty(self):
        assert _relevance("", set()) == 0.0
        assert _relevance("topic", set()) == 0.0

    def test_relevance_one_for_exact_match(self):
        score = _relevance("ml engineer", {"ml", "engineer"})
        assert score == 1.0

    def test_relevance_partial_overlap(self):
        score = _relevance("ml data science", {"ml", "engineer"})
        assert 0.0 < score < 1.0

    def test_relevance_no_overlap(self):
        assert _relevance("css art project", {"python", "ml"}) == 0.0


# ── TrendSummariser ───────────────────────────────────────────────────────────


class TestBuildUserPrompt:
    def test_includes_role_and_country(
        self,
        sample_salary: SalaryBenchmark,
        sample_trending_skills: list[TrendingSkill],
    ):
        prompt = _build_user_prompt(
            "ML Engineer", "CH", sample_trending_skills, sample_salary, [], 42
        )
        assert "ML Engineer" in prompt
        assert "CH" in prompt
        assert "42" in prompt

    def test_includes_salary_figures(
        self,
        sample_salary: SalaryBenchmark,
        sample_trending_skills: list[TrendingSkill],
    ):
        prompt = _build_user_prompt(
            "ML Engineer", "CH", sample_trending_skills, sample_salary, [], 10
        )
        assert "115,000" in prompt
        assert "CHF" in prompt

    def test_no_salary_shows_not_available(
        self, sample_trending_skills: list[TrendingSkill]
    ):
        prompt = _build_user_prompt("Dev", "DE", sample_trending_skills, None, [], 5)
        assert "not available" in prompt

    def test_includes_trending_skill_names(
        self,
        sample_trending_skills: list[TrendingSkill],
        sample_salary: SalaryBenchmark,
    ):
        prompt = _build_user_prompt(
            "Dev", "CH", sample_trending_skills, sample_salary, [], 5
        )
        assert "Python" in prompt
        assert "Kubernetes" in prompt

    def test_empty_skills_shows_none_identified(self):
        prompt = _build_user_prompt("Dev", "CH", [], None, [], 0)
        assert "none identified" in prompt


class TestFallbackSummary:
    def test_includes_role_and_country(
        self, sample_trending_skills: list[TrendingSkill], sample_salary: SalaryBenchmark
    ):
        result = _fallback_summary(
            "ML Engineer", "CH", sample_trending_skills, sample_salary, 42
        )
        assert "ML Engineer" in result
        assert "CH" in result
        assert "42" in result

    def test_includes_salary_when_present(
        self, sample_trending_skills: list[TrendingSkill], sample_salary: SalaryBenchmark
    ):
        result = _fallback_summary(
            "ML Engineer", "CH", sample_trending_skills, sample_salary, 10
        )
        assert "115,000" in result
        assert "CHF" in result

    def test_includes_top_skills(
        self, sample_trending_skills: list[TrendingSkill]
    ):
        result = _fallback_summary("Dev", "CH", sample_trending_skills, None, 5)
        assert "Python" in result

    def test_includes_freshness_note(self):
        result = _fallback_summary("Dev", "CH", [], None, 0)
        assert "freshness" in result.lower() or "real-time" in result.lower()

    def test_no_salary_still_returns_summary(self):
        result = _fallback_summary("Dev", "CH", [], None, 0)
        assert isinstance(result, str)
        assert len(result) > 0


class TestTrendSummariserAsync:
    async def test_successful_llm_summarise(
        self,
        trend_summariser: TrendSummariser,
        mock_llm: AsyncMock,
        sample_trending_skills: list[TrendingSkill],
        sample_salary: SalaryBenchmark,
        sample_industry_signals: list[IndustrySignal],
    ):
        payload = {"summary": "Strong demand for ML Engineers in CH with CHF 115k median salary."}
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await trend_summariser.summarise(
            "ML Engineer", "CH",
            sample_trending_skills, sample_salary, sample_industry_signals, 42,
        )
        assert "ML Engineer" in result or "115k" in result or len(result) > 0

    async def test_llm_failure_returns_fallback_text(
        self,
        trend_summariser: TrendSummariser,
        mock_llm: AsyncMock,
        sample_trending_skills: list[TrendingSkill],
        sample_salary: SalaryBenchmark,
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await trend_summariser.summarise(
            "ML Engineer", "CH", sample_trending_skills, sample_salary, [], 10,
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert "ML Engineer" in result

    async def test_invalid_json_returns_fallback(
        self,
        trend_summariser: TrendSummariser,
        mock_llm: AsyncMock,
    ):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not valid json"))
        result = await trend_summariser.summarise(
            "Dev", "DE", [], None, [], 0,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_missing_summary_key_returns_fallback(
        self,
        trend_summariser: TrendSummariser,
        mock_llm: AsyncMock,
    ):
        mock_llm.ainvoke = AsyncMock(
            return_value=_llm_response(json.dumps({"other_key": "value"}))
        )
        result = await trend_summariser.summarise("Dev", "DE", [], None, [], 0)
        assert isinstance(result, str)

    async def test_empty_data_returns_summary(
        self,
        trend_summariser: TrendSummariser,
        mock_llm: AsyncMock,
    ):
        payload = {"summary": "No data available yet."}
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await trend_summariser.summarise("Dev", "CH", [], None, [], 0)
        assert isinstance(result, str)


# ── _extract_country ──────────────────────────────────────────────────────────


class TestExtractCountry:
    def test_two_letter_code_last_part(self):
        assert _extract_country("Zurich, CH") == "CH"
        assert _extract_country("Berlin, DE") == "DE"
        assert _extract_country("Paris, FR") == "FR"

    def test_standalone_code(self):
        assert _extract_country("CH") == "CH"
        assert _extract_country("US") == "US"

    def test_country_name_in_string(self):
        assert _extract_country("Berlin, Germany") == "DE"
        assert _extract_country("Paris, France") == "FR"
        assert _extract_country("Zurich, Switzerland") == "CH"

    def test_none_returns_default(self):
        assert _extract_country(None) == "CH"

    def test_empty_string_returns_default(self):
        assert _extract_country("") == "CH"

    def test_us_city_state(self):
        # "San Francisco, CA" — CA is a US state, should return US
        assert _extract_country("San Francisco, CA") == "US"

    def test_us_city_state_country(self):
        assert _extract_country("New York, NY, US") == "US"

    def test_unknown_location_returns_default(self):
        assert _extract_country("Remote") == "CH"


# ── Serialisers ───────────────────────────────────────────────────────────────


class TestSerialisers:
    def test_serialise_posting_keys(self, sample_job_postings: list[JobPosting]):
        out = _serialise_posting(sample_job_postings[0])
        for key in (
            "title", "company", "location", "required_skills", "source",
            "posted_date", "salary_min", "salary_max", "currency", "url",
        ):
            assert key in out

    def test_serialise_posting_date_isoformat(self, sample_job_postings: list[JobPosting]):
        out = _serialise_posting(sample_job_postings[0])
        assert out["posted_date"] == "2026-05-01"

    def test_serialise_posting_none_date(self):
        p = JobPosting(
            title="Dev", company="X", location="", required_skills=[], source="Y"
        )
        assert _serialise_posting(p)["posted_date"] is None

    def test_serialise_salary_none_returns_none(self):
        assert _serialise_salary(None) is None

    def test_serialise_salary_keys(self, sample_salary: SalaryBenchmark):
        out = _serialise_salary(sample_salary)
        assert out is not None
        for key in (
            "role", "country", "median_annual", "p25_annual", "p75_annual",
            "currency", "source", "freshness_date",
        ):
            assert key in out

    def test_serialise_skill_enum_is_string(
        self, sample_trending_skills: list[TrendingSkill]
    ):
        out = _serialise_skill(sample_trending_skills[0])
        assert isinstance(out["trend_direction"], str)

    def test_serialise_signal_enum_is_string(
        self, sample_industry_signals: list[IndustrySignal]
    ):
        out = _serialise_signal(sample_industry_signals[0])
        assert isinstance(out["signal_type"], str)

    def test_collect_data_sources_deduplicates(
        self, sample_job_postings: list[JobPosting], sample_salary: SalaryBenchmark
    ):
        sources = _collect_data_sources(sample_job_postings, sample_salary)
        assert len(sources) == len(set(sources))
        assert "LinkedIn" in sources
        assert "Levels.fyi + Glassdoor" in sources


# ── MarketAgent ───────────────────────────────────────────────────────────────


class TestMarketAgent:
    def _make_agent(
        self,
        job_postings: list[JobPosting] | None = None,
        salary: SalaryBenchmark | None = None,
        github_trends: list[dict] | None = None,
        social_signals: list[dict] | None = None,
        llm_summary: str = "Strong market for ML Engineers.",
        emit_events: bool = False,
    ) -> tuple[MarketAgent, AsyncMock]:
        _postings = job_postings or []
        _salary = salary
        _github = github_trends or []
        _social = social_signals or []

        mock_job_fetcher = AsyncMock(spec=JobBoardFetcher)
        mock_salary_fetcher = AsyncMock(spec=SalaryFetcher)
        mock_trend_fetcher = AsyncMock(spec=TrendFetcher)
        mock_summariser = AsyncMock(spec=TrendSummariser)
        mock_publisher = MagicMock() if emit_events else None

        mock_job_fetcher.fetch = AsyncMock(return_value=_postings)
        mock_salary_fetcher.fetch = AsyncMock(return_value=_salary)
        mock_trend_fetcher.fetch = AsyncMock(return_value=(_github, _social))
        mock_summariser.summarise = AsyncMock(return_value=llm_summary)

        agent = MarketAgent(
            job_board_fetcher=mock_job_fetcher,
            salary_fetcher=mock_salary_fetcher,
            trend_fetcher=mock_trend_fetcher,
            signal_processor=SignalProcessor(),
            trend_summariser=mock_summariser,
            event_publisher=mock_publisher,
        )
        return agent, mock_summariser

    def test_agent_type(self):
        agent, _ = self._make_agent()
        assert agent.agent_type == AgentType.MARKET_INTELLIGENCE

    def test_display_name(self):
        agent, _ = self._make_agent()
        assert agent.display_name == "Market Intelligence Agent"

    async def test_execute_returns_required_keys(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context())
        for key in (
            "role", "country", "job_postings", "salary_benchmark",
            "trending_skills", "industry_signals", "market_summary",
            "fetched_at", "data_sources", "processing_steps",
        ):
            assert key in result

    async def test_execute_has_three_processing_steps(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context())
        assert len(result["processing_steps"]) == 3

    async def test_role_from_user_profile(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context(target_role="Data Engineer"))
        assert result["role"] == "Data Engineer"

    async def test_country_extracted_from_location(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context(location="Berlin, DE"))
        assert result["country"] == "DE"

    async def test_country_defaults_when_no_location(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context(location=None))
        assert result["country"] == "CH"

    async def test_no_role_defaults_to_software_engineer(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context(target_role=None))
        assert result["role"] == "Software Engineer"

    async def test_market_summary_in_output(self):
        agent, _ = self._make_agent(llm_summary="Great market for AI engineers.")
        result = await agent._execute(_make_context())
        assert result["market_summary"] == "Great market for AI engineers."

    async def test_salary_none_when_fetcher_returns_none(self):
        agent, _ = self._make_agent(salary=None)
        result = await agent._execute(_make_context())
        assert result["salary_benchmark"] is None

    async def test_salary_serialised_when_present(
        self, sample_salary: SalaryBenchmark
    ):
        agent, _ = self._make_agent(salary=sample_salary)
        result = await agent._execute(_make_context())
        assert result["salary_benchmark"] is not None
        assert result["salary_benchmark"]["currency"] == "CHF"

    async def test_job_postings_serialised(
        self, sample_job_postings: list[JobPosting]
    ):
        agent, _ = self._make_agent(job_postings=sample_job_postings)
        result = await agent._execute(_make_context())
        assert len(result["job_postings"]) == 3
        assert result["job_postings"][0]["title"] == "Senior ML Engineer"

    async def test_trending_skills_aggregated(
        self, sample_job_postings: list[JobPosting]
    ):
        agent, _ = self._make_agent(job_postings=sample_job_postings)
        result = await agent._execute(_make_context())
        assert len(result["trending_skills"]) > 0
        top = result["trending_skills"][0]
        assert top["name"] == "Python"  # Python appears 3× in sample postings

    async def test_three_progress_events_emitted(self):
        agent, _ = self._make_agent(emit_events=True)
        await agent._execute(_make_context())
        assert agent._event_publisher.emit.call_count == 3

    async def test_no_events_without_publisher(self):
        agent, _ = self._make_agent(emit_events=False)
        result = await agent._execute(_make_context())
        assert "role" in result

    async def test_fetched_at_is_iso8601(self):
        agent, _ = self._make_agent()
        result = await agent._execute(_make_context())
        # Should parse without error
        dt = datetime.fromisoformat(result["fetched_at"])
        assert dt.year == 2026

    async def test_summariser_receives_correct_args(
        self, sample_job_postings: list[JobPosting], sample_salary: SalaryBenchmark
    ):
        agent, mock_summariser = self._make_agent(
            job_postings=sample_job_postings,
            salary=sample_salary,
        )
        await agent._execute(_make_context(target_role="ML Engineer"))
        call_kwargs = mock_summariser.summarise.call_args
        assert call_kwargs[0][0] == "ML Engineer"  # role positional arg

    async def test_full_pipeline_via_base_agent_run(self):
        agent, _ = self._make_agent()
        result = await agent.run(_make_context())
        assert result.agent_type == AgentType.MARKET_INTELLIGENCE.value
        assert result.status == AgentResultStatus.COMPLETED
        assert "role" in result.output
        assert result.duration_ms >= 0

    async def test_run_returns_failed_on_unexpected_error(self):
        agent, _ = self._make_agent()
        agent._job_board_fetcher.fetch = AsyncMock(side_effect=RuntimeError("catastrophic"))
        result = await agent.run(_make_context())
        assert result.status == AgentResultStatus.FAILED

    async def test_partial_failure_job_board_still_returns_salary(
        self, sample_salary: SalaryBenchmark
    ):
        # Even when job board fails (returns empty list), salary is still returned.
        agent, _ = self._make_agent(job_postings=[], salary=sample_salary)
        result = await agent._execute(_make_context())
        assert result["salary_benchmark"] is not None
        assert result["job_postings"] == []

    async def test_industry_signals_present(self):
        github = [
            {"topic": "LangChain", "stars_this_week": 4200, "language": "Python"},
        ]
        agent, _ = self._make_agent(github_trends=github)
        result = await agent._execute(_make_context())
        assert len(result["industry_signals"]) > 0

    async def test_full_stub_client_pipeline(self):
        """End-to-end with StubMCPClient — no real LLM but realistic MCP data."""
        from agents.market_intelligence.mcp_client import StubMCPClient

        mock_summariser = AsyncMock(spec=TrendSummariser)
        mock_summariser.summarise = AsyncMock(return_value="Stub market summary.")

        stub = StubMCPClient()
        agent = MarketAgent(
            job_board_fetcher=JobBoardFetcher(stub),
            salary_fetcher=SalaryFetcher(stub),
            trend_fetcher=TrendFetcher(stub),
            signal_processor=SignalProcessor(),
            trend_summariser=mock_summariser,
        )
        result = await agent._execute(_make_context(target_role="ML Engineer"))
        assert result["role"] == "ML Engineer"
        assert len(result["job_postings"]) >= 3
        assert result["salary_benchmark"] is not None
        assert len(result["trending_skills"]) > 0
        assert result["market_summary"] == "Stub market summary."
