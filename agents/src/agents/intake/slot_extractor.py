"""SlotExtractor — NER-based slot filling for the Intake agent.

Extracts structured career-profile fields from a user's free-text message
using a single LLM call with a strict JSON output schema. Falls back to an
empty extraction result (not an error) when the text yields nothing parseable.

Design:
- Stateless: holds only the (shared) LLM client; all context flows through args.
- Observable: every call opens an OTel span and updates Prometheus counters.
- Resilient: retries LLM calls up to 3 times with exponential back-off.
- Testable: inject a mock LLM via the constructor to avoid real API calls.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import (
    INTAKE_SLOT_EXTRACTION_DURATION,
    INTAKE_SLOTS_EXTRACTED_TOTAL,
    get_tracer,
)
from agents.intake.models import ExtractedSlot, SlotExtractionResult

logger = get_logger(__name__)
_tracer = get_tracer("agents.intake.slot_extractor")

# ── Canonical slot catalogue ────────────────────────────────────────────────
# Ordered by downstream importance; the order appears verbatim in the prompt.

_SLOTS: dict[str, str] = {
    "target_role":            "The job title or role the user wants to reach (string)",
    "current_role":           "The user's current job title or position (string)",
    "skills":                 "Technical and soft skills the user already has (array of strings)",
    "goals":                  "Career objectives beyond the target role (array of strings)",
    "constraints":            "Limitations such as budget, visa, geography, or time (array of strings)",
    "location":               "City / country where the user is based or wants to work (string)",
    "timeline_months":        "Desired transition duration in months — convert '1 year' → 12 (integer)",
    "weekly_hours_available": "Hours per week the user can dedicate to learning (integer)",
    "salary_goal":            "Target annual salary; strip currency symbols and commas (integer)",
}

# Template uses .format(slot_descriptions=...) — double braces are literal JSON braces.
_SYSTEM_PROMPT = """\
You are a Named-Entity Recognition (NER) system for career-transition data.
Extract structured career-profile fields from the user's message via slot-filling.

Available slots (name → expected type / description):
{slot_descriptions}

Rules:
- Extract ONLY information explicitly stated or very clearly implied in the text.
- Do NOT infer, assume, or hallucinate values that are not present.
- confidence: 1.0 = literal match; 0.7 – 0.9 = clear implication; omit slot if < 0.7.
- source_span: copy the exact substring of the user text that yielded this slot.
- skills / goals / constraints: return as JSON arrays; split comma- or semicolon-separated lists.
- timeline_months: integer only — convert "two years" → 24, "six months" → 6.
- weekly_hours_available, salary_goal: integer only — strip currency symbols.
- unresolved_mentions: short phrases about career that you could NOT map to any slot above.
- overall_confidence: float 0.0 – 1.0 reflecting extraction quality overall.

Respond with ONLY valid JSON (no markdown fences, no prose):
{{"slots": [{{"field_name": "...", "value": ..., "confidence": 0.0, "source_span": "..."}}], \
"unresolved_mentions": [], "overall_confidence": 0.0}}
"""


class SlotExtractor:
    """Extracts structured career-profile slots from free-text messages via NER + LLM.

    Inject a custom ``llm`` in tests to avoid real Anthropic API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.clarification_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=1024,
            temperature=0.0,  # deterministic extraction
        )
        self._slot_descriptions = "\n".join(
            f"  {name}: {desc}" for name, desc in _SLOTS.items()
        )

    async def extract(
        self,
        text: str,
        *,
        correlation_id: str = "",
    ) -> SlotExtractionResult:
        """Run NER slot-filling on ``text``.

        Returns an empty ``SlotExtractionResult`` (not an error) when the text
        contains no extractable career information or when the LLM call fails
        after all retry attempts.
        """
        if not text.strip():
            return SlotExtractionResult(raw_text=text)

        with _tracer.start_as_current_span("intake.slot_extraction") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("text_length", len(text))
            t0 = time.monotonic()

            try:
                raw = await self._call_llm(text)
                result = _parse_llm_output(raw, text)

                duration = time.monotonic() - t0
                INTAKE_SLOT_EXTRACTION_DURATION.observe(duration)
                INTAKE_SLOTS_EXTRACTED_TOTAL.labels(status="success").inc()

                span.set_attribute("slots_extracted", len(result.slots))
                span.set_attribute("overall_confidence", result.overall_confidence)
                span.set_attribute("duration_ms", int(duration * 1000))
                span.set_status(Status(StatusCode.OK))

                logger.info(
                    "intake.slots_extracted",
                    count=len(result.slots),
                    fields=[s.field_name for s in result.slots],
                    overall_confidence=result.overall_confidence,
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return result

            except Exception as exc:
                duration = time.monotonic() - t0
                INTAKE_SLOT_EXTRACTION_DURATION.observe(duration)
                INTAKE_SLOTS_EXTRACTED_TOTAL.labels(status="fallback").inc()

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

                logger.warning(
                    "intake.slot_extraction_failed",
                    error=str(exc),
                    duration_ms=int(duration * 1000),
                    correlation_id=correlation_id,
                )
                return SlotExtractionResult(raw_text=text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _call_llm(self, text: str) -> dict[str, Any]:
        response = await self._llm.ainvoke(
            [
                SystemMessage(
                    content=_SYSTEM_PROMPT.format(
                        slot_descriptions=self._slot_descriptions
                    )
                ),
                HumanMessage(content=text),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object, got {type(raw).__name__}")
        return raw


# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_llm_output(raw: dict[str, Any], original_text: str) -> SlotExtractionResult:
    """Convert raw LLM JSON into a typed ``SlotExtractionResult``."""
    slots: list[ExtractedSlot] = []

    for item in raw.get("slots", []):
        try:
            field_name = str(item["field_name"])
            if field_name not in _SLOTS:
                continue
            confidence = float(item.get("confidence", 0.0))
            if confidence < 0.7:
                continue
            value = _coerce(field_name, item["value"])
            if value is None:
                continue
            slots.append(
                ExtractedSlot(
                    field_name=field_name,
                    value=value,
                    confidence=confidence,
                    source_span=str(item.get("source_span", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            pass  # skip malformed slot entries without crashing

    return SlotExtractionResult(
        raw_text=original_text,
        slots=slots,
        unresolved_mentions=[str(m) for m in raw.get("unresolved_mentions", []) if m],
        overall_confidence=float(raw.get("overall_confidence", 0.0)),
    )


def _coerce(field_name: str, value: Any) -> Any:
    """Type-coerce a raw LLM slot value to the expected Python type."""
    if value is None:
        return None

    if field_name in ("target_role", "current_role", "location"):
        s = str(value).strip()
        return s if s else None

    if field_name in ("skills", "goals", "constraints"):
        if isinstance(value, list):
            items = [str(v).strip() for v in value if str(v).strip()]
        elif isinstance(value, str):
            items = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
        else:
            return None
        return items if items else None

    if field_name in ("timeline_months", "weekly_hours_available", "salary_goal"):
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        if isinstance(value, str):
            digits = "".join(c for c in value if c.isdigit())
            return int(digits) if digits else None
        return None

    return None
