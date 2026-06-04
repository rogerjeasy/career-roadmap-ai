"""API v1 router — aggregates all v1 controllers."""
from fastapi import APIRouter

from src.endpoints.v1.admin_kb_controller import router as admin_kb_router
from src.endpoints.v1.auth_controller import router as auth_router
from src.endpoints.v1.books_controller import router as books_router
from src.endpoints.v1.coach_controller import router as coach_router
from src.endpoints.v1.cv_controller import router as cv_router
from src.endpoints.v1.intake_controller import router as intake_router
from src.endpoints.v1.integrations_controller import router as integrations_router
from src.endpoints.v1.market_controller import router as market_router
from src.endpoints.v1.monthly_plan_controller import router as monthly_plan_router
from src.endpoints.v1.networking_controller import router as networking_router
from src.endpoints.v1.notification_controller import router as notification_router
from src.endpoints.v1.opportunity_controller import router as opportunity_router
from src.endpoints.v1.orchestrator_controller import router as orchestrator_router
from src.endpoints.v1.progress_controller import router as progress_router
from src.endpoints.v1.roadmap_controller import router as roadmap_router
from src.endpoints.v1.schedule_controller import router as schedule_router
from src.endpoints.v1.session_controller import router as session_router
from src.endpoints.v1.stream_controller import router as stream_router
from src.endpoints.v1.user_controller import router as user_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(session_router)
router.include_router(orchestrator_router)
router.include_router(stream_router)
router.include_router(coach_router)
router.include_router(cv_router)
router.include_router(intake_router)
router.include_router(opportunity_router)
router.include_router(roadmap_router)
router.include_router(admin_kb_router)
router.include_router(market_router)
router.include_router(networking_router)
router.include_router(progress_router)
router.include_router(schedule_router)
router.include_router(monthly_plan_router)
router.include_router(books_router)
router.include_router(notification_router)
router.include_router(integrations_router)
