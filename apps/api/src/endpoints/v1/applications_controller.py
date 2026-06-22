"""Job Applications — CV rewrite + cover letter + tracking (§10.2).

Routes:
  GET    /api/v1/applications                       — my application pipeline
  GET    /api/v1/applications/summary               — pipeline counts
  POST   /api/v1/applications                       — track a new application
  GET    /api/v1/applications/{id}                  — one application
  PATCH  /api/v1/applications/{id}                  — update (status, notes, …)
  DELETE /api/v1/applications/{id}                  — remove
  POST   /api/v1/applications/{id}/tailor-cv        — generate a tailored CV rewrite
  POST   /api/v1/applications/{id}/cover-letter     — generate a cover letter
  PUT    /api/v1/applications/{id}/stage-notes/{s}  — set a per-stage note
  POST   /api/v1/applications/{id}/reminders        — add a follow-up reminder
  PATCH  /api/v1/applications/{id}/reminders/{rid}  — mark a reminder done/undone
  DELETE /api/v1/applications/{id}/reminders/{rid}  — remove a reminder
"""
from pydantic import BaseModel

from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.applications.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationSummary,
    ApplicationUpdate,
    ReminderCreate,
    StageNoteUpdate,
)
from src.domains.applications.service import (
    ApplicationService,
    get_application_service,
)
from src.domains.push.service import PushService, get_push_service
from src.domains.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut], summary="My applications")
async def list_applications(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationOut]:
    return await service.list(user.uid)


@router.get("/summary", response_model=ApplicationSummary, summary="Pipeline counts")
async def get_summary(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationSummary:
    return await service.summary(user.uid)


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Track a new application",
)
async def create_application(
    payload: ApplicationCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.create(user.uid, payload)


@router.get("/{app_id}", response_model=ApplicationOut, summary="One application")
async def get_application(
    app_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.get(user.uid, app_id)


@router.patch("/{app_id}", response_model=ApplicationOut, summary="Update an application")
async def update_application(
    app_id: str,
    payload: ApplicationUpdate,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    webhooks: WebhookService = Depends(get_webhook_service),
    push: PushService = Depends(get_push_service),
) -> ApplicationOut:
    app = await service.update(user.uid, app_id, payload)
    # Fire-and-forget notifications on a status change (runs after the response).
    if payload.status is not None:
        event_data = {
            "application_id": app.id,
            "company": app.company,
            "role": app.role,
            "status": app.status,
        }
        background.add_task(
            webhooks.dispatch, user.uid, "application.status_changed", event_data
        )
        background.add_task(
            push.send_to_user,
            user.uid,
            title="Application updated",
            body=f"{app.role} at {app.company} → {app.status}",
            url="/applications",
        )
    return app


@router.delete(
    "/{app_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an application"
)
async def delete_application(
    app_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> None:
    await service.delete(user.uid, app_id)


@router.post(
    "/{app_id}/tailor-cv",
    response_model=ApplicationOut,
    summary="Generate a tailored CV rewrite",
)
async def tailor_cv(
    app_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.tailor_cv(user.uid, app_id)


@router.post(
    "/{app_id}/cover-letter",
    response_model=ApplicationOut,
    summary="Generate a tailored cover letter",
)
async def cover_letter(
    app_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.cover_letter(user.uid, app_id)


@router.put(
    "/{app_id}/stage-notes/{stage}",
    response_model=ApplicationOut,
    summary="Set a per-stage note",
)
async def set_stage_note(
    app_id: str,
    stage: str,
    payload: StageNoteUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.set_stage_note(user.uid, app_id, stage, payload.note)


@router.post(
    "/{app_id}/reminders",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a follow-up reminder",
)
async def add_reminder(
    app_id: str,
    payload: ReminderCreate,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    push: PushService = Depends(get_push_service),
) -> ApplicationOut:
    app = await service.add_reminder(user.uid, app_id, payload)
    background.add_task(
        push.send_to_user,
        user.uid,
        title="Reminder set",
        body=f"{payload.title} — {app.role} at {app.company}",
        url="/applications",
    )
    return app


class ReminderDonePatch(BaseModel):
    done: bool = True


@router.patch(
    "/{app_id}/reminders/{reminder_id}",
    response_model=ApplicationOut,
    summary="Mark a reminder done/undone",
)
async def update_reminder(
    app_id: str,
    reminder_id: str,
    payload: ReminderDonePatch,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.set_reminder_done(user.uid, app_id, reminder_id, payload.done)


@router.delete(
    "/{app_id}/reminders/{reminder_id}",
    response_model=ApplicationOut,
    summary="Remove a reminder",
)
async def delete_reminder(
    app_id: str,
    reminder_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.delete_reminder(user.uid, app_id, reminder_id)
