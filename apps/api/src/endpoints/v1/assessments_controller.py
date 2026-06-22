"""Skill Assessment — quiz/challenge engine + verified badges.

Routes:
  GET    /api/v1/assessments              — my assessments (summaries)
  POST   /api/v1/assessments              — start a new assessment for a skill
  GET    /api/v1/assessments/{id}         — one assessment (questions or result)
  POST   /api/v1/assessments/{id}/submit  — grade answers, mint a badge on a pass
"""
from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.assessments.schemas import (
    AssessmentOut,
    AssessmentStartInput,
    AssessmentSubmit,
    AssessmentSummary,
)
from src.domains.assessments.service import AssessmentService, get_assessment_service
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _holder_name(user: AuthenticatedUser) -> str:
    return user.name or (user.email.split("@")[0] if user.email else "A verified professional")


@router.get("", response_model=list[AssessmentSummary], summary="My assessments")
async def list_assessments(
    user: AuthenticatedUser = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> list[AssessmentSummary]:
    return await service.list(user.uid)


@router.post(
    "",
    response_model=AssessmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start an assessment for a skill",
)
async def start_assessment(
    payload: AssessmentStartInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentOut:
    return await service.start(user.uid, payload)


@router.get("/{assessment_id}", response_model=AssessmentOut, summary="One assessment")
async def get_assessment(
    assessment_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentOut:
    return await service.get(user.uid, assessment_id)


@router.post(
    "/{assessment_id}/submit",
    response_model=AssessmentOut,
    summary="Submit answers and grade the assessment",
)
async def submit_assessment(
    assessment_id: str,
    payload: AssessmentSubmit,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
    webhooks: WebhookService = Depends(get_webhook_service),
) -> AssessmentOut:
    result = await service.submit(user.uid, assessment_id, _holder_name(user), payload)
    if result.passed:
        background.add_task(
            webhooks.dispatch,
            user.uid,
            "assessment.passed",
            {
                "assessment_id": result.id,
                "skill": result.skill,
                "level": result.level,
                "score": result.score,
                "credential_id": result.credential_id,
            },
        )
    return result
