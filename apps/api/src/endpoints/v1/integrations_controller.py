"""External account integrations (OAuth).

Routes:
  GET    /api/v1/integrations                      — connection status per provider
  POST   /api/v1/integrations/{provider}/authorize — begin connect, returns authorize URL
  GET    /api/v1/integrations/{provider}/callback   — OAuth redirect target (no auth)
  DELETE /api/v1/integrations/{provider}            — disconnect

The callback is hit by the OAuth provider's redirect, so it is NOT behind
``get_current_user`` — the user identity is recovered from the signed ``state``
parameter that was minted (and bound to the user) when the flow began.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from src.config import get_settings
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import AppException
from src.core.logging import get_logger
from src.domains.integrations.schemas import AuthorizeOut, IntegrationStatusOut
from src.domains.integrations.service import (
    IntegrationsService,
    get_integrations_service,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatusOut], summary="List integration status")
async def list_integrations(
    user: AuthenticatedUser = Depends(get_current_user),
    service: IntegrationsService = Depends(get_integrations_service),
) -> list[IntegrationStatusOut]:
    return await service.list_status(user.uid)


@router.post(
    "/{provider}/authorize",
    response_model=AuthorizeOut,
    summary="Begin connecting an external account",
)
async def authorize_integration(
    provider: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: IntegrationsService = Depends(get_integrations_service),
) -> AuthorizeOut:
    url = await service.build_authorize_url(user.uid, provider)
    return AuthorizeOut(authorization_url=url)


@router.get(
    "/{provider}/callback",
    summary="OAuth redirect target",
    include_in_schema=False,
)
async def integration_callback(
    provider: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    service: IntegrationsService = Depends(get_integrations_service),
) -> RedirectResponse:
    settings = get_settings()
    base = f"{settings.frontend_base_url.rstrip('/')}/settings/integrations"

    def _redirect(params: dict[str, str]) -> RedirectResponse:
        # 303 so the browser issues a GET to the app after the provider's redirect.
        return RedirectResponse(url=f"{base}?{urlencode(params)}", status_code=303)

    if error:
        logger.info("integrations.callback_denied", provider=provider, error=error)
        return _redirect({"provider": provider, "status": "denied"})
    if not code or not state:
        return _redirect({"provider": provider, "status": "error"})

    try:
        await service.handle_callback(provider, code, state)
    except AppException as exc:
        logger.warning(
            "integrations.callback_failed", provider=provider, error=exc.detail
        )
        return _redirect({"provider": provider, "status": "error"})

    return _redirect({"provider": provider, "status": "connected"})


@router.delete(
    "/{provider}",
    status_code=204,
    summary="Disconnect an external account",
)
async def disconnect_integration(
    provider: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: IntegrationsService = Depends(get_integrations_service),
) -> None:
    await service.disconnect(user.uid, provider)
