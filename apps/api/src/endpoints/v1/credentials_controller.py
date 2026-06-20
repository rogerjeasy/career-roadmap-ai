"""Verifiable Skill Credentials (§14.8).

Routes:
  GET    /api/v1/credentials                   — list my credentials
  POST   /api/v1/credentials                   — issue a signed credential
  GET    /api/v1/credentials/{id}              — get one of mine
  POST   /api/v1/credentials/{id}/revoke       — revoke (keeps the record honest)
  DELETE /api/v1/credentials/{id}              — soft-delete
  GET    /api/v1/credentials/verify/{token}    — PUBLIC verification (no auth)
"""
from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.credentials.schemas import (
    CredentialIssue,
    CredentialOut,
    CredentialVerification,
)
from src.domains.credentials.service import CredentialService, get_credential_service
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/credentials", tags=["credentials"])


def _holder_name(user: AuthenticatedUser) -> str:
    return user.name or (user.email.split("@")[0] if user.email else "A verified professional")


@router.get("", response_model=list[CredentialOut], summary="List my credentials")
async def list_credentials(
    user: AuthenticatedUser = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> list[CredentialOut]:
    return await service.list(user.uid)


@router.post(
    "",
    response_model=CredentialOut,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a signed, shareable credential",
)
async def issue_credential(
    payload: CredentialIssue,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
    webhooks: WebhookService = Depends(get_webhook_service),
) -> CredentialOut:
    credential = await service.issue(user.uid, _holder_name(user), payload)
    background.add_task(
        webhooks.dispatch,
        user.uid,
        "credential.issued",
        {"credential_id": credential.id, "skill": credential.skill, "level": credential.level},
    )
    return credential


# NB: the public verify route is declared before "/{credential_id}" so the
# literal "verify" segment is not captured as a credential id.
@router.get(
    "/verify/{share_token}",
    response_model=CredentialVerification,
    summary="Publicly verify a credential by share token (no auth)",
)
async def verify_credential(
    share_token: str,
    service: CredentialService = Depends(get_credential_service),
) -> CredentialVerification:
    return await service.verify(share_token)


@router.get(
    "/{credential_id}", response_model=CredentialOut, summary="Get one credential"
)
async def get_credential(
    credential_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialOut:
    return await service.get(user.uid, credential_id)


@router.post(
    "/{credential_id}/revoke",
    response_model=CredentialOut,
    summary="Revoke a credential",
)
async def revoke_credential(
    credential_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialOut:
    return await service.revoke(user.uid, credential_id)


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a credential",
)
async def delete_credential(
    credential_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> None:
    await service.delete(user.uid, credential_id)
