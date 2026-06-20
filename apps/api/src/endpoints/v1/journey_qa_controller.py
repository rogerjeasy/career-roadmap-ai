"""Ask-My-Journey — grounded Q&A over the user's own data.

Routes:
  POST   /api/v1/journey/ask   — ask a question; answer grounded in your data
"""
from fastapi import APIRouter, Depends

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.journey_qa.schemas import AskInput, AskReply
from src.domains.journey_qa.service import JourneyQaService, get_journey_qa_service

router = APIRouter(prefix="/journey", tags=["journey-qa"])


@router.post("/ask", response_model=AskReply, summary="Ask about your journey")
async def ask(
    payload: AskInput,
    user: AuthenticatedUser = Depends(get_current_user),
    service: JourneyQaService = Depends(get_journey_qa_service),
) -> AskReply:
    return await service.ask(user.uid, payload)
