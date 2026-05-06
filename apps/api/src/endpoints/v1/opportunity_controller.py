"""Opportunity — HTTP endpoint for on-demand job opportunity matching.

POST /api/v1/opportunity/search
    Dispatches an ``opportunity_search`` orchestration task with
    ``forced_intent="opportunity_search"`` to bypass intent classification and
    run the OpportunityAgent directly.  Returns immediately with ``request_id``
    and ``stream_channel`` for SSE subscription.

GET /api/v1/opportunity/alerts
    Returns the most recent match alerts and target companies cached in the
    session plan context from the last opportunity search or roadmap run.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agents.bus.channel import channel_for_session
from agents.bus.publisher import TaskPublisher
from agents.contracts.tasks import OrchestratorTaskInput, UserProfileSnapshot
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger
from src.session.manager import SessionManager, get_session_manager
from src.session.models import UserProfileContext

router = APIRouter(prefix="/opportunity", tags=["opportunity"])
logger = get_logger(__name__)

_task_publisher = TaskPublisher()


# ── Schemas ───────────────────────────────────────────────────────────────────


class OpportunitySearchRequest(BaseModel):
    role: str | None = Field(
        default=None,
        description="Override target role for this search. Defaults to the session's target_role.",
        max_length=200,
    )
    location: str | None = Field(
        default=None,
        description="Override search location. Defaults to the session's location.",
        max_length=200,
    )


class OpportunitySearchResponse(BaseModel):
    request_id: str
    session_id: str
    stream_channel: str
    search_query: str
    message: str = "Opportunity search started. Subscribe to the stream for live output."


class AlertsResponse(BaseModel):
    alerts: list[str]
    target_companies: list[dict]
    high_match_count: int
    search_query: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/search",
    response_model=OpportunitySearchResponse,
    status_code=202,
    summary="Search for matching job opportunities",
)
async def search_opportunities(
    body: OpportunitySearchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> OpportunitySearchResponse:
    """Dispatch a standalone opportunity search.

    Sets ``forced_intent="opportunity_search"`` so the intent parser is
    bypassed and the OpportunityAgent runs directly.  Optional ``role`` and
    ``location`` overrides take precedence over session-stored profile values
    for this request only — the session profile itself is not modified.
    """
    session = await mgr.get_or_create(user.uid, user.email)
    stream_channel = channel_for_session(user.uid, session.user_id)

    profile_snapshot = _build_profile_snapshot(
        ctx=session.user_profile_context,
        role_override=body.role,
        location_override=body.location,
    )
    search_query = profile_snapshot.target_role or ""

    task_input = OrchestratorTaskInput(
        session_id=session.user_id,
        user_id=user.uid,
        user_message=f"Find matching job opportunities for {search_query or 'my target role'}",
        user_profile=profile_snapshot,
        stream_channel=stream_channel,
        forced_intent="opportunity_search",
    )

    try:
        task_id = _task_publisher.dispatch_orchestration(task_input)
    except Exception as exc:
        logger.error(
            "opportunity.dispatch_failed",
            error=str(exc),
            user_id=user.uid,
        )
        raise ExternalServiceError(
            "Failed to start opportunity search. Please try again."
        ) from exc

    logger.info(
        "opportunity.search_dispatched",
        task_id=task_id,
        user_id=user.uid,
        session_id=session.user_id,
        search_query=search_query,
    )

    return OpportunitySearchResponse(
        request_id=task_id,
        session_id=session.user_id,
        stream_channel=stream_channel,
        search_query=search_query,
    )


@router.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="Get latest match alerts from the most recent opportunity search",
)
async def get_opportunity_alerts(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
) -> AlertsResponse:
    """Return cached match alerts from the session's plan context.

    Opportunity data lands in ``plan_context.snapshot`` after a roadmap
    generation or standalone search.  Two lookup paths are tried in priority
    order:
    1. ``snapshot["opportunity"]`` — direct key written by the synthesiser for
       standalone ``opportunity_search`` runs.
    2. ``snapshot["agent_outputs"]["opportunity"]`` — raw aggregated form used
       when the synthesiser falls back to the full aggregated dict (e.g. on
       an LLM error during synthesis).

    Returns empty lists when no cached data exists — never raises 404.
    """
    session = await mgr.get(user.uid)
    if not session or not session.plan_context:
        return AlertsResponse(alerts=[], target_companies=[], high_match_count=0)

    snapshot = session.plan_context.snapshot
    opp_data: dict = (
        snapshot.get("opportunity")
        or snapshot.get("agent_outputs", {}).get("opportunity")
        or {}
    )

    return AlertsResponse(
        alerts=list(opp_data.get("match_alerts", [])),
        target_companies=list(opp_data.get("target_companies", [])),
        high_match_count=len(opp_data.get("high_match_jobs", [])),
        search_query=opp_data.get("search_query"),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_profile_snapshot(
    ctx: UserProfileContext | None,
    role_override: str | None,
    location_override: str | None,
) -> UserProfileSnapshot:
    """Build a profile snapshot, applying any per-request overrides."""
    if ctx is None:
        return UserProfileSnapshot(
            target_role=role_override,
            location=location_override,
        )
    return UserProfileSnapshot(
        target_role=role_override or ctx.target_role,
        current_role=ctx.current_role,
        skills=list(ctx.skills),
        goals=list(ctx.goals),
        constraints=list(ctx.constraints),
        location=location_override or ctx.location,
        timeline_months=ctx.timeline_months,
        weekly_hours_available=ctx.weekly_hours_available,
        salary_goal=ctx.salary_goal,
        additional=dict(ctx.additional),
    )
