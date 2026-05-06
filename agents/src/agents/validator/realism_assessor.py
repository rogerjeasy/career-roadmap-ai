"""RealismAssessor — Stage 3: timeline and workload feasibility check.

Two-pass assessment:
  Pass A (deterministic): compare total roadmap duration vs user's declared
          timeline and check per-phase hour budgets. Runs before any LLM call
          and can produce issues independently of LLM availability.
  Pass B (LLM): evaluate skill complexity, phase ordering, and weekly
          commitment plausibility for each phase with nuanced reasoning.

Returns (list[RealismIssue], realism_score: float).

Design:
- Stateless: all state passed as arguments.
- Pass A runs first and caps the LLM score on critical failures.
- Fallback: LLM failure falls back to Pass-A result only; score is estimated
  from deterministic checks so the pipeline keeps moving.
"""
from __future__ import annotations

import json
import time
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
from agents.core.logging import get_logger
from agents.core.observability import (
    VALIDATOR_REALISM_SCORE,
    VALIDATOR_STAGE_DURATION,
    get_tracer,
)
from agents.validator.models import FixPriority, RealismIssue

logger = get_logger(__name__)
_tracer = get_tracer("agents.validator.realism_assessor")

# If total roadmap duration exceeds user timeline by more than this fraction → flag.
_TIMELINE_OVERSHOOT_THRESHOLD = 0.20  # 20 % over budget → HIGH issue
_TIMELINE_CRITICAL_THRESHOLD = 0.50   # 50 % over budget → CRITICAL issue

# Rough heuristic: each new skill needs at least this many focused hours.
_MIN_HOURS_PER_SKILL = 8

_SYSTEM = """\
You are a career coaching expert evaluating the feasibility of an AI-generated
career roadmap for a specific user.

You will receive:
  A) phases — list of roadmap phases with skills, milestones, and durations
  B) user_constraints — timeline_months, weekly_hours_available, current_role, skills

For each phase and for the roadmap overall, identify realism issues:
  - Phases that require mastery of a fundamentally new discipline in too few weeks
  - Weekly hour estimates that exceed the user's declared availability
  - Missing prerequisite knowledge assumed at the start of a phase
  - Overly optimistic milestone requirements for the available time

Severity guide:
  critical — roadmap cannot succeed as-is; requires major restructuring
  high     — one phase is significantly infeasible; users will likely stall
  low      — minor optimism; motivated users can still succeed with effort

Reply with ONLY a JSON object — no prose, no markdown:
{
  "realism_score": 0.75,
  "issues": [
    {
      "description": "concise description of the issue",
      "phase_index": 2,
      "severity": "high",
      "suggested_adjustment": "one specific, actionable change"
    }
  ]
}
Set phase_index to null for whole-roadmap issues.
Return "issues": [] if the roadmap is realistic.
"""


class RealismAssessor:
    """Stage 3: timeline and workload realism check.

    Parameters
    ----------
    llm:
        Override the default LLM instance (primarily for testing).
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.validator_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
            temperature=0.0,
        )

    async def assess(
        self,
        roadmap: dict[str, Any],
        user_profile: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> tuple[list[RealismIssue], float]:
        """Assess timeline and workload realism.

        Returns
        -------
        tuple[list[RealismIssue], float]
            (issues, realism_score 0.0–1.0)
        """
        phases = roadmap.get("phases", [])

        with _tracer.start_as_current_span("realism_assessor.assess") as span:
            t0 = time.monotonic()
            issues: list[RealismIssue] = []

            # Pass A: deterministic pre-check (no LLM required)
            det_issues = _deterministic_check(phases, user_profile)
            issues.extend(det_issues)

            # Pass B: LLM nuanced assessment
            try:
                raw = await self._llm_assess(phases, user_profile)
                score = max(0.0, min(1.0, float(raw.get("realism_score", 1.0))))
                llm_issues = [
                    RealismIssue(
                        description=str(i.get("description", "")),
                        phase_index=(
                            int(i["phase_index"])
                            if i.get("phase_index") is not None
                            else None
                        ),
                        severity=_parse_priority(i.get("severity", "low")),
                        suggested_adjustment=str(i.get("suggested_adjustment", "")),
                    )
                    for i in raw.get("issues", [])
                ]
                issues.extend(llm_issues)

                # Deterministic issues cap the LLM score to prevent false positives
                # from masking structural problems caught by heuristics.
                if any(i.severity == FixPriority.CRITICAL for i in det_issues):
                    score = min(score, 0.3)
                elif det_issues:
                    score = min(score, 0.6)

                VALIDATOR_REALISM_SCORE.observe(score)
                span.set_attribute("realism_score", score)
                span.set_attribute("issues_count", len(issues))
                span.set_attribute("deterministic_issues", len(det_issues))
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.warning(
                    "realism_assessor.llm_fallback",
                    error=str(exc),
                    correlation_id=correlation_id,
                )
                # Estimate score from deterministic checks only.
                score = 0.3 if any(
                    i.severity == FixPriority.CRITICAL for i in det_issues
                ) else (0.5 if det_issues else 0.8)
                VALIDATOR_REALISM_SCORE.observe(score)
                span.set_attribute("realism_score", score)
                span.set_attribute("issues_count", len(issues))
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            finally:
                VALIDATOR_STAGE_DURATION.labels(stage="realism").observe(
                    time.monotonic() - t0
                )
            return issues, score

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _llm_assess(
        self, phases: list[dict], user_profile: dict[str, Any]
    ) -> dict[str, Any]:
        content = json.dumps(
            {
                "phases": phases,
                "user_constraints": {
                    "timeline_months": user_profile.get("timeline_months"),
                    "weekly_hours_available": user_profile.get("weekly_hours_available"),
                    "current_role": user_profile.get("current_role"),
                    "skills": user_profile.get("skills", []),
                },
            },
            indent=2,
        )
        response = await self._llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=content)]
        )
        result = json.loads(str(response.content))
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict, got {type(result).__name__}")
        return result


# ── Deterministic helpers ──────────────────────────────────────────────────────


def _deterministic_check(
    phases: list[dict], user_profile: dict[str, Any]
) -> list[RealismIssue]:
    """Heuristic checks that do not require an LLM call."""
    issues: list[RealismIssue] = []
    timeline_months = user_profile.get("timeline_months")
    weekly_hours = user_profile.get("weekly_hours_available")

    # 1. Total duration vs declared timeline
    total_weeks = sum(int(p.get("duration_weeks", 0)) for p in phases)
    if timeline_months and total_weeks > 0:
        roadmap_months = total_weeks / 4.33
        overshoot = roadmap_months / timeline_months - 1.0
        if overshoot > _TIMELINE_CRITICAL_THRESHOLD:
            issues.append(
                RealismIssue(
                    description=(
                        f"Total roadmap duration ({roadmap_months:.1f} months) "
                        f"exceeds user timeline ({timeline_months} months) by "
                        f"{overshoot * 100:.0f}%."
                    ),
                    phase_index=None,
                    severity=FixPriority.CRITICAL,
                    suggested_adjustment=(
                        f"Reduce total roadmap to ≤ {timeline_months} months by "
                        "trimming phases, removing optional skills, or parallelising "
                        "skill acquisition across phases."
                    ),
                )
            )
        elif overshoot > _TIMELINE_OVERSHOOT_THRESHOLD:
            issues.append(
                RealismIssue(
                    description=(
                        f"Total roadmap duration ({roadmap_months:.1f} months) "
                        f"slightly exceeds user timeline ({timeline_months} months)."
                    ),
                    phase_index=None,
                    severity=FixPriority.HIGH,
                    suggested_adjustment=(
                        f"Trim ~{(roadmap_months - timeline_months) * 4.33:.0f} weeks "
                        "from the lowest-priority phases."
                    ),
                )
            )

    # 2. Per-phase skill load vs available hours
    if weekly_hours and weekly_hours > 0:
        for i, phase in enumerate(phases):
            phase_weeks = int(phase.get("duration_weeks", 0))
            skill_count = len(
                phase.get("skills_to_acquire", []) + phase.get("skills_to_gain", [])
            )
            if phase_weeks > 0 and skill_count > 0:
                hours_available = phase_weeks * weekly_hours
                min_hours_needed = skill_count * _MIN_HOURS_PER_SKILL
                if hours_available < min_hours_needed:
                    issues.append(
                        RealismIssue(
                            description=(
                                f"Phase {i + 1} targets {skill_count} skills in "
                                f"{phase_weeks} weeks ({hours_available:.0f}h available, "
                                f"~{min_hours_needed}h estimated)."
                            ),
                            phase_index=i,
                            severity=FixPriority.HIGH,
                            suggested_adjustment=(
                                f"Extend Phase {i + 1} to "
                                f"{int(min_hours_needed / weekly_hours) + 1} weeks or "
                                "reduce skill count to fit the available hours."
                            ),
                        )
                    )

    return issues


def _parse_priority(value: str) -> FixPriority:
    try:
        return FixPriority(value.lower())
    except ValueError:
        return FixPriority.LOW
