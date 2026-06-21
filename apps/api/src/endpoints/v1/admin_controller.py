"""Admin controller — role-gated platform administration endpoints.

Every route depends on ``require_admin`` (Firebase custom claim ``role`` ∈
{admin, superadmin}), so the entire surface is unreachable to normal users. The
heavier knowledge-base / RAG operations reuse the same Celery tasks as the
machine-to-machine ``/admin/kb`` controller, but here they are gated by the
human admin's role instead of the static ``X-Admin-Api-Key``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.core.auth import AuthenticatedUser, require_admin
from src.core.logging import get_logger
from src.domains.admin.schemas import (
    AdminAuditItem,
    AdminContactItem,
    AdminFeedbackItem,
    AdminOverview,
    AdminUserDetail,
    AdminUserListResponse,
    BroadcastRequest,
    BroadcastResult,
    InboxStatusUpdate,
    NewsletterSubscriberItem,
    SystemHealth,
    UserRoleUpdate,
    UserStatusUpdate,
)
from src.domains.admin.service import AdminService, get_admin_service
from src.endpoints.v1.admin_kb_controller import (
    KBDocType,
    _DEFAULT_SOURCE_PATHS,
    _TASK_EXTRA_ARGS,
)

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger(__name__)


# ── Overview ────────────────────────────────────────────────────────────────────


@router.get("/overview", response_model=AdminOverview, summary="Platform overview")
async def get_overview(
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminOverview:
    return await service.get_overview()


# ── User directory ──────────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminUserListResponse, summary="List users")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserListResponse:
    return await service.list_users(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        status=status_filter,
    )


@router.get("/users/{uid}", response_model=AdminUserDetail, summary="Get a user")
async def get_user(
    uid: str,
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserDetail:
    return await service.get_user_detail(uid)


@router.patch(
    "/users/{uid}/role",
    response_model=AdminUserDetail,
    summary="Change a user's role",
)
async def update_user_role(
    uid: str,
    body: UserRoleUpdate,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserDetail:
    return await service.update_user_role(admin, uid, body.role)


@router.patch(
    "/users/{uid}/status",
    response_model=AdminUserDetail,
    summary="Activate or deactivate a user",
)
async def update_user_status(
    uid: str,
    body: UserStatusUpdate,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserDetail:
    return await service.update_user_status(admin, uid, body.is_active)


@router.delete(
    "/users/{uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user account",
)
async def delete_user(
    uid: str,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> None:
    await service.delete_user(admin, uid)


# ── Inbox: feedback + contact ───────────────────────────────────────────────────


@router.get("/feedback", response_model=list[AdminFeedbackItem], summary="List feedback")
async def list_feedback(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[AdminFeedbackItem]:
    return await service.list_feedback(status=status_filter, limit=limit)


@router.patch(
    "/feedback/{feedback_id}/status",
    response_model=AdminFeedbackItem,
    summary="Update feedback status",
)
async def update_feedback_status(
    feedback_id: str,
    body: InboxStatusUpdate,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminFeedbackItem:
    return await service.update_feedback_status(admin, feedback_id, body.status)


@router.get("/contact", response_model=list[AdminContactItem], summary="List contact requests")
async def list_contact(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[AdminContactItem]:
    return await service.list_contact(status=status_filter, limit=limit)


@router.patch(
    "/contact/{contact_id}/status",
    response_model=AdminContactItem,
    summary="Update contact request status",
)
async def update_contact_status(
    contact_id: str,
    body: InboxStatusUpdate,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminContactItem:
    return await service.update_contact_status(admin, contact_id, body.status)


# ── Newsletter + broadcast ──────────────────────────────────────────────────────


@router.get(
    "/newsletter/subscribers",
    response_model=list[NewsletterSubscriberItem],
    summary="List newsletter subscribers",
)
async def list_subscribers(
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[NewsletterSubscriberItem]:
    return await service.list_subscribers()


@router.post(
    "/broadcast",
    response_model=BroadcastResult,
    status_code=status.HTTP_201_CREATED,
    summary="Send a broadcast notification",
)
async def send_broadcast(
    body: BroadcastRequest,
    admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> BroadcastResult:
    return await service.broadcast(admin, body)


# ── Audit trail ─────────────────────────────────────────────────────────────────


@router.get("/audit", response_model=list[AdminAuditItem], summary="List admin audit log")
async def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[AdminAuditItem]:
    return await service.list_audit(limit=limit)


# ── System health + knowledge-base operations ───────────────────────────────────


@router.get("/system/health", response_model=SystemHealth, summary="System health")
async def system_health(
    _admin: AuthenticatedUser = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> SystemHealth:
    return await service.get_system_health()


class KbIngestRequest(BaseModel):
    doc_types: list[KBDocType] = Field(
        default_factory=list,
        description="Document types to ingest. Empty → ingest the full corpus.",
    )


class KbDispatchResponse(BaseModel):
    task_ids: list[str]
    doc_types: list[str]
    message: str


@router.post(
    "/system/kb/ingest",
    response_model=KbDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger knowledge-base ingestion",
)
async def kb_ingest(
    body: KbIngestRequest,
    admin: AuthenticatedUser = Depends(require_admin),
) -> KbDispatchResponse:
    from agents.rag.tasks.ingestion_tasks import (  # noqa: PLC0415
        ingest_career_kb,
        ingest_esco,
        ingest_global_market,
        ingest_market_reports,
        ingest_role_templates,
        ingest_swiss_eu_market,
    )

    task_map = {
        KBDocType.career_kb: ingest_career_kb,
        KBDocType.esco: ingest_esco,
        KBDocType.onet: ingest_esco,
        KBDocType.market_reports: ingest_market_reports,
        KBDocType.role_templates: ingest_role_templates,
        KBDocType.swiss_eu_market: ingest_swiss_eu_market,
        KBDocType.global_market: ingest_global_market,
    }
    types_to_run = body.doc_types or list(KBDocType)
    task_ids: list[str] = []
    for doc_type in types_to_run:
        source_path = _DEFAULT_SOURCE_PATHS[doc_type]
        extra_args = _TASK_EXTRA_ARGS.get(doc_type, [])
        async_result = task_map[doc_type].delay(source_path, *extra_args)
        task_ids.append(async_result.id)
        logger.info(
            "admin.kb.ingest_dispatched",
            doc_type=doc_type.value,
            task_id=async_result.id,
            actor_uid=admin.uid,
        )

    return KbDispatchResponse(
        task_ids=task_ids,
        doc_types=[d.value for d in types_to_run],
        message=f"Dispatched {len(task_ids)} ingestion task(s).",
    )


@router.get("/system/kb/status/{task_id}", summary="Poll a KB task")
async def kb_task_status(
    task_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict:
    from celery.result import AsyncResult  # noqa: PLC0415

    from agents.bus.celery_app import celery_app  # noqa: PLC0415

    result: AsyncResult = celery_app.AsyncResult(task_id)
    state = result.state
    if state == "SUCCESS":
        return {"task_id": task_id, "state": state, "result": result.result}
    if state == "FAILURE":
        return {"task_id": task_id, "state": state, "error": str(result.result)}
    return {"task_id": task_id, "state": state}


class EvalRunResponse(BaseModel):
    task_id: str
    queries_count: int
    message: str


@router.post(
    "/system/kb/eval/run",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the offline RAG eval pipeline",
)
async def kb_eval_run(
    admin: AuthenticatedUser = Depends(require_admin),
) -> EvalRunResponse:
    from agents.rag.eval.dataset import load_eval_dataset  # noqa: PLC0415
    from agents.rag.tasks.ingestion_tasks import run_eval_pipeline  # noqa: PLC0415

    queries = load_eval_dataset()
    async_result = run_eval_pipeline.apply_async(queue="agents.ingestion")
    logger.info("admin.kb.eval_dispatched", task_id=async_result.id, actor_uid=admin.uid)
    return EvalRunResponse(
        task_id=async_result.id,
        queries_count=len(queries),
        message=f"Eval task dispatched for {len(queries)} queries.",
    )


@router.get("/system/kb/eval/results", summary="Latest RAG eval results")
async def kb_eval_results(
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict:
    import json  # noqa: PLC0415

    import redis as _redis  # noqa: PLC0415

    from src.config import get_settings  # noqa: PLC0415

    _settings = get_settings()
    client = _redis.from_url(str(_settings.redis_url))
    try:
        raw = client.get("rag:eval:latest")
    finally:
        client.close()

    if raw is None:
        return {"found": False, "message": "No eval results yet. Run an eval first."}
    data = json.loads(raw)
    return {"found": True, **data}
