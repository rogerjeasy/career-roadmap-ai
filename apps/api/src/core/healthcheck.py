"""Liveness and readiness probes for Kong / Kubernetes."""
from fastapi import APIRouter, status
from sqlalchemy import text

from src.db.session import async_session_maker

router = APIRouter(tags=["health"])


@router.get("/livez", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """Process is alive — does not check dependencies."""
    return {"status": "alive"}


@router.get("/readyz", status_code=status.HTTP_200_OK)
async def readiness() -> dict[str, str]:
    """Process is ready to accept traffic — checks DB."""
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}