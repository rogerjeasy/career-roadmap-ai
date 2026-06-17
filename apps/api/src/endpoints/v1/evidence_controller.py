"""Evidence Vault — CRUD for the user's proof-of-progress items.

Routes:
  GET    /api/v1/evidence          — list evidence (newest-first)
  POST   /api/v1/evidence          — add an item
  GET    /api/v1/evidence/{id}     — get one
  PATCH  /api/v1/evidence/{id}     — update one
  DELETE /api/v1/evidence/{id}     — remove one
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.evidence.schemas import EvidenceCreate, EvidenceOut, EvidenceUpdate
from src.domains.evidence.service import EvidenceService, get_evidence_service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("", response_model=list[EvidenceOut], summary="List evidence items")
async def list_evidence(
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthenticatedUser = Depends(get_current_user),
    service: EvidenceService = Depends(get_evidence_service),
) -> list[EvidenceOut]:
    return await service.list(user.uid, limit=limit)


@router.post(
    "",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an evidence item",
)
async def create_evidence(
    body: EvidenceCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceOut:
    return await service.create(user.uid, body)


@router.get("/{evidence_id}", response_model=EvidenceOut, summary="Get an evidence item")
async def get_evidence(
    evidence_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceOut:
    return await service.get(user.uid, evidence_id)


@router.patch(
    "/{evidence_id}", response_model=EvidenceOut, summary="Update an evidence item"
)
async def update_evidence(
    evidence_id: str,
    body: EvidenceUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceOut:
    return await service.update(user.uid, evidence_id, body)


@router.delete(
    "/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an evidence item",
)
async def delete_evidence(
    evidence_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: EvidenceService = Depends(get_evidence_service),
) -> None:
    await service.delete(user.uid, evidence_id)
