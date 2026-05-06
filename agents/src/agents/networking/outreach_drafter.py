"""OutreachDrafter — generate targeted, authentic outreach message drafts via LLM.

Generates three distinct drafts per run:
  - Mentor:            reaching out to a senior practitioner for guidance
  - Peer:              connecting with someone in a similar career transition
  - Community leader:  introducing oneself in a relevant online community

Each draft targets a specific skill gap and includes a concrete, single call-to-action.
Falls back to pre-written template drafts when all LLM retries fail.
"""
from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import Status, StatusCode
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import (
    NET_OUTREACH_DRAFT_DURATION,
    NET_OUTREACH_DRAFT_TOTAL,
    get_tracer,
)
from agents.networking.models import OutreachDraft, OutreachTone, RecipientType

logger = get_logger(__name__)
_tracer = get_tracer("agents.networking.outreach_drafter")

_DEFAULT_MAX_DRAFTS = 3

_SYSTEM_PROMPT = """\
You are an expert career coach who writes personalized, effective outreach messages.
Your messages are authentic, specific, and respect the recipient's time. They never sound
like copy-paste templates.

Given a career context, generate outreach message drafts. Return ONLY valid JSON array (no fences):
[
  {
    "recipient_type": "mentor|peer|hiring_manager|community_leader|open_source_maintainer",
    "subject": "<LinkedIn message title or email subject — specific, not generic>",
    "body": "<3-5 sentence message — warm, specific, respects recipient's time>",
    "tone": "professional|friendly|concise",
    "platform": "LinkedIn|Email|Discord/Slack",
    "target_skill": "<skill gap or area this outreach addresses>",
    "call_to_action": "<one specific ask — 20-min call, code review intro, community join, etc.>",
    "estimated_response_rate": "high|medium|low"
  }
]

Drafting guidelines:
- Write exactly 3 drafts: (1) senior mentor, (2) peer in similar transition, (3) community intro
- Body must be 3-5 sentences — brevity gets responses
- Subject line must be specific and intriguing (not "Coffee Chat?" or "Quick Question")
- Use [THEIR_PROJECT] or [THEIR_ARTICLE] placeholder when referencing something specific
- Use [YOUR_NAME] as sender placeholder
- Call-to-action: ONE specific, time-bounded ask (not multiple asks or vague "let's chat")
- estimated_response_rate: "high" = brief ask + highly specific, "medium" = normal cold outreach,
  "low" = long or generic
- Never fabricate credentials or overstate the user's background
"""


class OutreachDrafter:
    """Draft personalized outreach messages targeting a specific skill gap.

    Inject a custom ``llm`` in tests to bypass real API calls.
    """

    def __init__(
        self,
        llm: ChatAnthropic | None = None,
        max_drafts: int = _DEFAULT_MAX_DRAFTS,
    ) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.networking_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=3000,
            temperature=0.3,
        )
        self._max_drafts = max_drafts

    async def draft(
        self,
        target_role: str,
        current_role: str | None,
        top_skill_gap: str,
        background_summary: str,
        *,
        correlation_id: str = "",
    ) -> list[OutreachDraft]:
        """Generate outreach drafts for the top skill gap.

        Falls back to pre-written template drafts when all LLM retries fail.
        """
        with _tracer.start_as_current_span("networking.outreach_draft") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("target_role", target_role)
            span.set_attribute("top_skill_gap", top_skill_gap)
            t0 = time.monotonic()

            try:
                drafts = await self._draft_with_llm(
                    target_role, current_role, top_skill_gap, background_summary, correlation_id
                )
                NET_OUTREACH_DRAFT_TOTAL.labels(status="llm").inc()
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "networking.outreach_draft_llm_failed",
                    error=str(exc),
                    fallback="template",
                    correlation_id=correlation_id,
                )
                drafts = _template_drafts(target_role, top_skill_gap)
                NET_OUTREACH_DRAFT_TOTAL.labels(status="fallback").inc()

            duration = time.monotonic() - t0
            NET_OUTREACH_DRAFT_DURATION.observe(duration)
            drafts = drafts[: self._max_drafts]
            span.set_attribute("draft_count", len(drafts))
            span.set_attribute("duration_ms", int(duration * 1000))
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "networking.outreach_drafted",
                target_role=target_role,
                top_skill_gap=top_skill_gap,
                draft_count=len(drafts),
                duration_ms=int(duration * 1000),
                correlation_id=correlation_id,
            )
            return drafts

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _draft_with_llm(
        self,
        target_role: str,
        current_role: str | None,
        top_skill_gap: str,
        background_summary: str,
        correlation_id: str,
    ) -> list[OutreachDraft]:
        context = (
            f"Target role: {target_role}\n"
            f"Current role: {current_role or 'Not specified'}\n"
            f"Priority skill to build: {top_skill_gap}\n"
            f"Background: {background_summary}\n\n"
            "Generate 3 outreach drafts to help build connections and bridge the skill gap."
        )
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=context),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, list):
            raise ValueError(f"Expected JSON array, got {type(raw).__name__}")
        return [_build_draft(item, top_skill_gap) for item in raw if isinstance(item, dict)]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_draft(raw: dict[str, Any], fallback_skill: str) -> OutreachDraft:
    try:
        recipient_type = RecipientType(raw.get("recipient_type", "mentor"))
    except ValueError:
        recipient_type = RecipientType.MENTOR

    try:
        tone = OutreachTone(raw.get("tone", "professional"))
    except ValueError:
        tone = OutreachTone.PROFESSIONAL

    return OutreachDraft(
        draft_id=str(uuid4()),
        recipient_type=recipient_type,
        subject=str(raw.get("subject", "Career conversation request")),
        body=str(raw.get("body", "")),
        tone=tone,
        platform=str(raw.get("platform", "LinkedIn")),
        target_skill=str(raw.get("target_skill", fallback_skill)),
        call_to_action=str(raw.get("call_to_action", "15-minute virtual coffee chat")),
        estimated_response_rate=str(raw.get("estimated_response_rate", "medium")),
    )


def _template_drafts(target_role: str, top_skill_gap: str) -> list[OutreachDraft]:
    """Pre-written fallback drafts used when LLM is unavailable."""
    return [
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.MENTOR,
            subject=f"Building {top_skill_gap} skills — 20 min of your insight?",
            body=(
                f"Hi [NAME], I came across your work on [THEIR_PROJECT] and was genuinely impressed. "
                f"I'm actively transitioning toward a {target_role} role and {top_skill_gap} is my "
                f"current priority gap. Would you be open to a 20-minute call to share what you "
                f"wish you'd known when building those skills? I've already [MENTION_ONE_THING_DONE] "
                f"— just want to make sure I'm on the right track."
            ),
            tone=OutreachTone.FRIENDLY,
            platform="LinkedIn",
            target_skill=top_skill_gap,
            call_to_action="20-minute call to share your learning path for this skill",
            estimated_response_rate="medium",
        ),
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.PEER,
            subject=f"Both targeting {target_role} — want to exchange notes?",
            body=(
                f"Hi [NAME], I noticed we're both working toward {target_role} roles. "
                f"I'm currently focused on {top_skill_gap} and it looks like you've been "
                f"doing similar work. Would love to exchange resources and compare notes — "
                f"always better to navigate a transition alongside someone who gets it."
            ),
            tone=OutreachTone.FRIENDLY,
            platform="LinkedIn",
            target_skill=top_skill_gap,
            call_to_action="Connect and share one resource each that's been most useful",
            estimated_response_rate="high",
        ),
        OutreachDraft(
            draft_id=str(uuid4()),
            recipient_type=RecipientType.COMMUNITY_LEADER,
            subject=f"Intro: Backend engineer transitioning to {target_role}",
            body=(
                f"Hi everyone! I'm [YOUR_NAME], a backend engineer actively transitioning into "
                f"{target_role} roles. Currently building {top_skill_gap} skills and would love "
                f"to learn from this community. Happy to share what I know about [YOUR_CURRENT_SKILLS] "
                f"in return — excited to contribute and grow here."
            ),
            tone=OutreachTone.FRIENDLY,
            platform="Discord/Slack",
            target_skill=top_skill_gap,
            call_to_action="Introduce yourself and ask one specific question to the community",
            estimated_response_rate="high",
        ),
    ]
