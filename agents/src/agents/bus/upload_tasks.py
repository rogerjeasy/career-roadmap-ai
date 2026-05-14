"""Background Celery tasks for uploading user media to Cloudinary.

Upload flow:
  1. API endpoint receives a file, processes it synchronously (e.g. Claude CV
     parse), and immediately returns the result to the caller.
  2. The API dispatches ``upload_to_cloudinary`` as a fire-and-forget Celery
     task, passing the file as base64-encoded bytes in the JSON payload.
  3. A worker decodes the bytes, uploads to Cloudinary with the correct
     resource type, and persists the upload record to Firestore.

Supported resource types and automatic routing:
  "raw"   → PDFs, DOCX, TXT, MD — stored verbatim, no transformations
  "image" → JPG, PNG, GIF, WebP  — Cloudinary image pipeline available
  "video" → MP4, MOV, AVI        — Cloudinary transcoding available

Cloudinary folder layout (base comes from CLOUDINARY_UPLOAD_FOLDER):
  {base}/cvs/{user_id}/{upload_id}
  {base}/images/{user_id}/{upload_id}
  {base}/videos/{user_id}/{upload_id}
  {base}/documents/{user_id}/{upload_id}

Firestore collection ``uploads/{upload_id}``:
  user_id, filename, content_type, resource_type, size_bytes,
  public_id, secure_url, status (uploaded|failed), error, timestamps.

Observability:
  - OTel span:  storage.upload_to_cloudinary
  - Prometheus: career_agents_file_upload_total  (resource_type × status)
                career_agents_file_upload_duration_seconds (resource_type)
                career_agents_file_upload_size_bytes       (resource_type)
  - structlog:  upload.task.started / completed / failed
  - Sentry:     automatic exception capture on final failure
"""
from __future__ import annotations

import asyncio
import base64
import io
import time
from datetime import datetime, timezone

from celery import Task
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

from agents.bus.celery_app import celery_app
from agents.config import agent_settings
from agents.core.logging import configure_agent_logging, get_logger
from agents.core.observability import (
    FILE_UPLOAD_DURATION,
    FILE_UPLOAD_SIZE_BYTES,
    FILE_UPLOAD_TOTAL,
    get_tracer,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.bus.upload_tasks")


# ── Payload schema ────────────────────────────────────────────────────────────

class UploadTaskPayload(BaseModel):
    """Validated payload consumed by the ``upload_to_cloudinary`` Celery task.

    The API side constructs this (or an equivalent dict) before calling
    ``upload_to_cloudinary.delay(payload.model_dump())``.
    """
    upload_id: str
    user_id: str
    filename: str
    content_type: str
    resource_type: str    # "raw" | "image" | "video"
    folder_path: str      # full Cloudinary folder, e.g. "career-roadmap/dev/cvs/uid"
    file_b64: str         # base64-encoded file bytes
    size_bytes: int
    tags: list[str] = Field(default_factory=list)


# ── Media uploader ────────────────────────────────────────────────────────────

class _MediaUploader:
    """Thin async wrapper around the Cloudinary SDK.

    Unlike ``CloudinaryClient`` (which is RAG-only and hard-codes
    resource_type="raw"), this class routes to the correct Cloudinary
    pipeline based on ``resource_type``.

    Constructed once per task execution — the SDK uses a module-level
    config singleton, so calling ``cloudinary.config()`` is idempotent.
    """

    def __init__(self) -> None:
        try:
            import cloudinary  # type: ignore[import-untyped]
            import cloudinary.uploader  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "cloudinary package is required. Add it to pyproject.toml."
            ) from exc

        if not agent_settings.cloudinary_cloud_name:
            raise RuntimeError("CLOUDINARY_CLOUD_NAME is not configured")

        cloudinary.config(
            cloud_name=agent_settings.cloudinary_cloud_name,
            api_key=agent_settings.cloudinary_api_key.get_secret_value()
            if agent_settings.cloudinary_api_key else "",
            api_secret=agent_settings.cloudinary_api_secret.get_secret_value()
            if agent_settings.cloudinary_api_secret else "",
            secure=True,
        )
        self._uploader = cloudinary.uploader

    async def upload(
        self,
        data: bytes,
        *,
        resource_type: str,
        folder: str,
        public_id: str,
        tags: list[str],
    ) -> dict:
        """Upload ``data`` to Cloudinary asynchronously (offloads sync SDK call).

        ``overwrite=False`` prevents accidentally clobbering an asset if the
        task is retried after a partial failure.
        """
        options: dict = {
            "folder": folder,
            "public_id": public_id,
            "resource_type": resource_type,
            "tags": tags,
            "overwrite": False,
        }
        return await asyncio.to_thread(
            self._uploader.upload,
            io.BytesIO(data),
            **options,
        )


# ── Firestore upload record ───────────────────────────────────────────────────

async def _persist_upload_record(
    payload: UploadTaskPayload,
    *,
    status: str,
    public_id: str | None = None,
    secure_url: str | None = None,
    error: str | None = None,
) -> None:
    """Write or overwrite the upload record in Firestore ``uploads`` collection.

    Called twice per task execution:
      - On success: status="uploaded" with public_id + secure_url
      - On failure: status="failed" with error message

    On retry the previous "failed" write is overwritten when the next attempt
    succeeds, so the document always reflects the most recent outcome.

    Firestore persistence is best-effort — a write failure here must never
    cause the Celery task to fail or retry, since the file is already on
    Cloudinary.
    """
    if not agent_settings.firestore_persistence_enabled:
        return
    if not agent_settings.firebase_project_id:
        return

    try:
        from agents.persistence._client import make_async_client  # noqa: PLC0415

        db = await make_async_client(
            project=agent_settings.firebase_project_id,
            credentials_json=agent_settings.firebase_credentials_json,
            credentials_path=agent_settings.firebase_credentials_path,
        )
        now = datetime.now(timezone.utc)
        await db.collection("uploads").document(payload.upload_id).set({
            "upload_id": payload.upload_id,
            "user_id": payload.user_id,
            "filename": payload.filename,
            "content_type": payload.content_type,
            "resource_type": payload.resource_type,
            "size_bytes": payload.size_bytes,
            "folder_path": payload.folder_path,
            "tags": payload.tags,
            "public_id": public_id,
            "secure_url": secure_url,
            "status": status,
            "error": error,
            "created_at": now,
            "completed_at": now if status in ("uploaded", "failed") else None,
        })
    except Exception as exc:
        logger.warning(
            "upload.firestore_save_failed",
            upload_id=payload.upload_id,
            error=str(exc),
        )


# ── Celery task ───────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="agents.bus.upload_tasks.upload_to_cloudinary",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def upload_to_cloudinary(self: Task, payload: dict) -> dict:
    """Upload a user file to Cloudinary and record the result in Firestore.

    Receives base64-encoded file bytes so the Celery message is standard JSON.
    For the 10 MB max file size the payload is ~13.3 MB — well within Redis limits.

    Retry policy: up to 3 attempts with 30-second back-off.
    On final failure the task raises so Celery marks it FAILURE and Sentry captures it.
    """
    configure_agent_logging()
    task_payload = UploadTaskPayload.model_validate(payload)

    log = logger.bind(
        upload_id=task_payload.upload_id,
        user_id=task_payload.user_id,
        resource_type=task_payload.resource_type,
        filename=task_payload.filename,
        size_bytes=task_payload.size_bytes,
    )
    log.info("upload.task.started")

    async def _run() -> dict:
        # Skip silently when Cloudinary is not configured for this environment.
        # Retrying a configuration error is pointless and blocks the worker queue.
        if not agent_settings.cloudinary_cloud_name:
            log.info("upload.task.skipped", reason="cloudinary_not_configured")
            return {"upload_id": task_payload.upload_id, "skipped": True}

        t0 = time.monotonic()

        with _tracer.start_as_current_span("storage.upload_to_cloudinary") as span:
            span.set_attribute("upload_id", task_payload.upload_id)
            span.set_attribute("user_id", task_payload.user_id)
            span.set_attribute("resource_type", task_payload.resource_type)
            span.set_attribute("filename", task_payload.filename)
            span.set_attribute("size_bytes", task_payload.size_bytes)

            try:
                file_bytes = base64.b64decode(task_payload.file_b64)

                uploader = _MediaUploader()
                result = await uploader.upload(
                    file_bytes,
                    resource_type=task_payload.resource_type,
                    folder=task_payload.folder_path,
                    public_id=task_payload.upload_id,
                    tags=task_payload.tags,
                )

                duration = time.monotonic() - t0
                FILE_UPLOAD_DURATION.labels(
                    resource_type=task_payload.resource_type
                ).observe(duration)
                FILE_UPLOAD_SIZE_BYTES.labels(
                    resource_type=task_payload.resource_type
                ).observe(task_payload.size_bytes)
                FILE_UPLOAD_TOTAL.labels(
                    resource_type=task_payload.resource_type,
                    status="success",
                ).inc()

                span.set_attribute("public_id", result["public_id"])
                span.set_attribute("secure_url", result["secure_url"])
                span.set_status(Status(StatusCode.OK))

                await _persist_upload_record(
                    task_payload,
                    status="uploaded",
                    public_id=result["public_id"],
                    secure_url=result["secure_url"],
                )

                log.info(
                    "upload.task.completed",
                    public_id=result["public_id"],
                    duration_ms=int(duration * 1000),
                )
                return {
                    "upload_id": task_payload.upload_id,
                    "public_id": result["public_id"],
                    "secure_url": result["secure_url"],
                    "resource_type": task_payload.resource_type,
                    "size_bytes": task_payload.size_bytes,
                }

            except Exception as exc:
                duration = time.monotonic() - t0
                FILE_UPLOAD_DURATION.labels(
                    resource_type=task_payload.resource_type
                ).observe(duration)
                FILE_UPLOAD_TOTAL.labels(
                    resource_type=task_payload.resource_type,
                    status="error",
                ).inc()

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

                await _persist_upload_record(
                    task_payload,
                    status="failed",
                    error=str(exc),
                )

                log.error(
                    "upload.task.failed",
                    error=str(exc),
                    attempt=self.request.retries + 1,
                    max_retries=self.max_retries,
                    exc_info=True,
                )
                # Don't retry configuration errors — they won't self-heal.
                if isinstance(exc, (ImportError, RuntimeError)):
                    raise
                raise self.retry(exc=exc) from exc

    return asyncio.run(_run())


# ── Helpers used by the API layer ─────────────────────────────────────────────

_CONTENT_TYPE_MAP: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "txt": "text/plain",
    "md": "text/markdown",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "mkv": "video/x-matroska",
}

_RESOURCE_TYPE_MAP: dict[str, str] = {
    "image/": "image",
    "video/": "video",
}


def detect_content_type(filename: str, declared: str | None) -> str:
    """Return the most reliable content-type for a file.

    Prefers the declared content-type from the HTTP multipart header unless
    it is the generic ``application/octet-stream`` fallback, in which case
    the extension is used.
    """
    if declared and declared != "application/octet-stream":
        return declared
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _CONTENT_TYPE_MAP.get(ext, "application/octet-stream")


def resource_type_for(content_type: str) -> str:
    """Return the Cloudinary resource_type for a given MIME type."""
    for prefix, rtype in _RESOURCE_TYPE_MAP.items():
        if content_type.startswith(prefix):
            return rtype
    return "raw"


def cloudinary_folder(base: str, category: str, user_id: str) -> str:
    """Build a scoped Cloudinary folder path.

    ``category`` is a short noun: ``cvs``, ``images``, ``videos``, ``documents``.
    """
    return f"{base}/{category}/{user_id}"
