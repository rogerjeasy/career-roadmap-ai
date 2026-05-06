"""ClarificationEngine — profile completeness scoring, question generation, and answer parsing.

Design:
- Stateless: all user-profile state lives in ``OrchestratorState`` / Redis.
- Observable: every public method opens an OTel span and updates Prometheus metrics.
- Resilient: LLM calls use tenacity retries (3 attempts, exponential back-off).
- Decoupled: depends only on ``agents.contracts``, ``agents.config``, and ``agents.core``.

Public API:
  ``score()``              — deterministic slot-based completeness check (sync, free).
  ``generate_questions()`` — LLM-backed targeted follow-up questions (async).
  ``parse_answers()``      — LLM-backed free-text → structured field extraction (async).
  ``apply_answers()``      — immutable merge of parsed answers into a profile (sync).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agents.config import agent_settings
from agents.contracts.tasks import UserProfileSnapshot
from agents.core.logging import get_logger
from agents.core.observability import (
    CLARIFICATION_ANSWER_PARSE_DURATION,
    CLARIFICATION_ANSWER_PARSE_TOTAL,
    CLARIFICATION_QUESTIONS_TOTAL,
    CLARIFICATION_RESOLVED_TOTAL,
    CLARIFICATION_ROUND_TOTAL,
    CLARIFICATION_SCORE,
    QUESTION_GENERATION_DURATION,
    get_tracer,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.orchestrator.clarification")

# ── Slot weights (must sum to 1.0) ─────────────────────────────────────────
# Higher weight = more blocking for downstream agents.
_SLOT_WEIGHTS: dict[str, float] = {
    "target_role": 0.30,
    "current_role": 0.15,
    "skills": 0.15,
    "location": 0.10,
    "timeline_months": 0.15,
    "weekly_hours_available": 0.10,
    "salary_goal": 0.05,
}

# ── System prompts ─────────────────────────────────────────────────────────

_QUESTION_SYSTEM = """\
You are a career advisor conducting a brief intake interview. The user wants a
personalised career roadmap but some key information is missing.

Generate exactly {n} targeted, friendly questions — one question per missing field.
Each question must:
- Address exactly one missing field (field_name must match exactly).
- Be conversational and concise (≤ 20 words).
- Include a concrete example in parentheses.

Reply with ONLY a JSON array — no prose, no markdown code fences:
[{{"question": "...", "field_name": "...", "priority": 1}}]
Priority 1 = most urgent. Do not number the questions.
"""

_ANSWER_PARSE_SYSTEM = """\
You are extracting structured career information from a user's conversational reply.

Questions that were asked (JSON):
{questions_json}

User's reply:
{user_reply}

Extract the value for each field that was clearly answered.
Return ONLY a valid JSON object with any subset of these keys:
{{
  "target_role": "string",
  "current_role": "string",
  "skills": ["list", "of", "strings"],
  "location": "string",
  "timeline_months": integer,
  "weekly_hours_available": integer,
  "salary_goal": integer
}}

Rules:
- Omit any field that was NOT clearly answered in the reply (never guess).
- skills: split comma- or semicolon-separated values into individual strings.
- timeline_months: convert "1 year" → 12; "6 months" → 6; integers stay as-is.
- salary_goal: strip currency symbols and commas; use the annual integer amount.
- weekly_hours_available: integer hours per week only.
Return {{}} if nothing was clearly answered.
"""


# ── Data types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClarificationQuestion:
    """An immutable clarification question produced by the engine."""

    question: str
    field_name: str
    priority: int = 1
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "field_name": self.field_name,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClarificationQuestion:
        return cls(
            question=d["question"],
            field_name=d["field_name"],
            priority=d.get("priority", 1),
            id=d.get("id", str(uuid.uuid4())),
        )


# ── Engine ─────────────────────────────────────────────────────────────────


class ClarificationEngine:
    """Scoring, question generation, and answer parsing for the clarification flow.

    One instance is created per ``MasterOrchestrator`` and shared across the
    LangGraph nodes. The engine itself holds no mutable state: everything
    flows through the arguments and the returned values.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=512,
            temperature=0.2,
        )

    # ── 1. Score ──────────────────────────────────────────────────────────

    def score(
        self,
        profile: UserProfileSnapshot,
        *,
        correlation_id: str = "",
    ) -> tuple[float, list[str]]:
        """Return ``(completeness_score ∈ [0, 1], missing_slot_names)``.

        Pure function: deterministic, O(1), no I/O. Safe to call many times.
        """
        with _tracer.start_as_current_span("clarification.score") as span:
            span.set_attribute("correlation_id", correlation_id)

            total = 0.0
            missing: list[str] = []

            for slot, weight in _SLOT_WEIGHTS.items():
                value = getattr(profile, slot, None)
                present = bool(value)
                if present:
                    total += weight
                else:
                    missing.append(slot)

            result = round(total, 3)
            span.set_attribute("score", result)
            span.set_attribute("missing_count", len(missing))
            span.set_attribute("missing_slots", ",".join(missing))
            span.set_status(Status(StatusCode.OK))

            CLARIFICATION_SCORE.observe(result)
            logger.info(
                "clarification.scored",
                score=result,
                missing=missing,
                correlation_id=correlation_id,
            )
            return result, missing

    # ── 2. Question generation ────────────────────────────────────────────

    async def generate_questions(
        self,
        profile: UserProfileSnapshot,
        missing_slots: list[str],
        user_message: str,
        n: int | None = None,
        *,
        correlation_id: str = "",
        intent_type: str = "unknown",
    ) -> list[ClarificationQuestion]:
        """Generate ≤N targeted questions for the highest-weight missing slots.

        Always returns a non-empty list when ``missing_slots`` is non-empty.
        Falls back to pre-written questions if the LLM call fails after retries.
        """
        with _tracer.start_as_current_span("clarification.generate_questions") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("intent_type", intent_type)
            span.set_attribute("missing_count", len(missing_slots))

            n_needed = min(
                n or agent_settings.max_clarification_questions,
                len(missing_slots),
            )
            if n_needed == 0:
                CLARIFICATION_QUESTIONS_TOTAL.labels(status="skipped").inc()
                span.set_status(Status(StatusCode.OK))
                return []

            # Sort by descending weight so we ask the most blocking question first.
            prioritised = sorted(
                missing_slots,
                key=lambda s: _SLOT_WEIGHTS.get(s, 0.0),
                reverse=True,
            )[:n_needed]

            CLARIFICATION_ROUND_TOTAL.inc()
            t0 = time.monotonic()

            try:
                questions = await self._generate_via_llm(
                    profile, prioritised, user_message, n_needed
                )
                duration = time.monotonic() - t0
                QUESTION_GENERATION_DURATION.observe(duration)
                CLARIFICATION_QUESTIONS_TOTAL.labels(status="generated").inc()

                capped = questions[: agent_settings.max_clarification_questions]
                span.set_attribute("questions_generated", len(capped))
                span.set_attribute("duration_ms", int(duration * 1000))
                span.set_status(Status(StatusCode.OK))

                logger.info(
                    "clarification.questions_generated",
                    count=len(capped),
                    slots=prioritised,
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return capped

            except Exception as exc:
                duration = time.monotonic() - t0
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                CLARIFICATION_QUESTIONS_TOTAL.labels(status="fallback").inc()

                logger.warning(
                    "clarification.questions_fallback",
                    error=str(exc),
                    slots=prioritised,
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return [
                    ClarificationQuestion(
                        question=_fallback_question(slot),
                        field_name=slot,
                        priority=i + 1,
                    )
                    for i, slot in enumerate(prioritised)
                ]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _generate_via_llm(
        self,
        profile: UserProfileSnapshot,
        prioritised_slots: list[str],
        user_message: str,
        n: int,
    ) -> list[ClarificationQuestion]:
        context = (
            f"User goal: {user_message}\n"
            f"Current role: {profile.current_role or 'unknown'}\n"
            f"Target role: {profile.target_role or 'unknown'}\n"
            f"Missing fields (priority order): {', '.join(prioritised_slots)}"
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_QUESTION_SYSTEM.format(n=n)),
                HumanMessage(content=context),
            ]
        )
        raw: list[dict[str, Any]] = json.loads(str(response.content))
        return [
            ClarificationQuestion(
                question=item["question"],
                field_name=item["field_name"],
                priority=i + 1,
                id=item.get("id", str(uuid.uuid4())),
            )
            for i, item in enumerate(raw)
        ]

    # ── 3. Answer parsing ─────────────────────────────────────────────────

    async def parse_answers(
        self,
        questions: list[ClarificationQuestion],
        user_response: str,
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Extract structured field values from the user's free-text reply.

        Returns a ``{field_name: coerced_value}`` dict for every field that
        was clearly answered. Returns ``{}`` when nothing was parseable or
        when inputs are empty.

        The LLM call is retried up to 3 times on transient failure.
        On persistent failure the method returns ``{}`` so the caller can
        proceed without crashing the orchestration loop.
        """
        if not questions or not user_response.strip():
            return {}

        with _tracer.start_as_current_span("clarification.parse_answers") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("questions_count", len(questions))

            t0 = time.monotonic()
            questions_json = json.dumps(
                [q.to_dict() for q in questions], ensure_ascii=False
            )

            try:
                raw = await self._parse_via_llm(questions_json, user_response)
                validated = _coerce_parsed_values(raw)

                duration = time.monotonic() - t0
                CLARIFICATION_ANSWER_PARSE_DURATION.observe(duration)

                status = "empty" if not validated else "success"
                CLARIFICATION_ANSWER_PARSE_TOTAL.labels(status=status).inc()

                span.set_attribute("fields_extracted", len(validated))
                span.set_attribute("fields", ",".join(validated.keys()))
                span.set_attribute("duration_ms", int(duration * 1000))
                span.set_status(Status(StatusCode.OK))

                logger.info(
                    "clarification.answers_parsed",
                    fields=list(validated.keys()),
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return validated

            except Exception as exc:
                duration = time.monotonic() - t0
                CLARIFICATION_ANSWER_PARSE_DURATION.observe(duration)
                CLARIFICATION_ANSWER_PARSE_TOTAL.labels(status="fallback").inc()

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

                logger.warning(
                    "clarification.answer_parse_failed",
                    error=str(exc),
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _parse_via_llm(
        self, questions_json: str, user_response: str
    ) -> dict[str, Any]:
        prompt = _ANSWER_PARSE_SYSTEM.format(
            questions_json=questions_json,
            user_reply=user_response,
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content="Extract the structured values now."),
            ]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Expected JSON object, got {type(result).__name__}")
        return result

    # ── 4. Profile merging ────────────────────────────────────────────────

    def apply_answers(
        self,
        profile: UserProfileSnapshot,
        parsed_answers: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[UserProfileSnapshot, list[str]]:
        """Apply parsed answer values onto a profile snapshot.

        Returns ``(updated_profile, applied_field_names)``.
        The original profile is never mutated (Pydantic ``model_copy``).

        Merge rules:
        - ``skills``: union with existing list (deduplication).
        - All other fields: overwrite only if the new value is non-empty.
        """
        if not parsed_answers:
            return profile, []

        with _tracer.start_as_current_span("clarification.apply_answers") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("candidates", len(parsed_answers))

            updates: dict[str, Any] = {}
            applied: list[str] = []

            for slot, value in parsed_answers.items():
                if slot not in _SLOT_WEIGHTS or value is None:
                    continue

                current = getattr(profile, slot, None)

                if slot == "skills":
                    # Merge skill sets; preserve order of new items after existing ones.
                    existing = set(current or [])
                    merged = list(current or []) + [
                        s for s in (value or []) if s not in existing
                    ]
                    updates[slot] = merged
                    applied.append(slot)
                else:
                    # Scalar fields: overwrite (the LLM only returns clearly answered values).
                    if value:
                        updates[slot] = value
                        applied.append(slot)

            updated = profile.model_copy(update=updates)

            # Compute score delta for logging and metrics (cheap, no I/O).
            old_score = _fast_score(profile)
            new_score = _fast_score(updated)
            resolved = new_score >= agent_settings.completeness_threshold

            if resolved:
                CLARIFICATION_RESOLVED_TOTAL.inc()

            span.set_attribute("applied_count", len(applied))
            span.set_attribute("applied_fields", ",".join(applied))
            span.set_attribute("old_score", old_score)
            span.set_attribute("new_score", new_score)
            span.set_attribute("resolved", resolved)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "clarification.profile_updated",
                applied=applied,
                old_score=old_score,
                new_score=new_score,
                score_delta=round(new_score - old_score, 3),
                resolved=resolved,
                correlation_id=correlation_id,
            )
            return updated, applied


# ── Helpers ────────────────────────────────────────────────────────────────


def _fast_score(profile: UserProfileSnapshot) -> float:
    """Compute completeness score without opening an OTel span."""
    return round(
        sum(
            weight
            for slot, weight in _SLOT_WEIGHTS.items()
            if bool(getattr(profile, slot, None))
        ),
        3,
    )


def _coerce_parsed_values(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise LLM output to the expected Python types for each slot."""
    result: dict[str, Any] = {}

    for slot, value in raw.items():
        if value is None or slot not in _SLOT_WEIGHTS:
            continue
        try:
            if slot in ("target_role", "current_role", "location"):
                if isinstance(value, str) and value.strip():
                    result[slot] = value.strip()

            elif slot == "skills":
                if isinstance(value, list):
                    skills = [s.strip() for s in value if isinstance(s, str) and s.strip()]
                elif isinstance(value, str):
                    skills = [
                        s.strip()
                        for s in value.replace(";", ",").split(",")
                        if s.strip()
                    ]
                else:
                    skills = []
                if skills:
                    result[slot] = skills

            elif slot in ("timeline_months", "weekly_hours_available", "salary_goal"):
                if isinstance(value, (int, float)) and value > 0:
                    result[slot] = int(value)
                elif isinstance(value, str):
                    digits = "".join(c for c in value if c.isdigit())
                    if digits:
                        result[slot] = int(digits)

        except (ValueError, TypeError):
            pass  # skip unparseable values rather than crashing

    return result


def _fallback_question(slot: str) -> str:
    _MAP: dict[str, str] = {
        "target_role": "What role are you aiming for? (e.g. Senior ML Engineer)",
        "current_role": "What is your current job title? (e.g. Backend Developer)",
        "skills": "What are your top technical skills? (e.g. Python, SQL, React)",
        "location": "Where are you based? (e.g. Zurich, Switzerland)",
        "timeline_months": "How many months are you targeting for this transition? (e.g. 12)",
        "weekly_hours_available": "How many hours per week can you dedicate? (e.g. 10)",
        "salary_goal": "What is your target annual salary? (e.g. 120000)",
    }
    return _MAP.get(slot, f"Could you share your {slot.replace('_', ' ')}?")
