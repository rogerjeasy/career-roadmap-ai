"""Mentorship & Insider Conversations (§14.13).

Routes:
  GET    /api/v1/mentorship/profile           — my mentor profile (or null)
  PUT    /api/v1/mentorship/profile           — opt in / update mentor profile
  DELETE /api/v1/mentorship/profile           — opt out (deactivate)
  GET    /api/v1/mentorship/mentors           — discover mentors, ranked by match
  GET    /api/v1/mentorship/sessions          — my sessions (as mentor + mentee)
  POST   /api/v1/mentorship/sessions          — request a session (approval gate)
  POST   /api/v1/mentorship/sessions/{id}/respond   — mentor accepts/declines
  POST   /api/v1/mentorship/sessions/{id}/complete  — mark accepted session done
  GET    /api/v1/mentorship/case-studies      — browse insider conversations
  POST   /api/v1/mentorship/case-studies      — contribute one
  DELETE /api/v1/mentorship/case-studies/{id} — delete my own
"""
from fastapi import APIRouter, Depends, Response, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.mentorship.schemas import (
    CaseStudyCreate,
    CaseStudyOut,
    MentorProfileOut,
    MentorProfileUpsert,
    MentorSessionOut,
    SessionRequest,
    SessionRespond,
)
from src.domains.mentorship.service import MentorshipService, get_mentorship_service

router = APIRouter(prefix="/mentorship", tags=["mentorship"])


def _name(user: AuthenticatedUser) -> str:
    return user.name or (user.email.split("@")[0] if user.email else "A member")


# ── Mentor profile ────────────────────────────────────────────────────────────


@router.get("/profile", response_model=MentorProfileOut | None, summary="My mentor profile")
async def get_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> MentorProfileOut | None:
    return await service.get_my_profile(user.uid)


@router.put("/profile", response_model=MentorProfileOut, summary="Opt in / update profile")
async def upsert_profile(
    payload: MentorProfileUpsert,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> MentorProfileOut:
    return await service.upsert_profile(user.uid, _name(user), payload)


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT, summary="Opt out")
async def deactivate_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> None:
    await service.deactivate_profile(user.uid)


# ── Discovery & sessions ──────────────────────────────────────────────────────


@router.get("/mentors", response_model=list[MentorProfileOut], summary="Discover mentors")
async def discover_mentors(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> list[MentorProfileOut]:
    return await service.discover_mentors(user.uid)


@router.get("/sessions", response_model=list[MentorSessionOut], summary="My sessions")
async def list_sessions(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> list[MentorSessionOut]:
    return await service.list_my_sessions(user.uid)


@router.post(
    "/sessions",
    response_model=MentorSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request a session",
)
async def request_session(
    payload: SessionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> MentorSessionOut:
    return await service.request_session(user.uid, _name(user), payload)


@router.post(
    "/sessions/{session_id}/respond",
    response_model=MentorSessionOut,
    summary="Accept or decline (mentor only)",
)
async def respond_session(
    session_id: str,
    payload: SessionRespond,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> MentorSessionOut:
    return await service.respond_session(user.uid, session_id, payload)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=MentorSessionOut,
    summary="Mark session completed",
)
async def complete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> MentorSessionOut:
    return await service.complete_session(user.uid, session_id)


# ── Insider conversations ─────────────────────────────────────────────────────


@router.get(
    "/case-studies", response_model=list[CaseStudyOut], summary="Browse insider stories"
)
async def list_case_studies(
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> list[CaseStudyOut]:
    return await service.list_case_studies(user.uid)


@router.post(
    "/case-studies",
    response_model=CaseStudyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Contribute a story",
)
async def create_case_study(
    payload: CaseStudyCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> CaseStudyOut:
    return await service.create_case_study(user.uid, _name(user), payload)


@router.delete(
    "/case-studies/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my story",
)
async def delete_case_study(
    case_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: MentorshipService = Depends(get_mentorship_service),
) -> Response:
    await service.delete_case_study(user.uid, case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
