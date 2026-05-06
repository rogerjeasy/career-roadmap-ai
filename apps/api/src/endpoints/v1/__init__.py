"""API v1 router — aggregates all v1 controllers."""
from fastapi import APIRouter

from src.endpoints.v1.auth_controller import router as auth_router
from src.endpoints.v1.orchestrator_controller import router as orchestrator_router
from src.endpoints.v1.session_controller import router as session_router
from src.endpoints.v1.stream_controller import router as stream_router
from src.endpoints.v1.user_controller import router as user_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(session_router)
router.include_router(orchestrator_router)
router.include_router(stream_router)
