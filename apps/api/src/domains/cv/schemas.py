"""CV domain — Pydantic schemas for CV analysis results."""
from enum import Enum

from pydantic import BaseModel, computed_field


class SkillLevel(str, Enum):
    strong = "strong"
    supporting = "supporting"


class CvRole(BaseModel):
    title: str
    company: str | None = None
    duration_months: int | None = None


class CvSkill(BaseModel):
    name: str
    level: SkillLevel


class CvProject(BaseModel):
    name: str
    description: str | None = None
    impact: str | None = None


class CvEducation(BaseModel):
    degree: str
    field: str | None = None
    institution: str | None = None
    year: int | None = None


class CvUploadResponse(BaseModel):
    """Response returned by POST /cv/upload.

    ``analysis`` contains the synchronously extracted profile data.
    ``upload_id`` is the background task reference — the file is being
    stored in Cloudinary asynchronously; use GET /uploads/{upload_id}
    to check the storage status (or ignore it — the analysis is the
    primary result).
    """
    analysis: "CvAnalysisResult"
    upload_id: str


class CvAnalysisResult(BaseModel):
    roles: list[CvRole] = []
    skills: list[CvSkill] = []
    projects: list[CvProject] = []
    education: list[CvEducation] = []
    leadership_signals: int = 0
    years_of_experience: int = 0
    current_role: str | None = None
    summary: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def strong_skills_count(self) -> int:
        return sum(1 for s in self.skills if s.level == SkillLevel.strong)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supporting_skills_count(self) -> int:
        return sum(1 for s in self.skills if s.level == SkillLevel.supporting)
