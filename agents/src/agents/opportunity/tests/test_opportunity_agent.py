"""Unit tests for the OpportunityAgent.

All LLM calls and MCP calls are mocked — no network access.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.opportunity.cv_tailor import CVTailor, _fallback_snippet, _parse_snippet
from agents.opportunity.job_scorer import (
    JobScorer,
    _deterministic_score,
    _seniority_match,
)
from agents.opportunity.mcp_client import _parse_listing
from agents.opportunity.models import (
    JobListing,
    JobMatchScore,
    OpportunityOutput,
)
from agents.opportunity.opportunity_agent import (
    OpportunityAgent,
    _build_alerts,
    _extract_target_companies,
)


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
def profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="Senior Python Developer",
        current_role="Python Developer",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
        goals=["Lead a backend team", "Work on distributed systems"],
        location="Berlin",
        timeline_months=12,
        weekly_hours_available=20,
        salary_goal=100_000,
    )


@pytest.fixture
def listings() -> list[JobListing]:
    return [
        JobListing(
            id="job-1",
            title="Senior Python Developer",
            company="TechCorp",
            location="Berlin",
            description="Join our team building scalable APIs with Python and FastAPI.",
            required_skills=["Python", "FastAPI", "PostgreSQL"],
            salary_min=90_000,
            salary_max=120_000,
            remote=False,
            seniority_level="senior",
        ),
        JobListing(
            id="job-2",
            title="Backend Engineer",
            company="StartupXYZ",
            location="Remote",
            description="Build microservices with Python and Docker.",
            required_skills=["Python", "Docker", "Kubernetes"],
            salary_min=80_000,
            salary_max=110_000,
            remote=True,
            seniority_level="mid",
        ),
        JobListing(
            id="job-3",
            title="Junior Developer",
            company="Agency Co",
            location="Munich",
            description="Entry-level position for Python enthusiasts.",
            required_skills=["Python", "Django"],
            salary_min=40_000,
            salary_max=55_000,
            remote=False,
            seniority_level="junior",
        ),
    ]


@pytest.fixture
def context(profile: UserProfileSnapshot) -> AgentContext:
    return AgentContext(
        task_id="task-123",
        session_id="session-abc",
        user_id="user-xyz",
        correlation_id="corr-001",
        stream_channel="channel:user-xyz:session-abc",
        user_profile=profile,
        user_message="Find me relevant job opportunities",
    )


# ── JobListing parsing ──────────────────────────────────────────────────────────


def test_parse_listing_full():
    raw = {
        "id": "42",
        "title": "Staff Engineer",
        "company": "BigCo",
        "location": "London",
        "description": "Great role.",
        "required_skills": ["Go", "Kubernetes"],
        "salary_range": {"min": 100_000, "max": 150_000},
        "posted_at": "2024-01-15",
        "url": "https://example.com/jobs/42",
        "remote": True,
        "seniority_level": "staff",
    }
    listing = _parse_listing(raw)
    assert listing.id == "42"
    assert listing.salary_min == 100_000
    assert listing.salary_max == 150_000
    assert listing.remote is True
    assert listing.seniority_level == "staff"


def test_parse_listing_minimal():
    listing = _parse_listing({"id": "1", "title": "Dev", "company": "Acme", "location": "", "description": ""})
    assert listing.salary_min is None
    assert listing.required_skills == []
    assert listing.remote is False


def test_parse_listing_no_salary_range():
    listing = _parse_listing({"id": "2", "title": "Dev", "company": "Co", "salary_range": None})
    assert listing.salary_min is None
    assert listing.salary_max is None


# ── Deterministic scoring ───────────────────────────────────────────────────────


def test_deterministic_score_high_match(listings, profile):
    job = listings[0]  # Senior Python Dev in Berlin — strong overlap
    scored = _deterministic_score(job, profile)
    assert scored.match_score >= 0.65
    assert scored.is_high_match is True
    assert "Python" in scored.skill_overlap
    assert "FastAPI" in scored.skill_overlap
    assert scored.location_fit is True


def test_deterministic_score_remote_always_location_fit(listings, profile):
    job = listings[1]  # remote listing
    scored = _deterministic_score(job, profile)
    assert scored.location_fit is True


def test_deterministic_score_salary_below_goal(profile):
    listing = JobListing(
        id="cheap",
        title="Dev",
        company="Co",
        location="Berlin",
        description="",
        salary_max=50_000,
    )
    scored = _deterministic_score(listing, profile)
    assert scored.salary_fit is False


def test_deterministic_score_salary_meets_goal(profile):
    listing = JobListing(
        id="good-pay",
        title="Dev",
        company="Co",
        location="Berlin",
        description="",
        salary_max=110_000,
    )
    scored = _deterministic_score(listing, profile)
    assert scored.salary_fit is True


def test_deterministic_score_no_salary_goal():
    no_goal_profile = UserProfileSnapshot(target_role="Dev", skills=["Python"])
    listing = JobListing(id="1", title="Dev", company="Co", location="NY", description="")
    scored = _deterministic_score(listing, no_goal_profile)
    assert scored.salary_fit is None


def test_deterministic_score_no_required_skills():
    """Listing with no required skills scores skill_score = 1.0 (max benefit of doubt)."""
    listing = JobListing(id="1", title="Dev", company="Co", location="Berlin", description="")
    profile = UserProfileSnapshot(target_role="Dev", skills=["Python"])
    scored = _deterministic_score(listing, profile)
    assert scored.skill_overlap == []
    assert scored.missing_skills == []


def test_deterministic_missing_skills_populated(listings, profile):
    job = listings[1]  # requires Kubernetes which user doesn't have
    scored = _deterministic_score(job, profile)
    assert "Kubernetes" in scored.missing_skills


# ── Seniority matching ──────────────────────────────────────────────────────────


def test_seniority_senior_to_senior():
    assert _seniority_match("senior", "Senior Developer", "Lead Engineer") == 1.0


def test_seniority_junior_to_junior():
    assert _seniority_match("junior", "Junior Dev", "Associate Engineer") == 1.0


def test_seniority_senior_listing_junior_profile():
    score = _seniority_match("senior", "Junior Developer", "Mid-level Developer")
    assert score < 0.7


def test_seniority_junior_listing_senior_profile():
    score = _seniority_match("junior", "Senior Dev", "Principal Engineer")
    assert score < 0.7


def test_seniority_unknown_is_neutral():
    assert _seniority_match(None, "Developer", "Engineer") == 0.8


# ── JobScorer ──────────────────────────────────────────────────────────────────


def test_scorer_scores_all_and_sorts_descending(listings, profile):
    scorer = JobScorer(llm=None)
    scored = scorer.score_all(listings, profile)
    assert len(scored) == 3
    scores = [j.match_score for j in scored]
    assert scores == sorted(scores, reverse=True)


def test_scorer_job1_scores_highest(listings, profile):
    scorer = JobScorer(llm=None)
    scored = scorer.score_all(listings, profile)
    assert scored[0].listing.id == "job-1"


@pytest.mark.asyncio
async def test_scorer_enrich_top_no_op_without_llm(listings, profile):
    scorer = JobScorer(llm=None)
    scored = scorer.score_all(listings, profile)
    enriched = await scorer.enrich_top(scored, profile)
    assert enriched[0].match_reasons == []


@pytest.mark.asyncio
async def test_scorer_enrich_top_applies_match_reasons(listings, profile):
    mock_llm = AsyncMock()
    enrichments = json.dumps([
        {"index": 0, "match_reasons": ["Strong Python match", "Berlin location", "Senior level"], "missing_skills": []},
        {"index": 1, "match_reasons": ["Remote role", "Docker match", "Good pay"], "missing_skills": ["Kubernetes"]},
        {"index": 2, "match_reasons": ["Python base"], "missing_skills": ["Django"]},
    ])
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=enrichments))
    scorer = JobScorer(llm=mock_llm)
    scored = scorer.score_all(listings, profile)
    enriched = await scorer.enrich_top(scored, profile)
    first = enriched[0]
    assert len(first.match_reasons) == 3
    assert "Strong Python match" in first.match_reasons


@pytest.mark.asyncio
async def test_scorer_enrich_fallback_on_llm_error(listings, profile):
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
    scorer = JobScorer(llm=mock_llm)
    scored = scorer.score_all(listings, profile)
    result = await scorer.enrich_top(scored, profile)
    # Falls back silently — returns original scored list
    assert len(result) == len(scored)


@pytest.mark.asyncio
async def test_scorer_enrich_handles_markdown_fenced_json(listings, profile):
    mock_llm = AsyncMock()
    enrichments = "```json\n" + json.dumps([
        {"index": 0, "match_reasons": ["reason1", "reason2", "reason3"], "missing_skills": []},
    ]) + "\n```"
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=enrichments))
    scorer = JobScorer(llm=mock_llm)
    scored = scorer.score_all(listings[:1], profile)
    enriched = await scorer.enrich_top(scored, profile)
    assert enriched[0].match_reasons == ["reason1", "reason2", "reason3"]


# ── CVTailor ──────────────────────────────────────────────────────────────────


def test_fallback_snippet_structure():
    job = JobMatchScore(
        listing=JobListing(id="1", title="Dev", company="Acme", location="NY", description=""),
        match_score=0.8,
        skill_overlap=["Python", "FastAPI"],
        is_high_match=True,
    )
    snippet = _fallback_snippet(job)
    assert snippet.job_id == "1"
    assert "Acme" in snippet.summary_bullet
    assert len(snippet.skill_highlights) > 0


def test_parse_snippet_maps_raw_fields():
    job = JobMatchScore(
        listing=JobListing(id="99", title="Engineer", company="Corp", location="NYC", description=""),
        match_score=0.75,
        is_high_match=True,
    )
    raw = {
        "summary_bullet": "Seasoned engineer building distributed systems.",
        "skill_highlights": ["Built APIs serving 10k rps", "Reduced latency by 30%"],
        "keywords_to_include": ["Python", "Kubernetes"],
    }
    snippet = _parse_snippet(job, raw)
    assert snippet.job_id == "99"
    assert snippet.summary_bullet == "Seasoned engineer building distributed systems."
    assert len(snippet.skill_highlights) == 2
    assert "Python" in snippet.keywords_to_include


@pytest.mark.asyncio
async def test_tailor_no_llm_returns_fallbacks(listings, profile):
    tailor = CVTailor(llm=None)
    job = JobMatchScore(listing=listings[0], match_score=0.85, skill_overlap=["Python"], is_high_match=True)
    snippets = await tailor.tailor([job], profile)
    assert len(snippets) == 1
    assert snippets[0].job_id == "job-1"


@pytest.mark.asyncio
async def test_tailor_empty_list_returns_empty(profile):
    tailor = CVTailor(llm=None)
    snippets = await tailor.tailor([], profile)
    assert snippets == []


@pytest.mark.asyncio
async def test_tailor_with_llm_success(listings, profile):
    mock_llm = AsyncMock()
    llm_output = json.dumps([{
        "summary_bullet": "Seasoned Python engineer building scalable FastAPI services.",
        "skill_highlights": ["Built REST APIs serving 10k+ rps", "Reduced DB query time by 40%"],
        "keywords_to_include": ["Python", "FastAPI", "PostgreSQL"],
    }])
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=llm_output))
    tailor = CVTailor(llm=mock_llm)
    job = JobMatchScore(listing=listings[0], match_score=0.85, skill_overlap=["Python", "FastAPI"], is_high_match=True)
    snippets = await tailor.tailor([job], profile)
    assert snippets[0].summary_bullet.startswith("Seasoned")
    assert len(snippets[0].skill_highlights) == 2
    assert "Python" in snippets[0].keywords_to_include


@pytest.mark.asyncio
async def test_tailor_fallback_on_llm_error(listings, profile):
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    tailor = CVTailor(llm=mock_llm)
    job = JobMatchScore(listing=listings[0], match_score=0.85, is_high_match=True)
    snippets = await tailor.tailor([job], profile)
    assert len(snippets) == 1
    assert snippets[0].job_id == "job-1"


@pytest.mark.asyncio
async def test_tailor_caps_at_five_jobs(listings, profile):
    tailor = CVTailor(llm=None)
    many_jobs = [
        JobMatchScore(
            listing=JobListing(id=f"j{i}", title="Dev", company=f"Co{i}", location="Berlin", description=""),
            match_score=0.8,
            is_high_match=True,
        )
        for i in range(8)
    ]
    snippets = await tailor.tailor(many_jobs, profile)
    assert len(snippets) == 5


# ── Target companies & alerts ──────────────────────────────────────────────────


def test_extract_target_companies_groups_by_company():
    jobs = [
        JobMatchScore(
            listing=JobListing(id="j1", title="Senior Dev", company="TechCorp", location="Berlin", description=""),
            match_score=0.85,
            is_high_match=True,
        ),
        JobMatchScore(
            listing=JobListing(id="j2", title="Lead Dev", company="TechCorp", location="Berlin", description=""),
            match_score=0.80,
            is_high_match=True,
        ),
        JobMatchScore(
            listing=JobListing(id="j3", title="Backend Eng", company="StartupXYZ", location="Remote", description=""),
            match_score=0.72,
            is_high_match=True,
        ),
    ]
    companies = _extract_target_companies(jobs)
    techcorp = next((c for c in companies if c.name == "TechCorp"), None)
    assert techcorp is not None
    assert techcorp.job_count == 2
    assert techcorp.avg_match_score == pytest.approx(0.825)


def test_extract_target_companies_excludes_single_low_match():
    jobs = [
        JobMatchScore(
            listing=JobListing(id="j1", title="Dev", company="SmallCo", location="NYC", description=""),
            match_score=0.66,
            is_high_match=True,
        ),
    ]
    companies = _extract_target_companies(jobs)
    # Single listing and score < 0.75 — should be excluded
    assert all(c.name != "SmallCo" for c in companies)


def test_extract_target_companies_includes_single_high_score():
    jobs = [
        JobMatchScore(
            listing=JobListing(id="j1", title="Dev", company="TopCo", location="NYC", description=""),
            match_score=0.9,
            is_high_match=True,
        ),
    ]
    companies = _extract_target_companies(jobs)
    topco = next((c for c in companies if c.name == "TopCo"), None)
    assert topco is not None


def test_build_alerts_max_five():
    jobs = [
        JobMatchScore(
            listing=JobListing(id=f"j{i}", title=f"Role {i}", company=f"Co{i}", location="NYC", description=""),
            match_score=0.9 - i * 0.05,
            is_high_match=True,
        )
        for i in range(8)
    ]
    alerts = _build_alerts(jobs)
    assert len(alerts) == 5
    assert "Strong match" in alerts[0]
    assert "Role 0" in alerts[0]


def test_build_alerts_includes_location():
    jobs = [
        JobMatchScore(
            listing=JobListing(id="j1", title="Dev", company="Co", location="Berlin", description=""),
            match_score=0.85,
            is_high_match=True,
        )
    ]
    alerts = _build_alerts(jobs)
    assert "Berlin" in alerts[0]


# ── OpportunityAgent integration ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opportunity_agent_full_run(context, listings, profile):
    mock_job_board = AsyncMock()
    mock_job_board.search_jobs = AsyncMock(return_value=listings)

    agent = OpportunityAgent(
        llm=None,
        job_board_client=mock_job_board,
        job_scorer=JobScorer(llm=None),
        cv_tailor=CVTailor(llm=None),
    )
    result = await agent._execute(context)

    assert result["total_listings_fetched"] == 3
    assert isinstance(result["scored_jobs"], list)
    assert isinstance(result["high_match_jobs"], list)
    assert isinstance(result["cv_tailoring"], list)
    assert isinstance(result["target_companies"], list)
    assert isinstance(result["match_alerts"], list)
    assert result["search_query"] == "Senior Python Developer"
    assert result["timestamp"] != ""


@pytest.mark.asyncio
async def test_opportunity_agent_returns_empty_on_no_listings(context):
    mock_job_board = AsyncMock()
    mock_job_board.search_jobs = AsyncMock(return_value=[])

    agent = OpportunityAgent(
        llm=None,
        job_board_client=mock_job_board,
    )
    result = await agent._execute(context)
    assert result["total_listings_fetched"] == 0
    assert result["scored_jobs"] == []
    assert result["high_match_jobs"] == []


@pytest.mark.asyncio
async def test_opportunity_agent_handles_mcp_failure(context):
    mock_job_board = AsyncMock()
    mock_job_board.search_jobs = AsyncMock(side_effect=RuntimeError("MCP unavailable"))

    agent = OpportunityAgent(
        llm=None,
        job_board_client=mock_job_board,
    )
    result = await agent._execute(context)
    assert result["total_listings_fetched"] == 0


@pytest.mark.asyncio
async def test_opportunity_agent_emits_progress_events(context, listings):
    mock_job_board = AsyncMock()
    mock_job_board.search_jobs = AsyncMock(return_value=listings)
    mock_publisher = MagicMock()
    mock_publisher.emit = MagicMock()

    agent = OpportunityAgent(
        event_publisher=mock_publisher,
        llm=None,
        job_board_client=mock_job_board,
        job_scorer=JobScorer(llm=None),
        cv_tailor=CVTailor(llm=None),
    )
    await agent._execute(context)
    assert mock_publisher.emit.call_count >= 3  # job_fetch, scoring, enrichment


@pytest.mark.asyncio
async def test_opportunity_agent_high_match_triggers_cv_tailoring(context, listings):
    mock_job_board = AsyncMock()
    mock_job_board.search_jobs = AsyncMock(return_value=listings)
    mock_tailor = AsyncMock()
    mock_tailor.tailor = AsyncMock(return_value=[])

    agent = OpportunityAgent(
        llm=None,
        job_board_client=mock_job_board,
        job_scorer=JobScorer(llm=None),
        cv_tailor=mock_tailor,
    )
    result = await agent._execute(context)
    # job-1 is a high match — tailor.tailor must have been called
    if result["high_match_jobs"]:
        mock_tailor.tailor.assert_called_once()


def test_agent_type_and_display_name():
    agent = OpportunityAgent(llm=None, job_board_client=AsyncMock())
    assert agent.agent_type == AgentType.OPPORTUNITY
    assert agent.display_name == "Opportunity Matcher"
