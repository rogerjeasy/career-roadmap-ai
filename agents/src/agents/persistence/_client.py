"""Shared Firestore async client factory for agent-side persistence.

Both ``FirestoreRoadmapStore`` and the upload Celery task use this so
credential resolution lives in exactly one place.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud.firestore_v1.async_client import AsyncClient


async def make_async_client(
    project: str,
    credentials_json: str | None = None,
    credentials_path: str | None = None,
) -> "AsyncClient":
    """Build an ``AsyncClient`` from explicit credentials or fall back to ADC.

    Priority:
      1. ``credentials_json``  — full service-account JSON as a string
      2. ``credentials_path``  — path to service-account JSON file
      3. Application Default Credentials (GKE / Cloud Run workload identity)
    """
    from google.cloud.firestore_v1.async_client import AsyncClient  # noqa: PLC0415

    if credentials_json:
        from google.oauth2 import service_account  # noqa: PLC0415
        info = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(info)
        return AsyncClient(project=project, credentials=creds)

    if credentials_path:
        from google.oauth2 import service_account  # noqa: PLC0415
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        return AsyncClient(project=project, credentials=creds)

    return AsyncClient(project=project)
