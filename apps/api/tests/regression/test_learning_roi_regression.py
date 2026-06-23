"""Regression tests for the Learning ROI domain."""
import pytest

from src.domains.learning_roi.schemas import LearningItemOut
from src.domains.learning_roi.service import LearningRoiService

pytestmark = pytest.mark.regression


def test_from_doc_unknown_type_and_status_fall_back() -> None:
    # REGRESSION: legacy/garbage enum values must degrade, not raise.
    out = LearningItemOut.from_doc(
        {"id": "i1", "title": "T", "type": "webinar", "status": "paused"}
    )
    assert out.type == "other"
    assert out.status == "planned"


def test_from_doc_coerces_numeric_strings() -> None:
    out = LearningItemOut.from_doc({"id": "i1", "title": "T", "cost": "150", "hours": "12"})
    assert out.cost == 150.0
    assert out.hours == 12.0


def test_demand_skills_dedupes_and_lowercases_across_sources() -> None:
    # REGRESSION: trending market skills + CV gaps must be merged, de-duplicated
    # case-insensitively, and tolerate both dict and str shapes without crashing.
    snapshot = {
        "market": {"trending_skills": [{"name": "Python"}, "SQL", {"name": "python"}]},
        "cv": {"skill_gaps": [{"skill": "sql"}, "Docker"]},
    }
    session = type("S", (), {"plan_context": type("P", (), {"snapshot": snapshot})()})()
    skills = LearningRoiService._demand_skills(session, profile=None)
    lowered = [s.lower() for s in skills]
    assert lowered == sorted(set(lowered), key=lowered.index)  # no dupes
    assert "python" in lowered and "sql" in lowered and "docker" in lowered
    assert len(lowered) == 3


def test_demand_skills_handles_missing_plan_context() -> None:
    session = type("S", (), {"plan_context": None})()
    assert LearningRoiService._demand_skills(session, profile=None) == []
