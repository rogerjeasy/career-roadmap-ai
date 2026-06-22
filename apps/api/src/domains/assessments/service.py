"""Skill Assessment domain — service layer.

``start`` generates a graded quiz (answer key stored server-side); ``submit``
grades the answers with the LLM, derives a measured proficiency level + gaps,
mints a verifiable credential on a pass, and writes the measured skill back into
the session profile so the roadmap can act on real (not assumed) gaps.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.assessments.firestore_repository import FirestoreAssessmentRepository
from src.domains.assessments.schemas import (
    PASS_THRESHOLD,
    AssessmentOut,
    AssessmentStartInput,
    AssessmentSubmit,
    AssessmentSummary,
    level_for_score,
)
from src.domains.credentials.firestore_repository import FirestoreCredentialRepository
from src.domains.credentials.schemas import CredentialIssue
from src.domains.credentials.service import CredentialService
from src.domains.evidence.firestore_repository import FirestoreEvidenceRepository
from src.session.manager import SessionManager, get_session_manager
from src.session.models import UserProfileContext

logger = get_logger(__name__)

_GEN_SYSTEM = """You are a rigorous technical assessor. Write a fair, non-trivial \
quiz that measures genuine proficiency in ONE skill. Mix multiple-choice and \
short-answer questions. Questions must be unambiguous and have a defensible \
correct answer. Do not test trivia; test understanding and application. Do not \
reference or infer any protected attribute.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "questions": [
    {
      "kind": "mcq",
      "prompt": "the question",
      "options": ["A", "B", "C", "D"],
      "correct": "the exact text of the correct option",
      "rubric": ""
    },
    {
      "kind": "short",
      "prompt": "the question",
      "options": [],
      "correct": "a model answer",
      "rubric": "what a strong answer must demonstrate"
    }
  ]
}
Rules: produce exactly the requested number of questions; roughly 60% mcq, 40% \
short; mcq must have exactly 4 distinct options.
"""

_GRADE_SYSTEM = """You are a fair, calibrated grader. Grade the candidate's answers \
against the provided answer key and rubric. Be honest — do not inflate. For \
short answers, award partial credit per the rubric. Then summarise measured \
strengths and the concrete gaps the answers revealed. Expose uncertainty: if an \
answer is borderline, reflect that in the score rather than rounding up. Do not \
infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "score": integer 0-100 (overall proficiency the answers demonstrate),
  "summary": "2-3 sentences on the measured proficiency",
  "strengths": ["a topic the candidate clearly handled well", "..."],
  "gaps": [
    {"topic": "a topic the answers were weak on", "note": "what to study"}
  ]
}
Rules: 0-4 strengths; 0-5 gaps; ground every gap in an actual weak answer.
"""


class AssessmentService:
    def __init__(
        self,
        repo: FirestoreAssessmentRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
        evidence: FirestoreEvidenceRepository,
        credentials: CredentialService,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions
        self._evidence = evidence
        self._credentials = credentials

    # ── Reads ───────────────────────────────────────────────────────────────────

    async def list(self, user_id: str) -> list[AssessmentSummary]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [AssessmentSummary.from_doc(d) for d in docs]

    async def get(self, user_id: str, assessment_id: str) -> AssessmentOut:
        doc = await self._repo.get(assessment_id, user_id)
        if doc is None:
            raise NotFoundError("Assessment not found.")
        return AssessmentOut.from_doc(doc)

    # ── Start ────────────────────────────────────────────────────────────────────

    async def start(self, user_id: str, payload: AssessmentStartInput) -> AssessmentOut:
        prompt = (
            f"SKILL: {payload.skill}\n"
            f"NUMBER OF QUESTIONS: {payload.num_questions}\n\n"
            "Generate the quiz per the schema."
        )
        try:
            raw = await self._llm.complete_json(system=_GEN_SYSTEM, user=prompt, max_tokens=2560)
        except ValueError:
            raw = {}
        items = raw.get("questions", []) if isinstance(raw, dict) else []
        questions: list[dict] = []
        answer_key: dict[str, dict] = {}
        for item in items:
            if not isinstance(item, dict) or not item.get("prompt"):
                continue
            qid = str(uuid4())
            kind = "mcq" if item.get("kind") == "mcq" else "short"
            options = [str(o) for o in (item.get("options") or [])] if kind == "mcq" else []
            questions.append({"id": qid, "kind": kind, "prompt": str(item["prompt"]), "options": options})
            answer_key[qid] = {
                "correct": str(item.get("correct", "")),
                "rubric": str(item.get("rubric", "")),
            }
        if not questions:
            raise ValidationError("Couldn't generate an assessment for that skill. Try again.")

        doc = await self._repo.create(
            user_id,
            {
                "skill": payload.skill.strip(),
                "status": "in_progress",
                "num_questions": len(questions),
                "questions": questions,
                "answer_key": answer_key,
                "score": None,
                "passed": False,
            },
        )
        logger.info("assessment.started", user_id=user_id, skill=payload.skill, count=len(questions))
        return AssessmentOut.from_doc(doc)

    # ── Submit & grade ───────────────────────────────────────────────────────────

    async def submit(
        self, user_id: str, assessment_id: str, holder_name: str, payload: AssessmentSubmit
    ) -> AssessmentOut:
        doc = await self._repo.get(assessment_id, user_id)
        if doc is None:
            raise NotFoundError("Assessment not found.")
        if doc.get("status") == "graded":
            raise ValidationError("This assessment has already been graded.")

        skill = str(doc.get("skill", ""))
        answer_key = doc.get("answer_key") or {}
        by_id = {str(q.get("id")): q for q in (doc.get("questions") or [])}
        given = {a.question_id: a.answer for a in payload.answers}

        lines: list[str] = []
        for qid, q in by_id.items():
            key = answer_key.get(qid, {})
            lines.append(
                f"Q ({q.get('kind')}): {q.get('prompt')}\n"
                f"Answer key: {key.get('correct', '')}\n"
                f"Rubric: {key.get('rubric', '') or '(exact/near-exact match)'}\n"
                f"Candidate answer: {given.get(qid, '(blank)') or '(blank)'}\n"
            )
        grade_prompt = f"SKILL: {skill}\n\n" + "\n".join(lines) + "\nGrade per the schema."

        try:
            raw = await self._llm.complete_json(system=_GRADE_SYSTEM, user=grade_prompt, max_tokens=1536)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        score = _clamp_score(raw.get("score"))
        level = level_for_score(score)
        passed = score >= PASS_THRESHOLD
        summary = str(raw.get("summary", ""))
        strengths = [str(s) for s in (raw.get("strengths") or [])][:4]
        gaps = [
            {"topic": str(g.get("topic", "")), "note": str(g.get("note", ""))}
            for g in (raw.get("gaps") or [])
            if isinstance(g, dict) and g.get("topic")
        ][:5]

        credential_id: str | None = None
        evidence_id: str | None = None
        if passed:
            credential_id, evidence_id = await self._mint_badge(
                user_id, holder_name, skill, level, score, summary
            )

        result = {
            "status": "graded",
            "score": score,
            "level": level,
            "passed": passed,
            "summary": summary,
            "strengths": strengths,
            "gaps": gaps,
            "credential_id": credential_id,
            "evidence_id": evidence_id,
            "graded_at": utcnow(),
        }
        updated = await self._repo.update(assessment_id, user_id, result)
        await self._record_measured_skill(user_id, skill, level, score, gaps)
        logger.info(
            "assessment.graded",
            user_id=user_id,
            assessment_id=assessment_id,
            skill=skill,
            score=score,
            passed=passed,
        )
        return AssessmentOut.from_doc(updated or {**doc, **result})

    # ── Internals ─────────────────────────────────────────────────────────────────

    async def _mint_badge(
        self, user_id: str, holder_name: str, skill: str, level: str, score: int, summary: str
    ) -> tuple[str | None, str | None]:
        """Create an evidence item for the pass, then mint a signed credential."""
        try:
            evidence_doc = await self._evidence.create(
                user_id,
                {
                    "title": f"{skill} skill assessment — {score}%",
                    "description": summary or f"Passed the {skill} assessment at {level} level.",
                    "type": "certification",
                    "link": "",
                    "date_label": utcnow().strftime("%b %Y"),
                    "skills": [skill],
                },
            )
            evidence_id = evidence_doc["id"]
            credential = await self._credentials.issue(
                user_id,
                holder_name,
                CredentialIssue(
                    skill=skill,
                    level=level,  # type: ignore[arg-type]
                    summary=summary or f"Measured {level} proficiency ({score}%).",
                    evidence_ids=[evidence_id],
                ),
            )
            return credential.id, evidence_id
        except Exception as exc:  # noqa: BLE001 - badge minting must not fail the grade
            logger.warning("assessment.badge_mint_failed", user_id=user_id, error=str(exc))
            return None, None

    async def _record_measured_skill(
        self, user_id: str, skill: str, level: str, score: int, gaps: list[dict]
    ) -> None:
        """Persist the measured result into the session profile for the roadmap."""
        try:
            session = await self._sessions.get(user_id)
            if session is None:
                return
            profile = session.user_profile_context or UserProfileContext()
            assessed = dict(profile.additional.get("assessed_skills") or {})
            assessed[skill.lower()] = {
                "skill": skill,
                "level": level,
                "score": score,
                "gaps": [g.get("topic", "") for g in gaps],
                "measured_at": utcnow().isoformat(),
            }
            profile.additional["assessed_skills"] = assessed
            await self._sessions.set_user_profile_context(user_id, profile)
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment
            logger.warning("assessment.profile_update_failed", user_id=user_id, error=str(exc))


def _clamp_score(value: object) -> int:
    try:
        return max(0, min(100, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


async def get_assessment_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> AssessmentService:
    credentials = CredentialService(
        FirestoreCredentialRepository(db),
        FirestoreCrudRepository(db, "evidence"),
    )
    return AssessmentService(
        FirestoreAssessmentRepository(db),
        llm,
        sessions,
        FirestoreEvidenceRepository(db),
        credentials,
    )
