"""Feedback — submit help requests / product feedback and read own history.

Routes:
  GET  /api/v1/feedback   — list the caller's submissions (newest-first)
  POST /api/v1/feedback   — file a new submission
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut
from src.domains.feedback.service import FeedbackService, get_feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("", response_model=list[FeedbackOut], summary="List my feedback")
async def list_feedback(
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
) -> list[FeedbackOut]:
    return await service.list(user.uid, limit=limit)


@router.post(
    "",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback",
)
async def create_feedback(
    body: FeedbackCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackOut:
    return await service.create(user.uid, body)
