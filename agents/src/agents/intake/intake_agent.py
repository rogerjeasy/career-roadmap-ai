"""IntakeAgent — L3 Specialist Agent: discovery interview & profile building.

Responsibility:
  1. Run NER slot-filling on the user's latest message (SlotExtractor).
  2. Merge extracted slots onto the existing UserProfileSnapshot (ProfileBuilder).
  3. Assess profile completeness and identify missing slots.
  4. Return the enriched UserProfile JSON + metadata in AgentResult.output.

The agent never writes to Redis or Firestore directly — it returns its output
in the AgentResult envelope and lets the Orchestrator decide what to persist.
The Synthesizer node reads intake output via plan_snapshot["intake"] and can
forward the enriched profile to the session layer.

Observable: OTel span wraps the full _execute(); STEP_PROGRESS SSE events are
emitted at each pipeline step so the client shows live progress.

Low-coupled: SlotExtractor and ProfileBuilder are injected (constructor DI),
making the agent fully testable without real LLM or Redis connections.

Registration (at Celery worker startup):
    from redis import Redis
    from agents.bus.publisher import EventPublisher
    from agents.intake import IntakeAgent
    from agents.core.agent_registry import registry

    registry.register(IntakeAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import STEP_PROGRESS_TOTAL, get_tracer
from agents.intake.models import ProfileDiff, SlotExtractionResult
from agents.intake.profile_builder import ProfileBuilder, missing_slots
from agents.intake.slot_extractor import SlotExtractor

logger = get_logger(__name__)
_tracer = get_tracer("agents.intake.intake_agent")

# Profile completeness threshold below which we flag needs_clarification.
_CLARIFICATION_THRESHOLD = 0.75


class IntakeAgent(BaseAgent):
    """Conducts a structured discovery interview and builds UserProfile JSON.

    Parameters
    ----------
    slot_extractor:
        NER/slot-filling component. Defaults to ``SlotExtractor()``.
    profile_builder:
        Profile merge component. Defaults to ``ProfileBuilder()``.
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events. When ``None``
        (e.g. in unit tests without Redis), progress events are silently skipped.
    llm:
        Override the LangChain LLM client forwarded to SlotExtractor when
        ``slot_extractor`` is not explicitly provided.
    """

    def __init__(
        self,
        *,
        slot_extractor: SlotExtractor | None = None,
        profile_builder: ProfileBuilder | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._slot_extractor = slot_extractor or SlotExtractor(llm=llm)
        self._profile_builder = profile_builder or ProfileBuilder()
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.INTAKE

    @property
    def display_name(self) -> str:
        return "Intake & Profile Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full intake pipeline and return the enriched profile output."""
        with _tracer.start_as_current_span("intake.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)
            span.set_attribute("has_user_message", bool(context.user_message))

            # ── Step 1: NER slot extraction ─────────────────────────────
            self._emit_progress(context, "slot_extraction", "Analysing your message…")
            STEP_PROGRESS_TOTAL.labels(step_name="intake.slot_extraction").inc()

            extraction: SlotExtractionResult = await self._slot_extractor.extract(
                context.user_message,
                correlation_id=context.correlation_id,
            )

            span.set_attribute("slots_extracted", len(extraction.slots))

            # ── Step 2: Profile merge ───────────────────────────────────
            self._emit_progress(context, "profile_build", "Building your profile…")
            STEP_PROGRESS_TOTAL.labels(step_name="intake.profile_build").inc()

            updated_profile, diff = self._profile_builder.build(
                context.user_profile,
                extraction,
                correlation_id=context.correlation_id,
            )

            # ── Step 3: Completeness assessment ─────────────────────────
            self._emit_progress(
                context, "completeness_check", "Assessing profile completeness…"
            )
            STEP_PROGRESS_TOTAL.labels(step_name="intake.completeness_check").inc()

            missing = missing_slots(updated_profile)
            needs_clarification = (
                diff.new_completeness < _CLARIFICATION_THRESHOLD and bool(missing)
            )

            span.set_attribute("completeness_score", diff.new_completeness)
            span.set_attribute("missing_count", len(missing))
            span.set_attribute("needs_clarification", needs_clarification)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "intake.completed",
                completeness=diff.new_completeness,
                added=diff.added_fields,
                updated=diff.updated_fields,
                missing=missing,
                needs_clarification=needs_clarification,
                correlation_id=context.correlation_id,
            )

            return {
                "user_profile": updated_profile.model_dump(),
                "completeness_score": diff.new_completeness,
                "missing_slots": missing,
                "needs_clarification": needs_clarification,
                "extracted_slots": [
                    {
                        "field_name": s.field_name,
                        "value": s.value,
                        "confidence": s.confidence,
                        "source_span": s.source_span,
                    }
                    for s in extraction.slots
                ],
                "unresolved_mentions": extraction.unresolved_mentions,
                "diff": {
                    "added": diff.added_fields,
                    "updated": diff.updated_fields,
                    "old_completeness": diff.old_completeness,
                    "new_completeness": diff.new_completeness,
                },
            }

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(
        self, context: AgentContext, step: str, description: str
    ) -> None:
        """Best-effort STEP_PROGRESS event emission. Never raises."""
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
            logger.warning(
                "intake.progress_emit_failed",
                step=step,
                error=str(exc),
            )
