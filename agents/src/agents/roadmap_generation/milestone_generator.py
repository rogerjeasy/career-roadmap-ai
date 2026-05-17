"""MilestoneGenerator — LLM: create one measurable milestone per learning phase.

Falls back to a heuristic milestone per phase when the LLM call fails.
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

    Inject a custom ``llm`` in tests to avoid real API calls.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.roadmap_milestone_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=3072,
            temperature=0.1,
        )

    async def generate(
        self,
        phases: list[Phase],
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> list[Milestone]:
        """Return LLM-generated milestones. Falls back to one heuristic per phase."""
        with _tracer.start_as_current_span("roadmap.milestone_generation") as span:
            span.set_attribute("phase_count", len(phases))
            span.set_attribute("target_role", target_role)
            span.set_attribute("correlation_id", correlation_id)
            t0 = time.monotonic()

            try:
                milestones = await self._generate_with_llm(phases, target_role, correlation_id)
                ROADMAP_MILESTONE_GEN_TOTAL.labels(status="llm").inc()
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                logger.warning(
                    "roadmap.milestone_gen_llm_failed",
                    error=str(exc),
                    fallback="heuristic",
                    correlation_id=correlation_id,
                )
                milestones = _fallback_milestones(phases)
                ROADMAP_MILESTONE_GEN_TOTAL.labels(status="fallback").inc()

            ROADMAP_MILESTONE_GEN_DURATION.observe(time.monotonic() - t0)
            logger.info(
                "roadmap.milestones_generated",
                milestone_count=len(milestones),
                target_role=target_role,
                correlation_id=correlation_id,
            )
            return milestones

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _generate_with_llm(
        self,
        phases: list[Phase],
        target_role: str,
        correlation_id: str,
    ) -> list[Milestone]:
        user_content = _build_user_prompt(phases, target_role)
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        raw = json.loads(str(response.content))
        if not isinstance(raw, dict) or "milestones" not in raw:
            raise ValueError("LLM response missing 'milestones' key")
        return [_parse_milestone(m) for m in raw["milestones"]]


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


_PHASE_ICONS = ["🏗️", "🚀", "🏆", "🌟", "🎓"]


def _fallback_milestones(phases: list[Phase]) -> list[Milestone]:
    """One heuristic milestone per phase."""
    milestones: list[Milestone] = []
    cumulative = 0
    for phase in phases:
        cumulative += phase.duration_weeks
        skills = phase.skills_to_acquire[:3]
        icon = _PHASE_ICONS[(phase.index - 1) % len(_PHASE_ICONS)]
        milestones.append(
            Milestone(
                name=f"{phase.title} Checkpoint",
                description=f"Demonstrate core competencies acquired during {phase.title}.",
                phase_index=phase.index,
                week_number=cumulative,
                icon=icon,
                success_criteria=[
                    f"Complete a project demonstrating {skills[0] if skills else 'core skills'}",
                    "Push working, documented code to a public repository",
                    "Write a README that explains the project purpose and how to run it",
                ],
                skills_demonstrated=skills,
                deliverable="Public repository with documented portfolio project",
            )
        )
    return milestones
