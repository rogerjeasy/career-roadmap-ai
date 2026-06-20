"""Plan Version Snapshots / Undo (§11.2, §11.4).

Routes:
  GET    /api/v1/roadmap-snapshots?roadmap_id=…   — snapshots for a roadmap
  POST   /api/v1/roadmap-snapshots                — capture the current roadmap
  POST   /api/v1/roadmap-snapshots/{id}/restore   — restore (auto-saves current first)
  DELETE /api/v1/roadmap-snapshots/{id}           — delete a snapshot
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.snapshots.schemas import SnapshotCreate, SnapshotOut
from src.domains.snapshots.service import SnapshotService, get_snapshot_service

router = APIRouter(prefix="/roadmap-snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotOut], summary="Snapshots for a roadmap")
async def list_snapshots(
    roadmap_id: str = Query(..., min_length=1),
    user: AuthenticatedUser = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> list[SnapshotOut]:
    return await service.list(user.uid, roadmap_id)


@router.post(
    "",
    response_model=SnapshotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Capture the current roadmap",
)
async def create_snapshot(
    payload: SnapshotCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> SnapshotOut:
    return await service.create(user.uid, payload.roadmap_id, payload.label)


@router.post(
    "/{snapshot_id}/restore",
    response_model=SnapshotOut,
    summary="Restore a snapshot (auto-saves current state first)",
)
async def restore_snapshot(
    snapshot_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> SnapshotOut:
    return await service.restore(user.uid, snapshot_id)


@router.delete(
    "/{snapshot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a snapshot",
)
async def delete_snapshot(
    snapshot_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: SnapshotService = Depends(get_snapshot_service),
) -> None:
    await service.delete(user.uid, snapshot_id)
