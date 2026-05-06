"""Tests for the CV Analysis Agent.

Covers:
  - PDFParser: text passthrough, PDF extraction, UTF-8 fallback
  - CVParser: successful parse, fallback on LLM failure, empty text handling
  - SkillExtractor: deduplication, multi-source collection, keyword scanning
  - SkillNormaliser: alias dict resolution, LLM path, graceful degradation
  - ReadinessScorer: LLM scoring, heuristic fallback, weight calculation
  - CVAgent: full pipeline, progress events, base agent run()

All LLM calls are mocked — no network or Anthropic API required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.tasks import AgentType, UserProfileSnapshot
from agents.core.context import AgentContext
from agents.cv_analysis.cv_agent import CVAgent, _serialise_parsed_cv, _serialise_skill_graph
from agents.cv_analysis.cv_parser import CVParser, _build_parsed_cv, _safe_float, _safe_int
from agents.cv_analysis.models import (
    EducationEntry,
    ExperienceEntry,
    ParsedCV,
    ProjectEntry,
    ReadinessBreakdown,
    ReadinessResult,
    SkillGraph,
    SkillNode,
)
from agents.cv_analysis.pdf_parser import PDFParser
from agents.cv_analysis.readiness_scorer import (
    ReadinessScorer,
    _build_readiness_result,
    _heuristic_score,
)
from agents.cv_analysis.skill_extractor import SkillExtractor, _scan_keywords
from agents.cv_analysis.skill_normaliser import SkillNormaliser


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def cv_parser(mock_llm: AsyncMock) -> CVParser:
    return CVParser(llm=mock_llm)


@pytest.fixture
def skill_normaliser(mock_llm: AsyncMock) -> SkillNormaliser:
    return SkillNormaliser(llm=mock_llm)


@pytest.fixture
def readiness_scorer(mock_llm: AsyncMock) -> ReadinessScorer:
    return ReadinessScorer(llm=mock_llm)


@pytest.fixture
def simple_parsed_cv() -> ParsedCV:
    return ParsedCV(
        raw_text="Sample CV text",
        full_name="Jane Doe",
        email="jane@example.com",
        location="Berlin, Germany",
        raw_skills=["Python", "FastAPI", "Docker"],
        total_experience_months=36,
        experience=[
            ExperienceEntry(
                company="Acme Corp",
                title="Backend Engineer",
                duration_months=24,
                responsibilities=["Built REST APIs using Python and FastAPI"],
                impact_statements=["Reduced API latency by 40%"],
            )
        ],
        education=[
            EducationEntry(
                institution="TU Berlin",
                degree="MSc",
                field_of_study="Computer Science",
                graduation_year=2021,
            )
        ],
        projects=[
            ProjectEntry(
                name="DataPipeline",
                description="ETL pipeline for analytics",
                technologies=["Python", "Kafka", "PostgreSQL"],
            )
        ],
    )


@pytest.fixture
def simple_skill_graph() -> SkillGraph:
    return SkillGraph(nodes=[
        SkillNode(name="Python", canonical_name="Python", category="programming_language"),
        SkillNode(name="FastAPI", canonical_name="FastAPI", category="framework"),
        SkillNode(name="Docker", canonical_name="Docker", category="tool"),
        SkillNode(name="PostgreSQL", canonical_name="PostgreSQL", category="database"),
    ])


def _llm_response(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


def _make_context(
    profile: UserProfileSnapshot | None = None,
    cv_document: str = "Sample CV text",
    source_type: str = "text",
    target_role: str = "Senior Backend Engineer",
) -> AgentContext:
    _profile = profile or UserProfileSnapshot(target_role=target_role)
    return AgentContext(
        task_id="task-cv-001",
        session_id="sess-cv-001",
        user_id="user-cv-001",
        correlation_id="corr-cv-001",
        stream_channel="channel-cv-test",
        user_profile=_profile,
        plan_snapshot={"cv": {"cv_document": cv_document, "source_type": source_type}},
    )


# ── PDFParser ─────────────────────────────────────────────────────────────────


class TestPDFParser:
    def test_string_input_passthrough(self):
        parser = PDFParser()
        text = "This is my resume. Python, FastAPI."
        result = parser.extract_text(text, correlation_id="c1")
        assert result == text

    def test_empty_string_passthrough(self):
        parser = PDFParser()
        assert parser.extract_text("") == ""

    def test_bytes_fallback_on_invalid_pdf(self):
        parser = PDFParser()
        raw = b"Not a real PDF, just some bytes"
        result = parser.extract_text(raw, correlation_id="c1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_utf8_replace_on_binary_garbage(self):
        parser = PDFParser()
        raw = b"\xff\xfe invalid \x00\x01"
        result = parser.extract_text(raw)
        assert isinstance(result, str)

    def test_pdf_extraction_delegates_to_pypdf(self):
        parser = PDFParser()
        with patch.object(parser, "_extract_with_pypdf", return_value="Page 1 content") as mock_extract:
            result = parser.extract_text(b"%PDF-1.4 fake", correlation_id="c2")
        assert result == "Page 1 content"
        mock_extract.assert_called_once()


# ── CVParser helpers ──────────────────────────────────────────────────────────


class TestSafeInt:
    def test_int_value(self):
        assert _safe_int(36) == 36

    def test_float_truncated(self):
        assert _safe_int(12.9) == 12

    def test_string_digits(self):
        assert _safe_int("24") == 24

    def test_none_returns_none(self):
        assert _safe_int(None) is None

    def test_invalid_string_returns_none(self):
        assert _safe_int("not a number") is None


class TestSafeFloat:
    def test_float_value(self):
        assert _safe_float(3.8) == pytest.approx(3.8)

    def test_string_float(self):
        assert _safe_float("3.5") == pytest.approx(3.5)

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_invalid_returns_none(self):
        assert _safe_float("n/a") is None


class TestBuildParsedCV:
    def test_full_response_parsed(self):
        raw = {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+49123456",
            "location": "Berlin",
            "summary": "Experienced engineer",
            "total_experience_months": 36,
            "raw_skills": ["Python", "FastAPI"],
            "certifications": ["AWS SAA 2023"],
            "languages": ["English", "German"],
            "experience": [
                {
                    "company": "Acme Corp",
                    "title": "Backend Engineer",
                    "start_date": "2021-01",
                    "end_date": "present",
                    "duration_months": 36,
                    "responsibilities": ["Built APIs"],
                    "impact_statements": ["Reduced latency by 40%"],
                }
            ],
            "education": [
                {
                    "institution": "TU Berlin",
                    "degree": "MSc",
                    "field_of_study": "Computer Science",
                    "graduation_year": 2021,
                    "gpa": 1.5,
                }
            ],
            "projects": [
                {
                    "name": "DataPipeline",
                    "description": "ETL pipeline",
                    "technologies": ["Python", "Kafka"],
                    "impact": "Processed 1M events/day",
                }
            ],
        }
        cv = _build_parsed_cv(raw, "raw text")
        assert cv.full_name == "Jane Doe"
        assert cv.total_experience_months == 36
        assert len(cv.experience) == 1
        assert cv.experience[0].company == "Acme Corp"
        assert cv.experience[0].duration_months == 36
        assert len(cv.education) == 1
        assert cv.education[0].gpa == pytest.approx(1.5)
        assert len(cv.projects) == 1
        assert cv.raw_skills == ["Python", "FastAPI"]

    def test_experience_without_company_skipped(self):
        raw = {
            "experience": [{"title": "Developer", "responsibilities": ["Coded"]}],
            "education": [], "projects": [], "raw_skills": [],
            "certifications": [], "languages": [],
        }
        cv = _build_parsed_cv(raw, "text")
        assert cv.experience == []

    def test_education_without_institution_skipped(self):
        raw = {
            "experience": [],
            "education": [{"degree": "BSc", "field_of_study": "CS"}],
            "projects": [], "raw_skills": [], "certifications": [], "languages": [],
        }
        cv = _build_parsed_cv(raw, "text")
        assert cv.education == []

    def test_empty_raw_returns_minimal_cv(self):
        cv = _build_parsed_cv({}, "raw")
        assert cv.experience == []
        assert cv.raw_skills == []
        assert cv.full_name is None


# ── CVParser async ────────────────────────────────────────────────────────────


class TestCVParserParse:
    async def test_empty_text_returns_minimal_cv(self, cv_parser: CVParser):
        result = await cv_parser.parse("   ")
        assert result.experience == []
        assert result.raw_skills == []

    async def test_successful_parse(self, cv_parser: CVParser, mock_llm: AsyncMock):
        payload = {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "location": "Berlin",
            "total_experience_months": 36,
            "raw_skills": ["Python", "FastAPI"],
            "experience": [
                {
                    "company": "Acme",
                    "title": "Engineer",
                    "duration_months": 24,
                    "responsibilities": ["Built APIs"],
                    "impact_statements": [],
                }
            ],
            "education": [], "projects": [], "certifications": [], "languages": ["English"],
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await cv_parser.parse("Jane Doe — Backend Engineer...")
        assert result.full_name == "Jane Doe"
        assert result.raw_skills == ["Python", "FastAPI"]
        assert len(result.experience) == 1

    async def test_llm_failure_returns_fallback(self, cv_parser: CVParser, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await cv_parser.parse("Some CV text", correlation_id="c1")
        assert result.raw_text == "Some CV text"
        assert result.experience == []

    async def test_invalid_json_returns_fallback(self, cv_parser: CVParser, mock_llm: AsyncMock):
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response("not json"))
        result = await cv_parser.parse("CV content")
        assert result.experience == []


# ── SkillExtractor ────────────────────────────────────────────────────────────


class TestScanKeywords:
    def test_known_keywords_detected(self):
        keywords = _scan_keywords("We used Python and FastAPI for the backend")
        assert "Python" in keywords
        assert "FastAPI" in keywords

    def test_case_insensitive_match(self):
        keywords = _scan_keywords("experience with docker and kubernetes")
        assert "Docker" in keywords
        assert "Kubernetes" in keywords

    def test_no_keywords_returns_empty(self):
        assert _scan_keywords("managed a team of five engineers") == []


class TestSkillExtractor:
    def test_raw_skills_collected(self, simple_parsed_cv: ParsedCV):
        extractor = SkillExtractor()
        skills = extractor.extract(simple_parsed_cv)
        assert "Python" in skills
        assert "FastAPI" in skills
        assert "Docker" in skills

    def test_project_technologies_collected(self, simple_parsed_cv: ParsedCV):
        extractor = SkillExtractor()
        skills = extractor.extract(simple_parsed_cv)
        assert "Kafka" in skills
        assert "PostgreSQL" in skills

    def test_deduplication_case_insensitive(self):
        cv = ParsedCV(
            raw_text="",
            raw_skills=["python", "Python"],
            projects=[ProjectEntry(name="P", technologies=["Python"])],
        )
        extractor = SkillExtractor()
        skills = extractor.extract(cv)
        python_entries = [s for s in skills if s.lower() == "python"]
        assert len(python_entries) == 1

    def test_experience_keywords_extracted(self):
        cv = ParsedCV(
            raw_text="",
            experience=[
                ExperienceEntry(
                    company="Corp",
                    title="Engineer",
                    responsibilities=["Deployed services using Docker and Kubernetes"],
                )
            ],
        )
        extractor = SkillExtractor()
        skills = extractor.extract(cv)
        assert "Docker" in skills
        assert "Kubernetes" in skills

    def test_empty_cv_returns_empty_list(self):
        cv = ParsedCV(raw_text="")
        extractor = SkillExtractor()
        assert extractor.extract(cv) == []


# ── SkillNormaliser ───────────────────────────────────────────────────────────


class TestSkillNormaliserDictPath:
    async def test_known_aliases_resolved_without_llm(self):
        normaliser = SkillNormaliser(llm=AsyncMock())
        graph = await normaliser.normalise(["js", "k8s", "postgres"])
        names = {n.canonical_name for n in graph.nodes}
        assert "JavaScript" in names
        assert "Kubernetes" in names
        assert "PostgreSQL" in names

    async def test_categories_assigned_correctly(self):
        normaliser = SkillNormaliser(llm=AsyncMock())
        graph = await normaliser.normalise(["python", "docker", "aws"])
        by_name = {n.canonical_name: n.category for n in graph.nodes}
        assert by_name["Python"] == "programming_language"
        assert by_name["Docker"] == "tool"
        assert by_name["AWS"] == "platform"

    async def test_empty_input_returns_empty_graph(self):
        normaliser = SkillNormaliser(llm=AsyncMock())
        graph = await normaliser.normalise([])
        assert graph.nodes == []


class TestSkillNormaliserLLMPath:
    async def test_unknown_skills_sent_to_llm(
        self, skill_normaliser: SkillNormaliser, mock_llm: AsyncMock
    ):
        llm_output = [
            {"raw": "Temporal", "canonical": "Temporal", "category": "tool"},
            {"raw": "Dagster", "canonical": "Dagster", "category": "tool"},
        ]
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(llm_output)))
        graph = await skill_normaliser.normalise(["Temporal", "Dagster"])
        assert len(graph.nodes) == 2
        categories = {n.canonical_name: n.category for n in graph.nodes}
        assert categories["Temporal"] == "tool"

    async def test_llm_failure_uses_fallback_category(
        self, skill_normaliser: SkillNormaliser, mock_llm: AsyncMock
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        graph = await skill_normaliser.normalise(["UnknownTool"])
        assert len(graph.nodes) == 1
        assert graph.nodes[0].category == "other"
        assert graph.nodes[0].canonical_name == "UnknownTool"

    async def test_mixed_known_and_unknown_skills(
        self, skill_normaliser: SkillNormaliser, mock_llm: AsyncMock
    ):
        llm_output = [{"raw": "Dagster", "canonical": "Dagster", "category": "tool"}]
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(llm_output)))
        graph = await skill_normaliser.normalise(["python", "Dagster"])
        canonical_names = {n.canonical_name for n in graph.nodes}
        assert "Python" in canonical_names
        assert "Dagster" in canonical_names


class TestSkillGraph:
    def test_by_category_groups_correctly(self, simple_skill_graph: SkillGraph):
        by_cat = simple_skill_graph.by_category
        assert "programming_language" in by_cat
        assert "framework" in by_cat
        lang_names = [n.canonical_name for n in by_cat["programming_language"]]
        assert "Python" in lang_names

    def test_canonical_names_property(self, simple_skill_graph: SkillGraph):
        names = simple_skill_graph.canonical_names
        assert "Python" in names
        assert "FastAPI" in names
        assert len(names) == 4


# ── ReadinessScorer ───────────────────────────────────────────────────────────


class TestBuildReadinessResult:
    def test_scores_clamped_above_one(self):
        raw = {
            "required_skills_matched": 1.5,
            "preferred_skills_matched": 0.6,
            "experience_level_match": 0.8,
            "education_match": 0.7,
            "domain_alignment": 0.9,
            "matched_skills": [], "missing_required_skills": [],
            "missing_preferred_skills": [], "recommendations": [],
        }
        result = _build_readiness_result(raw)
        assert result.breakdown.required_skills_matched == 1.0

    def test_scores_clamped_below_zero(self):
        raw = {
            "required_skills_matched": -0.1,
            "preferred_skills_matched": 0.6,
            "experience_level_match": 0.8,
            "education_match": 0.7,
            "domain_alignment": 0.9,
            "matched_skills": [], "missing_required_skills": [],
            "missing_preferred_skills": [], "recommendations": [],
        }
        result = _build_readiness_result(raw)
        assert result.breakdown.required_skills_matched == 0.0

    def test_all_ones_produce_overall_one(self):
        raw = {
            "required_skills_matched": 1.0,
            "preferred_skills_matched": 1.0,
            "experience_level_match": 1.0,
            "education_match": 1.0,
            "domain_alignment": 1.0,
            "matched_skills": [], "missing_required_skills": [],
            "missing_preferred_skills": [], "recommendations": [],
        }
        result = _build_readiness_result(raw)
        assert result.overall_score == pytest.approx(1.0, abs=0.001)

    def test_all_zeros_produce_overall_zero(self):
        raw = {
            "required_skills_matched": 0.0,
            "preferred_skills_matched": 0.0,
            "experience_level_match": 0.0,
            "education_match": 0.0,
            "domain_alignment": 0.0,
            "matched_skills": [], "missing_required_skills": ["Python"],
            "missing_preferred_skills": [], "recommendations": ["Learn Python"],
        }
        result = _build_readiness_result(raw)
        assert result.overall_score == pytest.approx(0.0, abs=0.001)


class TestHeuristicScore:
    def test_experienced_candidate_scores_higher(
        self, simple_parsed_cv: ParsedCV, simple_skill_graph: SkillGraph
    ):
        result = _heuristic_score(simple_parsed_cv, simple_skill_graph)
        assert result.overall_score > 0.0

    def test_no_experience_no_skills_scores_zero(self):
        cv = ParsedCV(raw_text="")
        graph = SkillGraph(nodes=[])
        result = _heuristic_score(cv, graph)
        assert result.overall_score == pytest.approx(0.0, abs=0.001)

    def test_score_bounded_zero_to_one(
        self, simple_parsed_cv: ParsedCV, simple_skill_graph: SkillGraph
    ):
        result = _heuristic_score(simple_parsed_cv, simple_skill_graph)
        assert 0.0 <= result.overall_score <= 1.0

    def test_fallback_recommendation_present(self):
        cv = ParsedCV(raw_text="")
        graph = SkillGraph(nodes=[])
        result = _heuristic_score(cv, graph)
        assert len(result.recommendations) > 0


class TestReadinessScorerAsync:
    async def test_successful_llm_scoring(
        self,
        readiness_scorer: ReadinessScorer,
        mock_llm: AsyncMock,
        simple_parsed_cv: ParsedCV,
        simple_skill_graph: SkillGraph,
    ):
        payload = {
            "required_skills_matched": 0.8,
            "preferred_skills_matched": 0.6,
            "experience_level_match": 0.9,
            "education_match": 0.8,
            "domain_alignment": 0.85,
            "matched_skills": ["Python", "FastAPI"],
            "missing_required_skills": ["Kubernetes"],
            "missing_preferred_skills": [],
            "recommendations": ["Get CKA certification"],
        }
        mock_llm.ainvoke = AsyncMock(return_value=_llm_response(json.dumps(payload)))
        result = await readiness_scorer.score(
            simple_parsed_cv, simple_skill_graph, "Senior Backend Engineer"
        )
        assert result.overall_score > 0.0
        assert "Python" in result.matched_skills
        assert "Kubernetes" in result.missing_required_skills
        assert len(result.recommendations) == 1

    async def test_llm_failure_falls_back_to_heuristic(
        self,
        readiness_scorer: ReadinessScorer,
        mock_llm: AsyncMock,
        simple_parsed_cv: ParsedCV,
        simple_skill_graph: SkillGraph,
    ):
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await readiness_scorer.score(
            simple_parsed_cv, simple_skill_graph, "Senior Backend Engineer"
        )
        assert isinstance(result, ReadinessResult)
        assert 0.0 <= result.overall_score <= 1.0


# ── CVAgent ───────────────────────────────────────────────────────────────────


class TestCVAgent:
    def _make_agent(
        self,
        parsed_cv: ParsedCV | None = None,
        skill_graph: SkillGraph | None = None,
        readiness: ReadinessResult | None = None,
        emit_events: bool = False,
    ) -> tuple[CVAgent, MagicMock, AsyncMock, MagicMock, AsyncMock, AsyncMock]:
        mock_pdf = MagicMock(spec=PDFParser)
        mock_cv_parser = AsyncMock(spec=CVParser)
        mock_skill_extractor = MagicMock(spec=SkillExtractor)
        mock_normaliser = AsyncMock(spec=SkillNormaliser)
        mock_scorer = AsyncMock(spec=ReadinessScorer)
        mock_publisher = MagicMock() if emit_events else None

        _parsed = parsed_cv or ParsedCV(raw_text="sample", raw_skills=["Python"])
        _graph = skill_graph or SkillGraph(nodes=[
            SkillNode(name="Python", canonical_name="Python", category="programming_language")
        ])
        _readiness = readiness or ReadinessResult(
            overall_score=0.75,
            breakdown=ReadinessBreakdown(
                required_skills_matched=0.8,
                preferred_skills_matched=0.6,
                experience_level_match=0.7,
                education_match=0.8,
                domain_alignment=0.75,
            ),
            matched_skills=["Python"],
            missing_required_skills=[],
            missing_preferred_skills=[],
            recommendations=["Learn Kubernetes"],
        )

        mock_pdf.extract_text = MagicMock(return_value="sample CV text")
        mock_cv_parser.parse = AsyncMock(return_value=_parsed)
        mock_skill_extractor.extract = MagicMock(return_value=["Python"])
        mock_normaliser.normalise = AsyncMock(return_value=_graph)
        mock_scorer.score = AsyncMock(return_value=_readiness)

        agent = CVAgent(
            pdf_parser=mock_pdf,
            cv_parser=mock_cv_parser,
            skill_extractor=mock_skill_extractor,
            skill_normaliser=mock_normaliser,
            readiness_scorer=mock_scorer,
            event_publisher=mock_publisher,
        )
        return agent, mock_pdf, mock_cv_parser, mock_skill_extractor, mock_normaliser, mock_scorer

    def test_agent_type(self):
        agent, *_ = self._make_agent()
        assert agent.agent_type == AgentType.CV_ANALYSIS

    def test_display_name(self):
        agent, *_ = self._make_agent()
        assert agent.display_name == "CV Analysis Agent"

    async def test_execute_returns_required_keys(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        required = {"cv_text_length", "parsed_cv", "skill_graph", "readiness", "processing_steps"}
        assert required.issubset(result.keys())

    async def test_execute_has_five_processing_steps(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert len(result["processing_steps"]) == 5

    async def test_pdf_parser_receives_cv_document(self):
        agent, mock_pdf, *_ = self._make_agent()
        context = _make_context(cv_document="my plain text cv")
        await agent._execute(context)
        mock_pdf.extract_text.assert_called_once()
        assert mock_pdf.extract_text.call_args[0][0] == "my plain text cv"

    async def test_cv_parser_receives_extracted_text(self):
        agent, mock_pdf, mock_cv_parser, *_ = self._make_agent()
        mock_pdf.extract_text.return_value = "Extracted CV text"
        await agent._execute(_make_context())
        mock_cv_parser.parse.assert_called_once()
        assert mock_cv_parser.parse.call_args[0][0] == "Extracted CV text"

    async def test_target_role_passed_to_scorer(self):
        agent, _, _, _, _, mock_scorer = self._make_agent()
        profile = UserProfileSnapshot(target_role="ML Engineer")
        context = _make_context(profile=profile)
        await agent._execute(context)
        mock_scorer.score.assert_called_once()
        _, _, role = mock_scorer.score.call_args[0]
        assert role == "ML Engineer"

    async def test_empty_target_role_handled(self):
        agent, _, _, _, _, mock_scorer = self._make_agent()
        profile = UserProfileSnapshot(target_role=None)
        await agent._execute(_make_context(profile=profile))
        _, _, role = mock_scorer.score.call_args[0]
        assert role == ""

    async def test_readiness_in_output(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert result["readiness"]["overall_score"] == pytest.approx(0.75)
        assert "breakdown" in result["readiness"]
        assert "recommendations" in result["readiness"]

    async def test_skill_graph_in_output(self):
        agent, *_ = self._make_agent()
        result = await agent._execute(_make_context())
        assert "nodes" in result["skill_graph"]
        assert "by_category" in result["skill_graph"]
        assert result["skill_graph"]["nodes"][0]["canonical_name"] == "Python"

    async def test_five_progress_events_emitted(self):
        agent, *_ = self._make_agent(emit_events=True)
        mock_publisher = agent._event_publisher
        await agent._execute(_make_context())
        assert mock_publisher.emit.call_count == 5

    async def test_no_events_without_publisher(self):
        agent, *_ = self._make_agent(emit_events=False)
        result = await agent._execute(_make_context())
        assert "cv_text_length" in result

    async def test_full_pipeline_via_base_agent_run(self):
        from agents.contracts.results import AgentResultStatus

        agent, *_ = self._make_agent()
        agent_result = await agent.run(_make_context())
        assert agent_result.agent_type == AgentType.CV_ANALYSIS.value
        assert agent_result.status == AgentResultStatus.COMPLETED
        assert "readiness" in agent_result.output
        assert agent_result.duration_ms >= 0


# ── Serialisers ───────────────────────────────────────────────────────────────


class TestSerialiseParsedCV:
    def test_all_top_level_fields_present(self, simple_parsed_cv: ParsedCV):
        out = _serialise_parsed_cv(simple_parsed_cv)
        assert out["full_name"] == "Jane Doe"
        assert out["email"] == "jane@example.com"
        assert out["total_experience_months"] == 36

    def test_experience_entry_structure(self, simple_parsed_cv: ParsedCV):
        out = _serialise_parsed_cv(simple_parsed_cv)
        exp = out["experience"][0]
        assert exp["company"] == "Acme Corp"
        assert "impact_statements" in exp
        assert "responsibilities" in exp

    def test_minimal_cv_serialises_cleanly(self):
        out = _serialise_parsed_cv(ParsedCV(raw_text=""))
        assert out["experience"] == []
        assert out["raw_skills"] == []
        assert out["full_name"] is None


class TestSerialiseSkillGraph:
    def test_nodes_and_by_category_present(self, simple_skill_graph: SkillGraph):
        out = _serialise_skill_graph(simple_skill_graph)
        assert "nodes" in out
        assert "by_category" in out

    def test_node_required_fields(self, simple_skill_graph: SkillGraph):
        out = _serialise_skill_graph(simple_skill_graph)
        node = out["nodes"][0]
        for field in ("name", "canonical_name", "category", "proficiency",
                      "years_of_experience", "evidence_sources"):
            assert field in node

    def test_by_category_groups_correctly(self, simple_skill_graph: SkillGraph):
        out = _serialise_skill_graph(simple_skill_graph)
        assert "programming_language" in out["by_category"]
        assert "Python" in out["by_category"]["programming_language"]
