"""CV Analysis domain models — pure data, no I/O, no LLM calls.

Internal to the cv_analysis package; do not import from outside.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExperienceEntry:
    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    duration_months: int | None = None
    responsibilities: list[str] = field(default_factory=list)
    impact_statements: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EducationEntry:
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: int | None = None
    gpa: float | None = None


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    name: str
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    impact: str | None = None


@dataclass(frozen=True, slots=True)
class SkillNode:
    name: str                       # raw skill string from CV
    canonical_name: str             # normalised canonical form
    # programming_language | framework | database | platform | tool |
    # soft_skill | domain | certification | other
    category: str
    proficiency: str | None = None  # beginner | intermediate | advanced | expert
    years_of_experience: float | None = None
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillGraph:
    nodes: list[SkillNode] = field(default_factory=list)

    @property
    def by_category(self) -> dict[str, list[SkillNode]]:
        result: dict[str, list[SkillNode]] = {}
        for node in self.nodes:
            result.setdefault(node.category, []).append(node)
        return result

    @property
    def canonical_names(self) -> list[str]:
        return [n.canonical_name for n in self.nodes]


@dataclass(frozen=True)
class ParsedCV:
    raw_text: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    experience: list[ExperienceEntry] = field(default_factory=list)
    education: list[EducationEntry] = field(default_factory=list)
    projects: list[ProjectEntry] = field(default_factory=list)
    raw_skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    total_experience_months: int | None = None


@dataclass(frozen=True, slots=True)
class ReadinessBreakdown:
    required_skills_matched: float    # 0–1 fraction of must-have skills present
    preferred_skills_matched: float   # 0–1 fraction of nice-to-have skills present
    experience_level_match: float     # 0–1 years-of-experience fit
    education_match: float            # 0–1 educational background alignment
    domain_alignment: float           # 0–1 industry/domain experience overlap


@dataclass(frozen=True)
class ReadinessResult:
    overall_score: float              # 0–1 weighted composite
    breakdown: ReadinessBreakdown
    matched_skills: list[str] = field(default_factory=list)
    missing_required_skills: list[str] = field(default_factory=list)
    missing_preferred_skills: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
