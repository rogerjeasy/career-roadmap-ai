"""Intake & Profile Agent — L3 Specialist Agent.

Public surface:
    IntakeAgent     — register via agents.core.agent_registry.registry.register()
    SlotExtractor   — NER/slot-filling component (injectable in tests)
    ProfileBuilder  — profile merge component (injectable in tests)
    ExtractedSlot   — one extracted slot datum
    SlotExtractionResult — full output of one SlotExtractor.extract() call
    ProfileDiff     — change summary from ProfileBuilder.build()
"""
from agents.intake.intake_agent import IntakeAgent
from agents.intake.models import ExtractedSlot, ProfileDiff, SlotExtractionResult
from agents.intake.profile_builder import ProfileBuilder
from agents.intake.slot_extractor import SlotExtractor

__all__ = [
    "IntakeAgent",
    "SlotExtractor",
    "ProfileBuilder",
    "ExtractedSlot",
    "SlotExtractionResult",
    "ProfileDiff",
]
