"""Tests for the Networking & Outreach Agent.

Covers:
  - LinkedInReviewer: LLM review, heuristic fallback, _build_score helper
  - EventFinder: MCP fetch, concurrent topic fan-out, deduplication, relevance ranking
  - OutreachDrafter: LLM drafting, template fallback, _build_draft helper
  - RelationshipTracker: pipeline building, contact seeding, next-action generation
  - NetworkingAgent: full 4-step pipeline, concurrent step 1+2, output shape, BaseAgent.run()

All LLM and MCP calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.results import AgentResultStatus
from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.networking.event_finder import EventFinder, _build_topics, _compute_relevance, _deduplicate_and_rank
from agents.networking.linkedin_reviewer import LinkedInReviewer, _build_score, _heuristic_review
from agents.networking.mcp_client import StubMCPClient
from agents.networking.models import (
    CommunityEvent,
    ConnectionStatus,
    EventType,
    LinkedInProfileScore,
    OutreachDraft,
    OutreachTone,
    RecipientType,
    RelationshipContact,
    RelationshipPipeline,
)
from agents.networking.networking_agent import (
    NetworkingAgent,
    _build_background_summary,
    _collect_data_sources,
    _resolve_top_gap,
    _serialise_draft,
    _serialise_event,
    _serialise_linkedin_review,
    _serialise_pipeline,
)
from agents.networking.outreach_drafter import OutreachDrafter, _build_draft, _template_drafts
from agents.networking.relationship_tracker import (
    RelationshipTracker,
    _count_by_status,
    _extract_priority_skills,
    _generate_next_actions,
    _infer_contact_role,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def stub_mcp() -> StubMCPClient:
    return StubMCPClient()


@pytest.fixture
def sample_linkedin_score() -> LinkedInProfileScore:
    return LinkedInProfileScore(
        headline_score=0.72,
        summary_score=0.65,
        experience_score=0.70,
        skills_score=0.60,
        overall_score=0.68,
        ats_score=0.55,
        strengths=["Good technical headline", "Strong experience section"],
        improvements=["Add target role to headline", "Quantify achievements"],
        recommended_keywords=["MLOps", "LLM", "RAG", "LangChain"],
    )


@pytest.fixture
def sample_outreach_drafts() -> list[OutreachDraft]:
    from uuid import uuid4
    return [
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.MENTOR,
            subject="Building MLOps skills — 20 min of your insight?",
            body="Hi [NAME], your work on [THEIR_PROJECT] caught my attention...",
            tone=OutreachTone.FRIENDLY,
            platform="LinkedIn",
            target_skill="MLOps",
            call_to_action="20-minute call to share your learning path",
            estimated_response_rate="medium",
        ),
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.PEER,
            subject="Both targeting ML Engineer — want to exchange notes?",
            body="Hi [NAME], I noticed we're both working toward ML Engineer roles...",
            tone=OutreachTone.FRIENDLY,
            platform="LinkedIn",
            target_skill="MLOps",
            call_to_action="Connect and share one useful resource",
            estimated_response_rate="high",
        ),
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.COMMUNITY_LEADER,
            subject="Intro: Backend engineer transitioning to ML Engineer",
            body="Hi everyone! I'm [YOUR_NAME]...",
            tone=OutreachTone.FRIENDLY,
            platform="Discord/Slack",
            target_skill="MLOps",
            call_to_action="Introduce yourself and ask one question",
            estimated_response_rate="high",
        ),
    ]


@pytest.fixture
def sample_prioritised_gaps() -> list[dict]:
    return [
        {
            "requirement_name": "MLOps",
            "dimension": "tech_skill",
            "severity": "critical",
            "diff_score": 0.9,
            "priority_rank": 1,
            "is_required": True,
        },
        {
            "requirement_name": "PyTorch",
            "dimension": "tech_skill",
            "severity": "high",
            "diff_score": 0.7,
            "priority_rank": 2,
            "is_required": True,
        },
        {
            "requirement_name": "System Design",
            "dimension": "tech_skill",
            "severity": "medium",
            "diff_score": 0.5,
            "priority_rank": 3,
            "is_required": True,
        },
    ]


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _make_context(
    target_role: str = "ML Engineer",
    current_role: str | None = "Backend Engineer",
    skills: list[str] | None = None,
    location: str | None = "Zurich, Switzerland",
    gap_analysis: dict | None = None,
    cv_analysis: dict | None = None,
) -> AgentContext:
    profile = UserProfileSnapshot(
        target_role=target_role,
        current_role=current_role,
        skills=skills or ["Python", "FastAPI", "Docker", "PostgreSQL"],
        location=location,
        timeline_months=12,
        weekly_hours_available=15,
    )
    plan: dict = {}
    if gap_analysis is not None:
        plan["gap_analysis"] = gap_analysis
    if cv_analysis is not None:
        plan["cv_analysis"] = cv_analysis
    return AgentContext(
        task_id="task-net-001",
        session_id="sess-net-001",
        user_id="user-net-001",
        correlation_id="corr-net-001",
        stream_channel="channel-net-test",
        user_profile=profile,
        plan_snapshot=plan,
    )


# ── LinkedInReviewer ──────────────────────────────────────────────────────────


class TestBuildScore:
    def test_all_fields_populated(self):
        raw = {
            "headline_score": 0.8,
            "summary_score": 0.7,
            "experience_score": 0.75,
            "skills_score": 0.6,
            "overall_score": 0.72,
            "ats_score": 0.65,
            "strengths": ["Good headline", "Strong experience"],
            "improvements": ["Add keywords", "Quantify achievements"],
            "recommended_keywords": ["MLOps", "LLM"],
        }
        score = _build_score(raw)
        assert score.headline_score == pytest.approx(0.8, abs=0.001)
        assert score.summary_score == pytest.approx(0.7, abs=0.001)
        assert score.ats_score == pytest.approx(0.65, abs=0.001)
        assert score.strengths == ["Good headline", "Strong experience"]
        assert "MLOps" in score.recommended_keywords

    def test_scores_clamped_to_unit_interval(self):
        raw = {
            "headline_score": 2.5,
            "summary_score": -0.3,
            "experience_score": 0.7,
            "skills_score": 0.6,
            "overall_score": 1.5,
            "ats_score": -1.0,
            "strengths": [],
            "improvements": [],
            "recommended_keywords": [],
        }
        score = _build_score(raw)
        assert score.headline_score == 1.0
        assert score.summary_score == 0.0
        assert score.overall_score == 1.0
        assert score.ats_score == 0.0

    def test_missing_fields_use_defaults(self):
        score = _build_score({})
        assert 0.0 <= score.headline_score <= 1.0
        assert 0.0 <= score.overall_score <= 1.0
        assert score.strengths == []
        assert score.improvements == []

    def test_overall_score_computed_from_components_when_missing(self):
        raw = {
            "headline_score": 0.8,
            "summary_score": 0.7,
            "experience_score": 0.9,
            "skills_score": 0.6,
            "ats_score": 0.7,
            "strengths": [],
            "improvements": [],
            "recommended_keywords": [],
        }
        score = _build_score(raw)
        # overall = 0.8*0.20 + 0.7*0.25 + 0.9*0.30 + 0.6*0.15 + 0.7*0.10 = 0.775
        assert score.overall_score == pytest.approx(0.775, abs=0.01)

    def test_empty_lists_handled(self):
        raw = {
            "headline_score": 0.5,
            "summary_score": 0.5,
            "experience_score": 0.5,
            "skills_score": 0.5,
            "overall_score": 0.5,
            "ats_score": 0.5,
            "strengths": [],
            "improvements": [],
            "recommended_keywords": [],
        }
        score = _build_score(raw)
        assert score.strengths == []
        assert score.improvements == []


class TestHeuristicReview:
    def test_returns_score_with_target_role_keyword(self):
        profile_data = {"profile_completeness": 0.7}
        score = _heuristic_review(profile_data, "ML Engineer")
        assert "ML Engineer" in score.recommended_keywords[0]

    def test_completeness_affects_scores(self):
        low_data = {"profile_completeness": 0.3}
        high_data = {"profile_completeness": 0.9}
        low_score = _heuristic_review(low_data, "ML Engineer")
        high_score = _heuristic_review(high_data, "ML Engineer")
        assert high_score.overall_score > low_score.overall_score

    def test_has_improvements(self):
        score = _heuristic_review({}, "Data Engineer")
        assert len(score.improvements) >= 3

    def test_scores_bounded(self):
        score = _heuristic_review({"profile_completeness": 0.5}, "ML Engineer")
        for val in (score.headline_score, score.summary_score, score.experience_score,
                    score.skills_score, score.overall_score, score.ats_score):
            assert 0.0 <= val <= 1.0


class TestLinkedInReviewerAsync:
    async def test_successful_llm_review(self, mock_llm: AsyncMock):
        payload = {
            "headline_score": 0.75,
            "summary_score": 0.70,
            "experience_score": 0.80,
            "skills_score": 0.65,
            "overall_score": 0.73,
            "ats_score": 0.60,
            "strengths": ["Good technical headline"],
            "improvements": ["Add target role to headline"],
            "recommended_keywords": ["MLOps", "PyTorch"],
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        reviewer = LinkedInReviewer(llm=mock_llm)
        result = await reviewer.review({"headline": "Engineer"}, "ML Engineer")
        assert result.overall_score == pytest.approx(0.73, abs=0.001)
        assert "MLOps" in result.recommended_keywords

    async def test_llm_failure_returns_heuristic_fallback(self, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        reviewer = LinkedInReviewer(llm=mock_llm)
        result = await reviewer.review({"profile_completeness": 0.6}, "Data Engineer")
        assert isinstance(result, LinkedInProfileScore)
        assert len(result.improvements) >= 1

    async def test_non_dict_json_raises_and_falls_back(self, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps([1, 2, 3])))
        reviewer = LinkedInReviewer(llm=mock_llm)
        result = await reviewer.review({}, "ML Engineer")
        assert isinstance(result, LinkedInProfileScore)


# ── EventFinder ───────────────────────────────────────────────────────────────


class TestBuildTopics:
    def test_target_role_always_first(self):
        topics = _build_topics("ML Engineer", ["Python", "PyTorch"])
        assert topics[0] == "ml engineer"

    def test_skills_appended_up_to_three(self):
        topics = _build_topics("ML Engineer", ["Python", "PyTorch", "Docker", "Kafka"])
        assert len(topics) <= 4

    def test_duplicates_excluded(self):
        topics = _build_topics("ML Engineer", ["ml engineer", "Python"])
        assert len([t for t in topics if t == "ml engineer"]) == 1

    def test_empty_skills_returns_role_only(self):
        topics = _build_topics("Data Engineer", [])
        assert topics == ["data engineer"]


class TestComputeRelevance:
    def test_exact_role_match_gives_high_score(self):
        score = _compute_relevance(["machine learning", "python"], "machine learning", set())
        assert score > 0.3

    def test_skill_match_gives_score(self):
        score = _compute_relevance(["python", "fastapi"], "ml engineer", {"python"})
        assert score > 0.0

    def test_no_match_gives_zero(self):
        score = _compute_relevance(["java", "spring"], "ml engineer", {"python"})
        assert score == 0.0

    def test_score_bounded_to_one(self):
        tags = ["machine learning"] * 10
        score = _compute_relevance(tags, "machine learning", {"machine learning"})
        assert score <= 1.0


class TestDeduplicateAndRank:
    def _sample_raw(self, event_id: str, tags: list[str]) -> dict:
        return {
            "id": event_id,
            "title": f"Event {event_id}",
            "type": "meetup",
            "platform": "Meetup.com",
            "skill_tags": tags,
            "description": "Test event",
            "is_online": True,
        }

    def test_duplicates_removed(self):
        raw = [
            self._sample_raw("evt-001", ["python"]),
            self._sample_raw("evt-001", ["python"]),  # duplicate
            self._sample_raw("evt-002", ["docker"]),
        ]
        events = _deduplicate_and_rank(raw, "ml engineer", ["python"])
        ids = [e.event_id for e in events]
        assert len(ids) == len(set(ids)) == 2

    def test_sorted_by_relevance_desc(self):
        raw = [
            self._sample_raw("evt-low", ["java"]),
            self._sample_raw("evt-high", ["python", "machine learning"]),
        ]
        events = _deduplicate_and_rank(raw, "machine learning", ["python"])
        assert events[0].event_id == "evt-high"

    def test_missing_id_skipped(self):
        raw = [{"title": "No ID event", "type": "meetup", "skill_tags": []}]
        events = _deduplicate_and_rank(raw, "ml engineer", [])
        assert events == []

    def test_invalid_event_type_defaults_to_meetup(self):
        raw = [self._sample_raw("evt-003", ["python"])]
        raw[0]["type"] = "invalid_type"
        events = _deduplicate_and_rank(raw, "ml engineer", ["python"])
        assert events[0].event_type == EventType.MEETUP


class TestEventFinderAsync:
    async def test_find_returns_events(self, stub_mcp: StubMCPClient):
        finder = EventFinder(stub_mcp, max_events=10)
        events = await finder.find(
            "machine learning", ["python"], "Zurich, Switzerland"
        )
        assert isinstance(events, list)
        assert all(isinstance(e, CommunityEvent) for e in events)

    async def test_max_events_respected(self, stub_mcp: StubMCPClient):
        finder = EventFinder(stub_mcp, max_events=2)
        events = await finder.find("machine learning", ["python", "docker"], None)
        assert len(events) <= 2

    async def test_find_returns_empty_list_when_mcp_fails(self):
        failing_mcp = AsyncMock()
        failing_mcp.call = AsyncMock(side_effect=RuntimeError("MCP unavailable"))
        finder = EventFinder(failing_mcp, max_events=10)
        events = await finder.find("python", [], None)
        assert events == []

    async def test_concurrent_topics_deduplicated(self, stub_mcp: StubMCPClient):
        finder = EventFinder(stub_mcp, max_events=20)
        events = await finder.find("machine learning", ["python"], None)
        event_ids = [e.event_id for e in events]
        assert len(event_ids) == len(set(event_ids))

    async def test_location_passed_to_mcp(self):
        mock_mcp = AsyncMock()
        mock_mcp.call = AsyncMock(return_value={
            "events": [
                {
                    "id": "evt-test-001",
                    "title": "Test Event",
                    "type": "meetup",
                    "platform": "Meetup.com",
                    "skill_tags": ["python"],
                    "description": "Test",
                    "is_online": False,
                }
            ],
            "total_count": 1,
        })
        finder = EventFinder(mock_mcp, max_events=10)
        await finder.find("python", [], "Geneva, Switzerland")
        call_kwargs = mock_mcp.call.call_args[0][2]  # params arg
        assert call_kwargs.get("location") == "Geneva, Switzerland"


# ── OutreachDrafter ───────────────────────────────────────────────────────────


class TestBuildDraft:
    def test_valid_recipient_type(self):
        raw = {
            "recipient_type": "mentor",
            "subject": "Learning MLOps",
            "body": "Hi [NAME]...",
            "tone": "friendly",
            "platform": "LinkedIn",
            "target_skill": "MLOps",
            "call_to_action": "20-minute call",
            "estimated_response_rate": "medium",
        }
        draft = _build_draft(raw, "MLOps")
        assert draft.recipient_type == RecipientType.MENTOR
        assert draft.tone == OutreachTone.FRIENDLY
        assert draft.target_skill == "MLOps"

    def test_invalid_recipient_type_defaults_to_mentor(self):
        raw = {"recipient_type": "unknown_type", "subject": "Hi", "body": "Body",
               "tone": "professional", "platform": "LinkedIn", "target_skill": "Python",
               "call_to_action": "call", "estimated_response_rate": "low"}
        draft = _build_draft(raw, "Python")
        assert draft.recipient_type == RecipientType.MENTOR

    def test_invalid_tone_defaults_to_professional(self):
        raw = {"recipient_type": "peer", "subject": "Hi", "body": "Body",
               "tone": "invalid_tone", "platform": "LinkedIn", "target_skill": "Python",
               "call_to_action": "call", "estimated_response_rate": "medium"}
        draft = _build_draft(raw, "Python")
        assert draft.tone == OutreachTone.PROFESSIONAL

    def test_fallback_skill_used_when_target_skill_missing(self):
        raw = {"recipient_type": "peer", "subject": "Hi", "body": "Body",
               "tone": "friendly", "platform": "LinkedIn",
               "call_to_action": "call", "estimated_response_rate": "medium"}
        draft = _build_draft(raw, "FallbackSkill")
        assert draft.target_skill == "FallbackSkill"

    def test_draft_id_is_uuid(self):
        raw = {"recipient_type": "mentor", "subject": "Hi", "body": "Body",
               "tone": "professional", "platform": "LinkedIn", "target_skill": "Python",
               "call_to_action": "call", "estimated_response_rate": "medium"}
        import uuid
        draft = _build_draft(raw, "Python")
        assert uuid.UUID(draft.draft_id)


class TestTemplateDrafts:
    def test_returns_three_drafts(self):
        drafts = _template_drafts("ML Engineer", "MLOps")
        assert len(drafts) == 3

    def test_covers_all_required_recipient_types(self):
        drafts = _template_drafts("ML Engineer", "MLOps")
        types = {d.recipient_type for d in drafts}
        assert RecipientType.MENTOR in types
        assert RecipientType.PEER in types
        assert RecipientType.COMMUNITY_LEADER in types

    def test_target_skill_in_subject(self):
        drafts = _template_drafts("ML Engineer", "MLOps")
        assert any("MLOps" in d.subject for d in drafts)

    def test_each_draft_has_unique_id(self):
        drafts = _template_drafts("ML Engineer", "MLOps")
        ids = [d.draft_id for d in drafts]
        assert len(ids) == len(set(ids))

    def test_body_not_empty(self):
        drafts = _template_drafts("Data Engineer", "Spark")
        for draft in drafts:
            assert len(draft.body) > 20


class TestOutreachDrafterAsync:
    async def test_successful_llm_drafts(self, mock_llm: AsyncMock):
        payload = [
            {
                "recipient_type": "mentor",
                "subject": "Learning MLOps",
                "body": "Hi [NAME], your work on [THEIR_PROJECT] is great...",
                "tone": "friendly",
                "platform": "LinkedIn",
                "target_skill": "MLOps",
                "call_to_action": "20-minute call",
                "estimated_response_rate": "medium",
            },
            {
                "recipient_type": "peer",
                "subject": "Both targeting ML Engineer",
                "body": "Hi [NAME], we're both transitioning...",
                "tone": "friendly",
                "platform": "LinkedIn",
                "target_skill": "MLOps",
                "call_to_action": "Exchange resources",
                "estimated_response_rate": "high",
            },
        ]
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        drafter = OutreachDrafter(llm=mock_llm, max_drafts=3)
        drafts = await drafter.draft(
            target_role="ML Engineer",
            current_role="Backend Engineer",
            top_skill_gap="MLOps",
            background_summary="Python engineer building ML skills",
        )
        assert len(drafts) == 2
        assert drafts[0].recipient_type == RecipientType.MENTOR

    async def test_llm_failure_returns_template_fallback(self, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        drafter = OutreachDrafter(llm=mock_llm, max_drafts=3)
        drafts = await drafter.draft(
            target_role="ML Engineer",
            current_role=None,
            top_skill_gap="PyTorch",
            background_summary="Python developer",
        )
        assert len(drafts) == 3
        assert all(isinstance(d, OutreachDraft) for d in drafts)

    async def test_max_drafts_respected(self, mock_llm: AsyncMock):
        payload = [
            {
                "recipient_type": "mentor", "subject": "S1", "body": "B1",
                "tone": "professional", "platform": "LinkedIn", "target_skill": "MLOps",
                "call_to_action": "call", "estimated_response_rate": "medium",
            },
            {
                "recipient_type": "peer", "subject": "S2", "body": "B2",
                "tone": "friendly", "platform": "LinkedIn", "target_skill": "MLOps",
                "call_to_action": "connect", "estimated_response_rate": "high",
            },
            {
                "recipient_type": "community_leader", "subject": "S3", "body": "B3",
                "tone": "friendly", "platform": "Discord/Slack", "target_skill": "MLOps",
                "call_to_action": "intro", "estimated_response_rate": "high",
            },
            {
                "recipient_type": "mentor", "subject": "S4", "body": "B4",
                "tone": "concise", "platform": "Email", "target_skill": "MLOps",
                "call_to_action": "email", "estimated_response_rate": "low",
            },
        ]
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        drafter = OutreachDrafter(llm=mock_llm, max_drafts=2)
        drafts = await drafter.draft("ML Engineer", None, "MLOps", "background")
        assert len(drafts) == 2

    async def test_non_list_json_falls_back_to_templates(self, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps({"error": "bad"})))
        drafter = OutreachDrafter(llm=mock_llm, max_drafts=3)
        drafts = await drafter.draft("ML Engineer", None, "MLOps", "background")
        assert len(drafts) > 0


# ── RelationshipTracker ────────────────────────────────────────────────────────


class TestInferContactRole:
    def test_mentor_includes_skill(self):
        role = _infer_contact_role(RecipientType.MENTOR, "MLOps", "ML Engineer")
        assert "MLOps" in role
        assert "ML Engineer" in role

    def test_peer_type_described(self):
        role = _infer_contact_role(RecipientType.PEER, "PyTorch", "ML Engineer")
        assert "ML Engineer" in role

    def test_community_leader_described(self):
        role = _infer_contact_role(RecipientType.COMMUNITY_LEADER, "Docker", "DevOps")
        assert "Docker" in role


class TestCountByStatus:
    def test_correct_counts(self):
        from uuid import uuid4
        contacts = [
            RelationshipContact(
                contact_id=str(uuid4()),
                role="Senior ML Engineer",
                recipient_type=RecipientType.MENTOR,
                connection_status=ConnectionStatus.IDENTIFIED,
                target_skill="MLOps",
                source="linkedin",
            ),
            RelationshipContact(
                contact_id=str(uuid4()),
                role="ML Engineer Peer",
                recipient_type=RecipientType.PEER,
                connection_status=ConnectionStatus.IDENTIFIED,
                target_skill="PyTorch",
                source="linkedin",
            ),
            RelationshipContact(
                contact_id=str(uuid4()),
                role="Community Leader",
                recipient_type=RecipientType.COMMUNITY_LEADER,
                connection_status=ConnectionStatus.REACHED_OUT,
                target_skill="Python",
                source="community",
            ),
        ]
        counts = _count_by_status(contacts)
        assert counts[ConnectionStatus.IDENTIFIED.value] == 2
        assert counts[ConnectionStatus.REACHED_OUT.value] == 1

    def test_empty_contacts_returns_empty(self):
        assert _count_by_status([]) == {}


class TestExtractPrioritySkills:
    def test_skills_extracted_in_order(self, sample_prioritised_gaps: list[dict]):
        skills = _extract_priority_skills(sample_prioritised_gaps)
        assert skills[0] == "MLOps"
        assert skills[1] == "PyTorch"

    def test_empty_gaps_returns_empty(self):
        assert _extract_priority_skills([]) == []

    def test_gaps_without_name_skipped(self):
        gaps = [{"severity": "high"}, {"requirement_name": "Python"}]
        skills = _extract_priority_skills(gaps)
        assert skills == ["Python"]


class TestGenerateNextActions:
    def test_returns_non_empty_list(self, sample_prioritised_gaps: list[dict]):
        from uuid import uuid4
        contacts = [
            RelationshipContact(
                contact_id=str(uuid4()),
                role="Senior ML Engineer",
                recipient_type=RecipientType.MENTOR,
                connection_status=ConnectionStatus.IDENTIFIED,
                target_skill="MLOps",
                source="linkedin",
            )
        ]
        actions = _generate_next_actions(contacts, sample_prioritised_gaps, "ML Engineer")
        assert len(actions) >= 2

    def test_mentions_identified_contacts_count(self, sample_prioritised_gaps: list[dict]):
        from uuid import uuid4
        contacts = [
            RelationshipContact(
                contact_id=str(uuid4()),
                role="A",
                recipient_type=RecipientType.MENTOR,
                connection_status=ConnectionStatus.IDENTIFIED,
                target_skill="X",
                source="linkedin",
            )
            for _ in range(3)
        ]
        actions = _generate_next_actions(contacts, sample_prioritised_gaps, "ML Engineer")
        assert any("3" in action for action in actions)


class TestRelationshipTracker:
    def test_pipeline_has_contacts_from_drafts(
        self, sample_outreach_drafts: list[OutreachDraft], sample_prioritised_gaps: list[dict]
    ):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=sample_prioritised_gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        assert pipeline.total_contacts >= len(sample_outreach_drafts)

    def test_all_contacts_start_as_identified(
        self, sample_outreach_drafts: list[OutreachDraft], sample_prioritised_gaps: list[dict]
    ):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=sample_prioritised_gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        for contact in pipeline.contacts:
            assert contact.connection_status == ConnectionStatus.IDENTIFIED

    def test_by_status_sums_to_total(
        self, sample_outreach_drafts: list[OutreachDraft], sample_prioritised_gaps: list[dict]
    ):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=sample_prioritised_gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        assert sum(pipeline.by_status.values()) == pipeline.total_contacts

    def test_priority_skills_from_gaps(
        self, sample_outreach_drafts: list[OutreachDraft], sample_prioritised_gaps: list[dict]
    ):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=sample_prioritised_gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        assert "MLOps" in pipeline.outreach_priority_skills

    def test_empty_gaps_and_drafts_returns_empty_pipeline(self):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=[],
            outreach_drafts=[],
            target_role="ML Engineer",
        )
        assert pipeline.total_contacts == 0
        assert pipeline.contacts == []

    def test_additional_contacts_for_uncovered_gaps(
        self, sample_outreach_drafts: list[OutreachDraft]
    ):
        gaps = [
            {"requirement_name": "UniqueTechSkill", "severity": "critical"},
        ]
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        uncovered_contacts = [
            c for c in pipeline.contacts
            if c.target_skill == "UniqueTechSkill"
        ]
        assert len(uncovered_contacts) >= 1


# ── NetworkingAgent ───────────────────────────────────────────────────────────


class TestResolveTopGap:
    def test_uses_first_gap_name(self, sample_prioritised_gaps: list[dict]):
        context = _make_context(gap_analysis={"prioritised_gaps": sample_prioritised_gaps})
        result = _resolve_top_gap(sample_prioritised_gaps[:3], context)
        assert result == "MLOps"

    def test_falls_back_to_profile_skills_when_no_gaps(self):
        context = _make_context(skills=["Python", "Docker"])
        result = _resolve_top_gap([], context)
        assert result == "Python"

    def test_falls_back_to_target_role_when_no_skills(self):
        context = _make_context(target_role="Data Engineer", skills=[])
        result = _resolve_top_gap([], context)
        assert result == "Data Engineer"


class TestBuildBackgroundSummary:
    def test_includes_current_role(self):
        profile = UserProfileSnapshot(
            current_role="Backend Engineer",
            skills=["Python"],
        )
        summary = _build_background_summary({}, profile)
        assert "Backend Engineer" in summary

    def test_includes_skills(self):
        profile = UserProfileSnapshot(skills=["Python", "FastAPI", "Docker"])
        summary = _build_background_summary({}, profile)
        assert "Python" in summary

    def test_includes_latest_experience(self):
        cv = {"experience": [{"title": "Senior Dev", "company": "TechCorp"}]}
        profile = UserProfileSnapshot(skills=["Python"])
        summary = _build_background_summary(cv, profile)
        assert "TechCorp" in summary

    def test_defaults_when_empty(self):
        profile = UserProfileSnapshot(skills=[])
        summary = _build_background_summary({}, profile)
        assert len(summary) > 0


class TestCollectDataSources:
    def test_includes_linkedin_source_when_review_present(
        self, sample_linkedin_score: LinkedInProfileScore
    ):
        sources = _collect_data_sources([], sample_linkedin_score)
        assert "mcp_linkedin_profile" in sources

    def test_excludes_linkedin_source_when_review_none(self):
        sources = _collect_data_sources([], None)
        assert "mcp_linkedin_profile" not in sources

    def test_includes_llm_sources(self):
        sources = _collect_data_sources([], None)
        assert "llm_outreach_drafter" in sources

    def test_event_sources_collected(self):
        events = [
            CommunityEvent(
                event_id="e1",
                title="Test",
                event_type=EventType.MEETUP,
                platform="Meetup.com",
                skill_tags=[],
                relevance_score=0.5,
                description="",
                source="mcp_industry_news",
            )
        ]
        sources = _collect_data_sources(events, None)
        assert "mcp_industry_news" in sources

    def test_sources_are_sorted(self):
        sources = _collect_data_sources([], None)
        assert sources == sorted(sources)


class TestSerialisers:
    def test_linkedin_review_all_keys(self, sample_linkedin_score: LinkedInProfileScore):
        out = _serialise_linkedin_review(sample_linkedin_score)
        for key in ("headline_score", "summary_score", "experience_score", "skills_score",
                    "overall_score", "ats_score", "strengths", "improvements",
                    "recommended_keywords"):
            assert key in out

    def test_event_all_keys(self):
        event = CommunityEvent(
            event_id="e1",
            title="Test Event",
            event_type=EventType.CONFERENCE,
            platform="Eventbrite",
            skill_tags=["python"],
            relevance_score=0.8,
            description="A great conference",
        )
        out = _serialise_event(event)
        for key in ("event_id", "title", "event_type", "platform", "skill_tags",
                    "relevance_score", "description", "url", "date", "location",
                    "is_online", "source"):
            assert key in out
        assert out["event_type"] == "conference"

    def test_draft_all_keys(self, sample_outreach_drafts: list[OutreachDraft]):
        out = _serialise_draft(sample_outreach_drafts[0])
        for key in ("draft_id", "recipient_type", "subject", "body", "tone",
                    "platform", "target_skill", "call_to_action", "estimated_response_rate"):
            assert key in out
        assert out["recipient_type"] == "mentor"

    def test_pipeline_all_keys(
        self, sample_outreach_drafts: list[OutreachDraft], sample_prioritised_gaps: list[dict]
    ):
        tracker = RelationshipTracker()
        pipeline = tracker.build_pipeline(
            prioritised_gaps=sample_prioritised_gaps,
            outreach_drafts=sample_outreach_drafts,
            target_role="ML Engineer",
        )
        out = _serialise_pipeline(pipeline)
        for key in ("total_contacts", "by_status", "contacts", "next_actions",
                    "outreach_priority_skills"):
            assert key in out
        assert out["total_contacts"] == pipeline.total_contacts


class TestNetworkingAgent:
    def _make_agent(
        self,
        emit_events: bool = False,
        linkedin_score: LinkedInProfileScore | None = None,
        events: list[CommunityEvent] | None = None,
        drafts: list[OutreachDraft] | None = None,
    ) -> NetworkingAgent:
        mock_reviewer = AsyncMock(spec=LinkedInReviewer)
        mock_event_finder = AsyncMock(spec=EventFinder)
        mock_drafter = AsyncMock(spec=OutreachDrafter)
        mock_tracker = MagicMock(spec=RelationshipTracker)

        from uuid import uuid4

        _score = linkedin_score or LinkedInProfileScore(
            headline_score=0.7, summary_score=0.6, experience_score=0.75,
            skills_score=0.65, overall_score=0.68, ats_score=0.6,
            strengths=["Good profile"], improvements=["Add keywords"],
            recommended_keywords=["MLOps"],
        )
        _events = events or [
            CommunityEvent(
                event_id="evt-test-001",
                title="ML Meetup",
                event_type=EventType.MEETUP,
                platform="Meetup.com",
                skill_tags=["machine learning"],
                relevance_score=0.8,
                description="Monthly ML meetup",
            )
        ]
        _drafts = drafts or [
            OutreachDraft(
                draft_id=str(uuid4()),
                recipient_type=RecipientType.MENTOR,
                subject="Learning MLOps",
                body="Hi [NAME]...",
                tone=OutreachTone.FRIENDLY,
                platform="LinkedIn",
                target_skill="MLOps",
                call_to_action="20-min call",
                estimated_response_rate="medium",
            )
        ]
        _pipeline = RelationshipPipeline(
            total_contacts=4,
            by_status={ConnectionStatus.IDENTIFIED.value: 4},
            contacts=[],
            next_actions=["Send outreach to 4 contacts"],
            outreach_priority_skills=["MLOps"],
        )

        mock_reviewer.review = AsyncMock(return_value=_score)
        mock_event_finder.find = AsyncMock(return_value=_events)
        mock_drafter.draft = AsyncMock(return_value=_drafts)
        mock_tracker.build_pipeline = MagicMock(return_value=_pipeline)

        publisher = MagicMock() if emit_events else None

        return NetworkingAgent(
            linkedin_reviewer=mock_reviewer,
            event_finder=mock_event_finder,
            outreach_drafter=mock_drafter,
            relationship_tracker=mock_tracker,
            event_publisher=publisher,
        )

    def test_agent_type(self):
        agent = self._make_agent()
        assert agent.agent_type == AgentType.NETWORKING

    def test_display_name(self):
        agent = self._make_agent()
        assert agent.display_name == "Networking & Outreach Agent"

    async def test_execute_returns_required_keys(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        for key in (
            "target_role", "linkedin_review", "events_and_communities",
            "outreach_drafts", "relationship_pipeline", "data_sources",
            "generated_at", "processing_steps",
        ):
            assert key in result

    async def test_execute_has_four_processing_steps(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        assert len(result["processing_steps"]) == 4

    async def test_target_role_in_output(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context(target_role="Data Engineer"))
        assert result["target_role"] == "Data Engineer"

    async def test_linkedin_review_present(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        assert result["linkedin_review"] is not None
        assert "overall_score" in result["linkedin_review"]

    async def test_events_and_communities_list(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        assert isinstance(result["events_and_communities"], list)
        assert len(result["events_and_communities"]) > 0

    async def test_outreach_drafts_present(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        assert isinstance(result["outreach_drafts"], list)
        assert len(result["outreach_drafts"]) > 0

    async def test_relationship_pipeline_present(self):
        agent = self._make_agent()
        result = await agent._execute(_make_context())
        pipeline = result["relationship_pipeline"]
        assert pipeline is not None
        assert "total_contacts" in pipeline
        assert "next_actions" in pipeline

    async def test_four_progress_events_emitted(self):
        agent = self._make_agent(emit_events=True)
        await agent._execute(_make_context())
        publisher = agent._event_publisher
        assert publisher.emit.call_count == 4

    async def test_no_error_without_publisher(self):
        agent = self._make_agent(emit_events=False)
        result = await agent._execute(_make_context())
        assert "target_role" in result

    async def test_linkedin_review_none_when_reviewer_fails(self):
        agent = self._make_agent()
        agent._linkedin_reviewer.review = AsyncMock(side_effect=RuntimeError("profile unavailable"))
        result = await agent._execute(_make_context())
        assert result["linkedin_review"] is None

    async def test_gap_analysis_from_plan_snapshot(
        self, sample_prioritised_gaps: list[dict]
    ):
        agent = self._make_agent()
        context = _make_context(gap_analysis={"prioritised_gaps": sample_prioritised_gaps})
        await agent._execute(context)
        # Verify drafter was called with the top gap name
        drafter: AsyncMock = agent._outreach_drafter
        call_kwargs = drafter.draft.call_args[1]
        assert call_kwargs["top_skill_gap"] == "MLOps"

    async def test_full_pipeline_via_base_agent_run(self):
        agent = self._make_agent()
        result = await agent.run(_make_context())
        assert result.agent_type == AgentType.NETWORKING.value
        assert result.status == AgentResultStatus.COMPLETED
        assert "events_and_communities" in result.output
        assert result.duration_ms >= 0

    async def test_base_agent_run_returns_failed_on_exception(self):
        agent = self._make_agent()
        agent._event_finder.find = AsyncMock(side_effect=RuntimeError("unexpected crash"))
        result = await agent.run(_make_context())
        assert result.status == AgentResultStatus.FAILED
        assert result.error_message is not None
