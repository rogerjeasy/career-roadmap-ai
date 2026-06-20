"""Interview Prep — mock interviews + question banks.

Routes:
  POST   /api/v1/interview/questions     — generate a tailored question bank
  POST   /api/v1/interview/turn          — one mock-interview turn (scored)
  GET    /api/v1/interview/sessions      — my saved practices
  POST   /api/v1/interview/sessions      — save a completed practice
  DELETE /api/v1/interview/sessions/{id} — delete a practice
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.interview_prep.schemas import (
    QuestionRequest,
    QuestionSet,
    SessionCreate,
    SessionOut,
    TurnInput,
    TurnReply,
)
from src.domains.interview_prep.service import (
    InterviewPrepService,
    get_interview_prep_service,
)

router = APIRouter(prefix="/interview", tags=["interview-prep"])


@router.post("/questions", response_model=QuestionSet, summary="Generate a question bank")
async def generate_questions(
    payload: QuestionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> QuestionSet:
    return await service.generate_questions(user.uid, payload)


@router.post("/turn", response_model=TurnReply, summary="One mock-interview turn")
async def interview_turn(
    payload: TurnInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> TurnReply:
    return await service.turn(user.uid, payload)


@router.get("/sessions", response_model=list[SessionOut], summary="My saved practices")
async def list_sessions(
    user: AuthenticatedUser = Depends(get_current_user),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> list[SessionOut]:
    return await service.list_sessions(user.uid)


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save a completed practice",
)
async def save_session(
    payload: SessionCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> SessionOut:
    return await service.save_session(user.uid, payload)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a practice",
)
async def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: InterviewPrepService = Depends(get_interview_prep_service),
) -> None:
    await service.delete_session(user.uid, session_id)
