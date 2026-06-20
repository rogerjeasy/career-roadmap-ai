"""Public API Keys — key management (§21).

Firebase-authenticated CRUD for a user's own API keys.

Routes:
  GET    /api/v1/api-keys             — list my keys (secrets never returned)
  POST   /api/v1/api-keys             — mint a key (full secret returned ONCE)
  POST   /api/v1/api-keys/{id}/revoke — revoke a key
  DELETE /api/v1/api-keys/{id}        — delete a key
"""
from fastapi import APIRouter, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.api_keys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from src.domains.api_keys.service import ApiKeyService, get_api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut], summary="List my API keys")
async def list_keys(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyOut]:
    return await service.list(user.uid)


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Mint an API key (secret shown once)",
)
async def create_key(
    payload: ApiKeyCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyCreated:
    return await service.create(user.uid, payload)


@router.post("/{key_id}/revoke", response_model=ApiKeyOut, summary="Revoke a key")
async def revoke_key(
    key_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyOut:
    return await service.revoke(user.uid, key_id)


@router.delete(
    "/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a key"
)
async def delete_key(
    key_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApiKeyService = Depends(get_api_key_service),
) -> None:
    await service.delete(user.uid, key_id)
