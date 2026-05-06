"""Intake-domain data models.

Pure dataclasses — no I/O, no LLM, no framework imports.
These are internal to the intake package; do not import them from outside.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ExtractedSlot:
    """One piece of information extracted from the user's text via NER/slot-fill."""

    field_name: str
    value: Any
    confidence: float     # 0.0 – 1.0
    source_span: str      # exact substring of raw text that produced this slot


@dataclass(frozen=True)
class SlotExtractionResult:
    """Output of one SlotExtractor.extract() call."""

    raw_text: str
    slots: list[ExtractedSlot] = field(default_factory=list)
    unresolved_mentions: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0

    @property
    def as_dict(self) -> dict[str, Any]:
        """Flat {field_name: value} view of the extracted slots."""
        return {s.field_name: s.value for s in self.slots}


@dataclass(frozen=True)
class ProfileDiff:
    """Changes applied to a UserProfileSnapshot by ProfileBuilder.build()."""

    added_fields: list[str]
    updated_fields: list[str]
    unchanged_fields: list[str]
    old_completeness: float
    new_completeness: float
