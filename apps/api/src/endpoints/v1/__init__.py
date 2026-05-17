"""API v1 router — aggregates all v1 controllers."""
from fastapi import APIRouter

from src.endpoints.v1.admin_kb_controller import router as admin_kb_router
from src.endpoints.v1.auth_controller import router as auth_router
from src.endpoints.v1.coach_controller import router as coach_router
from src.endpoints.v1.cv_controller import router as cv_router
from src.endpoints.v1.intake_controller import router as intake_router
from src.endpoints.v1.opportunity_controller import router as opportunity_router
from src.endpoints.v1.orchestrator_controller import router as orchestrator_router
from src.endpoints.v1.roadmap_controller import router as roadmap_router
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
