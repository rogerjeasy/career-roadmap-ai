"""MilestoneGenerator — LLM: create one measurable milestone per learning phase.

Provider cascade: Claude (primary) → OpenAI (secondary) → DeepSeek (tertiary).
If every provider fails, a RuntimeError is raised — no generic milestones are substituted,
because hardcoded milestone descriptions would be meaningless outside the user's actual domain.
"""
from __future__ import annotations

import json
import time
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.core.llm_provider import llm_generate
from agents.core.logging import get_logger
from agents.core.observability import (
    ROADMAP_MILESTONE_GEN_DURATION,
    ROADMAP_MILESTONE_GEN_TOTAL,
    get_tracer,
)
from agents.roadmap_generation.models import Milestone, Phase

logger = get_logger(__name__)
_tracer = get_tracer("agents.roadmap_generation.milestone_generator")

_SYSTEM_PROMPT = """\
You are an expert learning milestone designer. Given a set of learning phases, create
concrete, measurable milestones that mark the successful completion of each phase.

OUTPUT — valid JSON only (no code fences, no markdown):
{
  "milestones": [
    {
      "name": "Short achievement-style name",
      "description": "What achieving this proves about the learner",
      "phase_index": 1,
      "week_number": 6,
      "icon": "🚀",
      "success_criteria": [
        "Build X that does Y and handles Z",
        "Score ≥ 80% on an objective assessment for skill A",
        "Receive code review feedback and iterate at least once"
      ],
      "skills_demonstrated": ["Skill1", "Skill2"],
      "deliverable": "Concrete shareable artifact (GitHub repo, live URL, certificate)"
    }
  ]
}

RULES:
1. Exactly one milestone per phase — milestone count must equal phase count
2. week_number = cumulative end-week of the phase (phase 1 ends at its duration_weeks,
   phase 2 at duration_weeks_1 + duration_weeks_2, and so on)
3. success_criteria must be observable — NOT "understand X" but "build X that does Y"
4. At least 3 success_criteria per milestone
5. deliverable must be a concrete, shareable artifact
6. skills_demonstrated must come from the phase's skills_to_acquire
7. Milestone names should feel like achievements ("Data Engineering Foundations Certified")
8. icon: choose one emoji that best represents the milestone theme — use career-appropriate
   icons such as 🚀 🎯 🏆 💡 🔧 📊 🌟 🎓 💼 🛠️ 📈 🔬 🤝 🎨 ⚡ 🏗️ 🧠 🔑 🌐 ✅
"""


class MilestoneGenerator:
    """Generates measurable milestones for each roadmap phase.

    Uses multi-LLM cascade (Claude → OpenAI → DeepSeek); raises RuntimeError
    if all providers fail — no synthetic milestones substituted.
    """

    async def generate(
        self,
        phases: list[Phase],
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> list[Milestone]:
        """Return LLM-generated milestones. Raises RuntimeError if all providers fail — no synthetic fallback."""
        with _tracer.start_as_current_span("roadmap.milestone_generation") as span:
            span.set_attribute("phase_count", len(phases))
            span.set_attribute("target_role", target_role)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                milestones, provider = await self._generate_with_cascade(
                    phases, target_role, correlation_id
                )
                ROADMAP_MILESTONE_GEN_TOTAL.labels(status=f"llm_{provider}").inc()
                span.set_attribute("llm_provider", provider)
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                ROADMAP_MILESTONE_GEN_TOTAL.labels(status="failed").inc()
                logger.error(
                    "roadmap.milestone_gen_all_providers_failed",
                    target_role=target_role,
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                raise RuntimeError(
                    f"Milestone generation failed for role '{target_role}': "
                    "all AI providers (Claude, OpenAI, DeepSeek) are currently unavailable. "
                    "Please try again in a few minutes."
                ) from exc

            ROADMAP_MILESTONE_GEN_DURATION.observe(time.monotonic() - t0)
            logger.info(
                "roadmap.milestones_generated",
                milestone_count=len(milestones),
                target_role=target_role,
                correlation_id=correlation_id,
            )
            return milestones

    async def _generate_with_cascade(
        self,
        phases: list[Phase],
        target_role: str,
        correlation_id: str,
    ) -> tuple[list[Milestone], str]:
        user_content = _build_user_prompt(phases, target_role)
        raw_content, provider = await llm_generate(
            _SYSTEM_PROMPT,
            user_content,
            max_tokens=3072,
            temperature=0.1,
            primary_model=agent_settings.roadmap_milestone_model,
            label="roadmap.milestone_gen",
        )
        parsed = json.loads(raw_content)
        if not isinstance(parsed, dict) or "milestones" not in parsed:
            raise ValueError(f"LLM response missing 'milestones' key (provider={provider})")
        return [_parse_milestone(m) for m in parsed["milestones"]], provider


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_user_prompt(phases: list[Phase], target_role: str) -> str:
    lines = [f"Target role: {target_role}", f"Number of phases: {len(phases)}", ""]
    cumulative = 0
    for phase in phases:
        cumulative += phase.duration_weeks
        lines.append(f"Phase {phase.index}: {phase.title}")
        lines.append(f"  Duration: {phase.duration_weeks} weeks (ends at week {cumulative})")
        lines.append(f"  Difficulty: {phase.difficulty.value}")
        lines.append(f"  Goals: {'; '.join(phase.goals[:3])}")
        lines.append(f"  Skills: {', '.join(phase.skills_to_acquire[:6])}")
        lines.append(f"  Gaps closed: {', '.join(phase.gaps_addressed[:5])}")
        lines.append("")
    return "\n".join(lines)


def _parse_milestone(raw: dict[str, Any]) -> Milestone:
    return Milestone(
        name=str(raw.get("name", "Phase Milestone")),
        description=str(raw.get("description", "")),
        phase_index=int(raw.get("phase_index", 1)),
        week_number=int(raw.get("week_number", 4)),
        icon=str(raw.get("icon", "🎯")),
        success_criteria=_to_str_list(raw.get("success_criteria", [])),
        skills_demonstrated=_to_str_list(raw.get("skills_demonstrated", [])),
        deliverable=str(raw.get("deliverable", "Portfolio project on GitHub")),
    )


def _to_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    return []
