"""HabitStreakAnalyser — pure computation: streak and completion-rate statistics.

Stateless. Given an ordered list of weekly scorecards, it returns one
HabitStreak per habit seen across those scorecards.

Design: no I/O, no LLM calls — safe to use in unit tests with no mocks.
"""
from __future__ import annotations

from agents.core.logging import get_logger
from agents.progress.models import HabitStreak, WeeklyScorecard

logger = get_logger(__name__)


class HabitStreakAnalyser:
    """Compute per-habit streak and completion-rate statistics from scorecard history."""

    def analyse(
        self,
        scorecards: list[WeeklyScorecard],
        *,
        correlation_id: str = "",
    ) -> list[HabitStreak]:
        """Return one HabitStreak per habit encountered in the scorecards.

        Parameters
        ----------
        scorecards:
            Weekly self-reports ordered oldest → newest.
        """
        if not scorecards:
            return []

        # Union of all habit names seen across all scorecards
        all_habits: set[str] = set()
        for sc in scorecards:
            all_habits.update(sc.habit_completions.keys())

        streaks: list[HabitStreak] = []
        for habit in sorted(all_habits):
            # Build a binary completion vector aligned to scorecard order.
            # If a habit was not tracked in a given week, treat it as not completed.
            completions = [
                sc.habit_completions.get(habit, False) for sc in scorecards
            ]
            streaks.append(_compute_streak(habit, completions))

        logger.info(
            "habit_streak_analyser.completed",
            habit_count=len(streaks),
            scorecard_count=len(scorecards),
            correlation_id=correlation_id,
        )
        return streaks


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compute_streak(habit_name: str, completions: list[bool]) -> HabitStreak:
    """Compute streak statistics for a single habit."""
    total_weeks = len(completions)
    weeks_completed = sum(1 for c in completions if c)
    completion_rate = round(weeks_completed / total_weeks, 3) if total_weeks else 0.0

    # Current streak: count backwards from the most recent entry
    current_streak = 0
    for completed in reversed(completions):
        if completed:
            current_streak += 1
        else:
            break

    # Longest streak: forward scan
    longest = 0
    run = 0
    for completed in completions:
        if completed:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    return HabitStreak(
        habit_name=habit_name,
        current_streak_weeks=current_streak,
        longest_streak_weeks=longest,
        completion_rate=completion_rate,
        total_weeks_tracked=total_weeks,
        weeks_completed=weeks_completed,
    )
