"""API v1 router — aggregates all v1 controllers."""
from fastapi import APIRouter

from src.endpoints.v1.auth_controller import router as auth_router
from src.endpoints.v1.user_controller import router as user_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(user_router)
