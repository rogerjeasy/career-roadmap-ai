"""WeeklyPlanner — pure computation: distribute phase content into a weekly schedule.

No I/O, no LLM calls. Deterministic and unit-testable.

Algorithm:
  1. Scale phase durations to sum exactly to timeline_months * 4 weeks
  2. Walk week-by-week; rotate through the phase's skills_to_acquire
  3. Pick task template by position within the phase (intro → build → consolidate)
  4. Attach the phase milestone deliverable to the last week of each phase
  5. Emit a fixed set of core habits plus role-keyed bonus habits
"""
from __future__ import annotations

import dataclasses

from agents.roadmap_generation.models import Habit, Milestone, Phase, WeeklyTask

# ── Weekly task templates ────────────────────────────────────────────────────

_TASK_TEMPLATES: dict[str, list[str]] = {
    "intro": [
        "Set up development environment for {skill}",
        "Complete the official {skill} getting-started guide",
        "Study core concepts and reference documentation",
        "Complete 2–3 beginner exercises to validate understanding",
    ],
    "build": [
        "Build a small project applying {skill} concepts learned so far",
        "Explore advanced features and edge cases of {skill}",
        "Read best-practice articles or community guides for {skill}",
        "Self-review code against a quality checklist",
    ],
    "consolidate": [
        "Complete the phase milestone project using {skill}",
        "Write a README documenting the project and key learnings",
        "Push final code to GitHub and record a short walkthrough",
        "List remaining gaps in {skill} for continued study",
    ],
}

# ── Standard habits ──────────────────────────────────────────────────────────

_CORE_HABITS: list[Habit] = [
    Habit(
        name="Daily coding practice",
        frequency="daily",
        duration_minutes=30,
        rationale="Consistent daily coding builds muscle memory faster than any other single habit.",
        phase_start=1,
    ),
    Habit(
        name="Review learning notes",
        frequency="daily",
        duration_minutes=15,
        rationale="Spaced repetition of notes consolidates long-term retention.",
        phase_start=1,
    ),
    Habit(
        name="Weekly project review",
        frequency="weekly",
        duration_minutes=60,
        rationale="A weekly reflection session maintains momentum and surfaces blockers early.",
        phase_start=1,
    ),
    Habit(
        name="Read tech articles or release notes",
        frequency="daily",
        duration_minutes=15,
        rationale="Staying current with the ecosystem ensures skills remain market-relevant.",
        phase_start=1,
    ),
]

_ROLE_HABITS: dict[str, list[Habit]] = {
    "data": [
        Habit(
            name="Kaggle notebook practice",
            frequency="weekly",
            duration_minutes=90,
            rationale="Real-dataset challenges reinforce ML/data skills better than tutorials alone.",
            phase_start=2,
        )
    ],
    "machine learning": [
        Habit(
            name="Kaggle notebook practice",
            frequency="weekly",
            duration_minutes=90,
            rationale="Hands-on ML challenges build model-building intuition.",
            phase_start=2,
        )
    ],
    "cloud": [
        Habit(
            name="Cloud console exploration",
            frequency="weekly",
            duration_minutes=45,
            rationale="Hands-on console time builds service familiarity faster than theory.",
            phase_start=2,
        )
    ],
    "devops": [
        Habit(
            name="Infrastructure lab exercises",
            frequency="weekly",
            duration_minutes=60,
            rationale="Regular sandbox lab work builds operational confidence.",
            phase_start=2,
        )
    ],
    "frontend": [
        Habit(
            name="UI component study and cloning",
            frequency="weekly",
            duration_minutes=60,
            rationale="Recreating polished UIs accelerates front-end design intuition.",
            phase_start=2,
        )
    ],
}


class WeeklyPlanner:
    """Distributes phase content into per-week tasks and emits habit recommendations.

    Stateless — create once and call as many times as needed.
    """

    def plan(
        self,
        phases: list[Phase],
        milestones: list[Milestone],
        timeline_months: int,
        weekly_hours: int,
        target_role: str = "",
    ) -> tuple[list[WeeklyTask], list[Habit]]:
        """Return (weekly_schedule, habits) for the full roadmap."""
        total_weeks = timeline_months * 4
        scaled = _scale_phases(phases, total_weeks)
        milestone_map: dict[int, Milestone] = {m.phase_index: m for m in milestones}

        schedule: list[WeeklyTask] = []
        week_cursor = 1
        for phase in scaled:
            schedule.extend(
                _plan_phase(phase, week_cursor, weekly_hours, milestone_map.get(phase.index))
            )
            week_cursor += phase.duration_weeks

        habits = list(_CORE_HABITS)
        role_lower = target_role.lower()
        for keyword, bonus in _ROLE_HABITS.items():
            if keyword in role_lower:
                habits.extend(bonus)
                break

        return schedule, habits


# ── Helpers ──────────────────────────────────────────────────────────────────


def _scale_phases(phases: list[Phase], total_weeks: int) -> list[Phase]:
    """Proportionally rescale phase durations to sum exactly to total_weeks."""
    if not phases:
        return phases
    current_total = sum(p.duration_weeks for p in phases)
    if current_total == total_weeks:
        return phases

    scaled: list[Phase] = []
    accumulated = 0
    for i, phase in enumerate(phases):
        if i == len(phases) - 1:
            new_dur = max(1, total_weeks - accumulated)
        else:
            new_dur = max(1, round(phase.duration_weeks * total_weeks / current_total))
        accumulated += new_dur
        scaled.append(dataclasses.replace(phase, duration_weeks=new_dur))
    return scaled


def _plan_phase(
    phase: Phase,
    start_week: int,
    weekly_hours: int,
    milestone: Milestone | None,
) -> list[WeeklyTask]:
    tasks: list[WeeklyTask] = []
    skills = phase.skills_to_acquire or [phase.title]
    n = phase.duration_weeks

    for w in range(n):
        week_num = start_week + w
        is_last = w == n - 1
        skill = skills[w % len(skills)]

        ratio = w / max(n - 1, 1)
        if ratio < 0.35:
            template_key = "intro"
        elif not is_last:
            template_key = "build"
        else:
            template_key = "consolidate"

        week_tasks = [t.format(skill=skill) for t in _TASK_TEMPLATES[template_key]]
        deliverable = milestone.deliverable if (is_last and milestone) else None

        tasks.append(
            WeeklyTask(
                week_number=week_num,
                phase_index=phase.index,
                focus_area=skill,
                tasks=week_tasks,
                estimated_hours=float(weekly_hours),
                deliverable=deliverable,
            )
        )
    return tasks
