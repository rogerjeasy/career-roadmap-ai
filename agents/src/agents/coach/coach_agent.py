"""CoachAgent — L3 Specialist Agent: always-on conversational career coach.

Responsibilities:
  1. Assemble full context: user profile, conversation history, plan/roadmap data.
  2. Classify the coaching type (ad-hoc, interview prep, timeline check, …).
  3. Call Claude with a rich, personalised prompt.
  4. Return a structured CoachResponse with actionable steps, confidence,
     and — when needed — a constructive timeline reality check.

The agent is invoked via the ``coach_query`` intent and runs standalone (no
upstream agent dependencies in that DAG). It can also run after a roadmap
generation pipeline, in which case ``plan_snapshot`` contains live outputs
from CV/gap/market agents and the coach response is deeply grounded.

Observable: OTel spans, STEP_PROGRESS SSE events, Prometheus counters/histograms.

Registration (Celery worker startup):
    from agents.bus.publisher import EventPublisher
    from agents.coach import CoachAgent
    from agents.core.agent_registry import registry

    registry.register(CoachAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    COACH_CONFIDENCE_SCORE,
    COACH_LLM_DURATION,
    COACH_LLM_TOTAL,
    COACH_TIMELINE_CONCERNS_TOTAL,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.coach.context_assembler import CoachContextAssembler
from agents.coach.models import ActionableStep, CoachContextBundle, CoachResponse, CoachingType

logger = get_logger(__name__)
_tracer = get_tracer("agents.coach.coach_agent")

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _default_model() -> str:
    return os.getenv("COACH_MODEL", "claude-haiku-4-5-20251001")


class CoachAgent(BaseAgent):
    """Always-on conversational career coach.

    Parameters
    ----------
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events. When ``None`` (e.g.
        in unit tests without Redis), progress events are silently skipped.
    llm:
        Override the LangChain LLM client (useful in tests).
    context_assembler:
        Override the context assembler (useful in tests).
    """

    def __init__(
        self,
        *,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
        context_assembler: CoachContextAssembler | None = None,
    ) -> None:
        self._event_publisher = event_publisher
        self._llm = llm or ChatAnthropic(
            model=_default_model(),
            max_tokens=2048,
            temperature=0.3,
        )
        self._assembler = context_assembler or CoachContextAssembler()
        self._system_prompt = _load_prompt("coach_system.txt")

    # ── BaseAgent contract ─────────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.COACH

    @property
    def display_name(self) -> str:
        return "Career Coach"

    async def _execute(self, context: AgentContext) -> dict:
        with _tracer.start_as_current_span("coach.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)
            span.set_attribute("has_plan_snapshot", bool(context.plan_snapshot))

            # ── Step 1: Assemble rich context ──────────────────────────────
            self._emit_progress(context, "context_assembly", "Reading your profile and history…")
            STEP_PROGRESS_TOTAL.labels(step_name="coach.context_assembly").inc()

            bundle = self._assembler.assemble(context)
            span.set_attribute("has_plan", bundle.has_plan)
            span.set_attribute("history_turns", len(bundle.conversation_history))

            # ── Step 2: Build prompt & call LLM ────────────────────────────
            self._emit_progress(context, "llm_inference", "Preparing your personalised coaching response…")
            STEP_PROGRESS_TOTAL.labels(step_name="coach.llm_inference").inc()

            coach_response = await self._call_llm(bundle, correlation_id=context.correlation_id)

            # ── Step 3: Record observability ───────────────────────────────
            span.set_attribute("coaching_type", coach_response.coaching_type.value)
            span.set_attribute("confidence", coach_response.confidence)
            span.set_attribute("timeline_concern", coach_response.timeline_concern)
            span.set_status(Status(StatusCode.OK))

            COACH_CONFIDENCE_SCORE.observe(coach_response.confidence)
            if coach_response.timeline_concern:
                COACH_TIMELINE_CONCERNS_TOTAL.inc()

            logger.info(
                "coach.completed",
                coaching_type=coach_response.coaching_type.value,
                confidence=coach_response.confidence,
                timeline_concern=coach_response.timeline_concern,
                response_length=len(coach_response.response),
                correlation_id=context.correlation_id,
            )

            return coach_response.model_dump()

    # ── LLM call ──────────────────────────────────────────────────────────────

    async def _call_llm(
        self,
        bundle: CoachContextBundle,
        *,
        correlation_id: str = "",
    ) -> CoachResponse:
        """Attempt the LLM call with retries; fall back deterministically on total failure."""
        t0 = time.monotonic()
        try:
            result = await self._call_llm_with_retry(bundle)
            COACH_LLM_TOTAL.labels(status="llm").inc()
            return result
        except Exception as exc:
            logger.warning(
                "coach.llm_failed",
                error=str(exc),
                fallback="structured",
                correlation_id=correlation_id,
            )
            COACH_LLM_TOTAL.labels(status="fallback").inc()
            return _fallback_response(bundle)
        finally:
            COACH_LLM_DURATION.observe(time.monotonic() - t0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _call_llm_with_retry(self, bundle: CoachContextBundle) -> CoachResponse:
        """Raw LLM call — retried up to 3 times before the caller falls back."""
        user_prompt = _build_user_prompt(bundle)
        response = await self._llm.ainvoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_prompt),
        ])
        raw_text = str(response.content).strip()

        # Strip markdown code fences if the model wraps the JSON
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        return _validate_llm_output(parsed)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _emit_progress(self, context: AgentContext, step: str, description: str) -> None:
        if self._event_publisher is None:
            return
        try:
            self._event_publisher.emit(
                AgentEvent(
                    event_type=AgentEventType.STEP_PROGRESS,
                    session_id=context.session_id,
                    user_id=context.user_id,
                    correlation_id=context.correlation_id,
                    payload={
                        "agent": self.agent_type.value,
                        "step": step,
                        "description": description,
                    },
                )
            )
        except Exception as exc:
            logger.warning("coach.progress_emit_failed", step=step, error=str(exc))


# ── Prompt builder ─────────────────────────────────────────────────────────────


def _build_user_prompt(bundle: CoachContextBundle) -> str:
    lines: list[str] = ["=== USER PROFILE ==="]

    if bundle.current_role:
        lines.append(f"Current role: {bundle.current_role}")
    if bundle.target_role:
        lines.append(f"Target role: {bundle.target_role}")
    if bundle.timeline_months:
        lines.append(f"Desired timeline: {bundle.timeline_months} months")
    if bundle.weekly_hours:
        lines.append(f"Weekly learning hours available: {bundle.weekly_hours}h")
    if bundle.skills:
        lines.append(f"Current skills: {', '.join(bundle.skills[:20])}")
    if bundle.goals:
        lines.append(f"Goals: {'; '.join(bundle.goals[:5])}")
    if bundle.constraints:
        lines.append(f"Constraints: {'; '.join(bundle.constraints[:5])}")

    if bundle.has_plan:
        lines.append("\n=== ROADMAP CONTEXT ===")
        if bundle.roadmap_summary:
            lines.append(bundle.roadmap_summary)
        if bundle.gap_summary:
            lines.append(f"Gap analysis: {bundle.gap_summary}")
        if bundle.market_summary:
            lines.append(f"Market intel: {bundle.market_summary}")
        if bundle.progress_summary:
            lines.append(f"Progress: {bundle.progress_summary}")

    if bundle.conversation_history:
        lines.append("\n=== CONVERSATION HISTORY (most recent first) ===")
        for turn in reversed(bundle.conversation_history[-8:]):
            role_label = "USER" if turn["role"] == "user" else "COACH"
            lines.append(f"{role_label}: {turn['content'][:400]}")

    lines.append("\n=== CURRENT USER MESSAGE ===")
    lines.append(bundle.user_message)

    return "\n".join(lines)


def _validate_llm_output(parsed: dict) -> CoachResponse:
    """Validate and coerce LLM JSON output into a CoachResponse."""
    steps_raw = parsed.get("actionable_steps", [])
    steps = []
    for s in steps_raw:
        if isinstance(s, dict):
            steps.append(ActionableStep(
                step=str(s.get("step", "")),
                timeframe=str(s.get("timeframe", "soon")),
                priority=str(s.get("priority", "medium")),
            ))

    coaching_type_str = parsed.get("coaching_type", "ad_hoc")
    try:
        coaching_type = CoachingType(coaching_type_str)
    except ValueError:
        coaching_type = CoachingType.AD_HOC

    return CoachResponse(
        response=str(parsed.get("response", "No response generated.")),
        coaching_type=coaching_type,
        confidence=float(parsed.get("confidence", 0.7)),
        follow_up_suggestions=list(parsed.get("follow_up_suggestions", [])),
        timeline_concern=bool(parsed.get("timeline_concern", False)),
        timeline_note=parsed.get("timeline_note"),
        actionable_steps=steps,
        assumptions=list(parsed.get("assumptions", [])),
    )


def _fallback_response(bundle: CoachContextBundle) -> CoachResponse:
    """Deterministic fallback when the LLM call fails entirely."""
    context_note = (
        "grounded in your roadmap" if bundle.has_plan
        else "based on your current profile"
    )
    response = (
        f"I wasn't able to generate a detailed coaching response right now — "
        f"please try again in a moment.\n\n"
        f"In the meantime, your question was: **{bundle.user_message[:200]}**\n\n"
        f"I'll provide a full answer {context_note} as soon as the service recovers."
    )
    return CoachResponse(
        response=response,
        coaching_type=CoachingType.AD_HOC,
        confidence=0.1,
        follow_up_suggestions=["Can you try your question again?"],
        assumptions=["LLM service temporarily unavailable — response is a fallback."],
    )
