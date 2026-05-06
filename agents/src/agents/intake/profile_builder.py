"""ProfileBuilder — merges NER-extracted slots into a UserProfileSnapshot.

Pure functions: no I/O, no LLM calls, no network. Takes the existing profile
and a SlotExtractionResult and returns an updated profile plus a ProfileDiff.

Merge rules (consistent with ClarificationEngine.apply_answers):
- ``skills``, ``goals``, ``constraints``: union — new items appended, no duplicates.
- Scalar fields: overwrite only when new value is non-empty and different.
- ``additional`` dict: never touched.

Observable: opens an OTel span and records a Prometheus histogram on each call.
"""
from __future__ import annotations

from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.contracts.tasks import UserProfileSnapshot
from agents.core.logging import get_logger
from agents.core.observability import INTAKE_PROFILE_COMPLETENESS, get_tracer
from agents.intake.models import ProfileDiff, SlotExtractionResult

logger = get_logger(__name__)
_tracer = get_tracer("agents.intake.profile_builder")

# Mirrors _SLOT_WEIGHTS in ClarificationEngine so completeness scores are comparable.
_COMPLETENESS_WEIGHTS: dict[str, float] = {
    "target_role":            0.30,
    "current_role":           0.15,
    "skills":                 0.15,
    "location":               0.10,
    "timeline_months":        0.15,
    "weekly_hours_available": 0.10,
    "salary_goal":            0.05,
}

# All list-typed profile fields that should be merged (union) rather than replaced.
_LIST_FIELDS = frozenset({"skills", "goals", "constraints"})


class ProfileBuilder:
    """Merges NER-extracted slots onto an existing UserProfileSnapshot.

    Stateless — instantiate once and call ``build()`` for each agent run.
    """

    def build(
        self,
        existing: UserProfileSnapshot,
        extraction: SlotExtractionResult,
        *,
        correlation_id: str = "",
    ) -> tuple[UserProfileSnapshot, ProfileDiff]:
        """Merge extracted slots onto ``existing`` and return ``(updated, diff)``.

        The original profile is never mutated; Pydantic ``model_copy`` is used.
        Only slots with confidence >= 0.7 (enforced by SlotExtractor) reach here.
        """
        with _tracer.start_as_current_span("intake.profile_build") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("input_slots", len(extraction.slots))

            added: list[str] = []
            updated: list[str] = []
            unchanged: list[str] = []
            updates: dict[str, Any] = {}

            for slot in extraction.slots:
                name, new_val = slot.field_name, slot.value
                current_val = getattr(existing, name, None)

                if name in _LIST_FIELDS:
                    merged = _merge_list(current_val, new_val)
                    if merged != (current_val or []):
                        updates[name] = merged
                        (added if not current_val else updated).append(name)
                    else:
                        unchanged.append(name)
                else:
                    if new_val and new_val != current_val:
                        updates[name] = new_val
                        (added if current_val is None else updated).append(name)
                    else:
                        unchanged.append(name)

            updated_profile = existing.model_copy(update=updates) if updates else existing

            old_score = _completeness(existing)
            new_score = _completeness(updated_profile)

            INTAKE_PROFILE_COMPLETENESS.observe(new_score)

            diff = ProfileDiff(
                added_fields=added,
                updated_fields=updated,
                unchanged_fields=unchanged,
                old_completeness=old_score,
                new_completeness=new_score,
            )

            span.set_attribute("fields_added", len(added))
            span.set_attribute("fields_updated", len(updated))
            span.set_attribute("old_completeness", old_score)
            span.set_attribute("new_completeness", new_score)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "intake.profile_built",
                added=added,
                updated=updated,
                old_score=old_score,
                new_score=new_score,
                score_delta=round(new_score - old_score, 3),
                correlation_id=correlation_id,
            )
            return updated_profile, diff


# ── Public helpers ─────────────────────────────────────────────────────────


def completeness_score(profile: UserProfileSnapshot) -> float:
    """Weighted completeness in [0, 1]. Consistent with ClarificationEngine.score()."""
    return _completeness(profile)


def missing_slots(profile: UserProfileSnapshot) -> list[str]:
    """Slot names with no value, ordered by descending weight (most blocking first)."""
    return sorted(
        (slot for slot in _COMPLETENESS_WEIGHTS if not getattr(profile, slot, None)),
        key=lambda s: _COMPLETENESS_WEIGHTS[s],
        reverse=True,
    )


# ── Private helpers ────────────────────────────────────────────────────────


def _completeness(profile: UserProfileSnapshot) -> float:
    return round(
        sum(
            weight
            for slot, weight in _COMPLETENESS_WEIGHTS.items()
            if bool(getattr(profile, slot, None))
        ),
        3,
    )


def _merge_list(existing: list[str] | None, new_items: list[str] | None) -> list[str]:
    """Union of two lists, preserving order and deduplicating case-insensitively."""
    existing_lower: set[str] = {v.lower() for v in (existing or [])}
    result: list[str] = list(existing or [])
    for item in new_items or []:
        if item.lower() not in existing_lower:
            result.append(item)
            existing_lower.add(item.lower())
    return result
