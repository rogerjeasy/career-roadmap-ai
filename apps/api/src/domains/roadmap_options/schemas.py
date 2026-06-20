"""Roadmap Strategy Options domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StrategyType = Literal["aggressive", "balanced", "long_term"]

_VALID = ("aggressive", "balanced", "long_term")


class StrategyPhase(BaseModel):
    title: str
    duration_weeks: int = 0
    focus: str = ""


class RoadmapStrategyOption(BaseModel):
    id: str
    strategy: StrategyType
    title: str
    timeline_months: int
    weekly_hours: int
    intensity: str
    summary: str
    phases: list[StrategyPhase] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    best_for: str = ""
    selected: bool = False

    @classmethod
    def from_doc(cls, doc: dict[str, Any], selected_strategy: str | None) -> "RoadmapStrategyOption":
        strat = doc.get("strategy", "balanced")
        strat = strat if strat in _VALID else "balanced"
        return cls(
            id=doc.get("id", ""),
            strategy=strat,
            title=doc.get("title", ""),
            timeline_months=int(doc.get("timeline_months", 0) or 0),
            weekly_hours=int(doc.get("weekly_hours", 0) or 0),
            intensity=doc.get("intensity", ""),
            summary=doc.get("summary", ""),
            phases=[
                StrategyPhase(
                    title=str(p.get("title", "")),
                    duration_weeks=int(p.get("duration_weeks", 0) or 0),
                    focus=str(p.get("focus", "")),
                )
                for p in (doc.get("phases") or [])
                if isinstance(p, dict)
            ],
            tradeoffs=list(doc.get("tradeoffs", []) or []),
            risks=list(doc.get("risks", []) or []),
            best_for=doc.get("best_for", ""),
            selected=strat == selected_strategy,
        )


class RoadmapOptionsSet(BaseModel):
    has_data: bool = True
    based_on: str = ""
    options: list[RoadmapStrategyOption] = Field(default_factory=list)
    selected_strategy: StrategyType | None = None
    generated_at: datetime | None = None

    @classmethod
    def empty(cls) -> "RoadmapOptionsSet":
        return cls(has_data=False, based_on="", options=[])

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "RoadmapOptionsSet":
        selected = doc.get("selected_strategy")
        options = [
            RoadmapStrategyOption.from_doc(o, selected)
            for o in (doc.get("options") or [])
            if isinstance(o, dict)
        ]
        return cls(
            has_data=bool(options),
            based_on=doc.get("based_on", ""),
            options=options,
            selected_strategy=selected if selected in _VALID else None,
            generated_at=doc.get("generated_at"),
        )


class SelectStrategyInput(BaseModel):
    strategy: StrategyType
