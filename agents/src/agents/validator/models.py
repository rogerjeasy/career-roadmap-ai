"""Validator / Critic Agent domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    DEGRADED = "degraded"  # partial failure — score below threshold but not zero


class FixPriority(str, Enum):
    CRITICAL = "critical"  # must fix before roadmap can be shown to the user
    HIGH = "high"          # should fix; degrades quality significantly if left
    LOW = "low"            # optional improvement


@dataclass(frozen=True)
class EvidenceCheck:
    """Coverage result for a single roadmap claim against agent outputs."""

    claim: str
    is_grounded: bool
    evidence_ref: str | None  # key path in agent_outputs, or None
    confidence: float         # 0.0–1.0


@dataclass(frozen=True)
class UnsupportedClaim:
    """A roadmap claim that has no backing in any agent output."""

    claim: str
    roadmap_location: str  # e.g. "phases[2].market_relevance"
    severity: FixPriority


@dataclass(frozen=True)
class RealismIssue:
    """A timeline or workload feasibility issue detected in the roadmap."""

    description: str
    phase_index: int | None  # None = whole-roadmap issue
    severity: FixPriority
    suggested_adjustment: str


@dataclass(frozen=True)
class FixInstruction:
    """One actionable repair instruction for the Roadmap Synthesis Agent."""

    issue_id: str
    priority: FixPriority
    category: str          # "evidence_gap" | "unsupported_claim" | "timeline" | "workload"
    description: str
    suggested_action: str
    roadmap_location: str


@dataclass
class ValidationResult:
    """Full structured output returned by ValidatorAgent._execute().

    Call ``to_dict()`` before returning from _execute() to ensure the
    value is JSON-serialisable (plain dicts, no dataclass instances).
    """

    # Aggregate
    passed: bool
    overall_score: float          # weighted composite (0.0–1.0)

    # Per-stage scores
    evidence_coverage_score: float
    grounding_score: float
    realism_score: float

    # Per-stage detailed outputs
    evidence_checks: list[EvidenceCheck] = field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = field(default_factory=list)
    realism_issues: list[RealismIssue] = field(default_factory=list)
    fix_instructions: list[FixInstruction] = field(default_factory=list)

    # Per-stage status labels
    evidence_check_status: CheckStatus = CheckStatus.PASSED
    grounding_status: CheckStatus = CheckStatus.PASSED
    realism_status: CheckStatus = CheckStatus.PASSED

    processing_steps: list[str] = field(default_factory=list)
    validation_duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serialisable dict for AgentResult.output storage."""
        return asdict(self)
