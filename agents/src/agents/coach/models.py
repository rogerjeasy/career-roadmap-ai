"""Coach agent data models.

Internal Pydantic models for coach input/output. Not imported outside the
coach package — callers interact via AgentResult.output (plain dict).
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CoachingType(str, Enum):
    AD_HOC = "ad_hoc"
    INTERVIEW_PREP = "interview_prep"
    TIMELINE_CHECK = "timeline_check"
    PROGRESS_NUDGE = "progress_nudge"
    GOAL_CLARIFICATION = "goal_clarification"
    SKILL_GUIDANCE = "skill_guidance"


class ActionableStep(BaseModel):
    step: str
    timeframe: str  # e.g. "this week", "next 2 weeks", "month 1"
    priority: str = Field(default="medium")  # high | medium | low


class CoachResponse(BaseModel):
    """Structured output from one coach agent invocation."""

    response: str = Field(description="Main coaching narrative (markdown)")
    coaching_type: CoachingType = Field(default=CoachingType.AD_HOC)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="2-3 proactive questions the user might want to ask next",
    )
    timeline_concern: bool = Field(
        default=False,
        description="True when user's stated timeline appears unrealistic",
    )
    timeline_note: str | None = Field(
        default=None,
        description="Constructive pushback message when timeline_concern is True",
    )
    actionable_steps: list[ActionableStep] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Key assumptions the coach made when data was incomplete",
    )


class CoachContextBundle(BaseModel):
    """Assembled context passed to the LLM prompt builder."""

    user_message: str
    current_role: str | None = None
    target_role: str | None = None
    skills: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    timeline_months: int | None = None
    weekly_hours: int | None = None
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    roadmap_summary: str | None = None
    gap_summary: str | None = None
    market_summary: str | None = None
    progress_summary: str | None = None
    has_plan: bool = False
