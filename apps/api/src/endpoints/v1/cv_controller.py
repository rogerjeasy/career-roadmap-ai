"""CV controller — upload and parse a CV/resume document.

POST /api/v1/cv/upload
    Phase 1 (sync)  — validates the file, extracts structured profile data
                      via Claude, and returns the result immediately.
    Phase 1b (sync) — extracts raw text from the file and stores it in the
                      session so the CV agent can access it during pipeline runs.
    Phase 2 (async) — dispatches a Celery task that uploads the file to
                      Cloudinary and writes the asset record to Firestore.
                      The caller does NOT need to wait for this.

Supported formats: PDF · DOCX · TXT · MD (max 10 MB).
"""
import base64
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from agents.bus.upload_tasks import (
    UploadTaskPayload,
    cloudinary_folder,
    detect_content_type,
    resource_type_for,
    upload_to_cloudinary,
)
from agents.cv_analysis.pdf_parser import PDFParser
from src.config import settings
from src.core.auth import AuthenticatedUser, get_current_user
from src.core.logging import get_logger
from src.db.http import get_http_client
from src.domains.cv.schemas import (
    CvAnalysisResult,
    CvImportUrlRequest,
    CvUploadResponse,
)
from src.domains.cv.service import CvService, get_cv_service
from src.domains.cv.url_import import (
    ALLOWED_EXTS as _URL_ALLOWED_EXTS,
    UrlImportError,
    fetch_remote_document,
)
from src.session.manager import SessionManager, get_session_manager
from src.session.models import UserProfileContext

router = APIRouter(prefix="/cv", tags=["cv"])
logger = get_logger(__name__)

_ALLOWED_EXTS = {"pdf", "docx", "txt", "md"}
_pdf_parser = PDFParser()


def _extract_raw_text(data: bytes, ext: str) -> str:
    """Extract plain text from uploaded file bytes without calling an LLM."""
    if ext == "pdf":
        return _pdf_parser.extract_text(data)
    if ext == "docx":
        return CvService._extract_docx_text(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload",
    response_model=CvUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and analyse a CV document",
)
async def upload_cv(
    file: UploadFile,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CvService = Depends(get_cv_service),
    mgr: SessionManager = Depends(get_session_manager),
) -> CvUploadResponse:
    """Parse a CV and enqueue a background Cloudinary upload.

    **Phase 1 (sync):** Claude extracts roles, skills, projects, education,
    years of experience, leadership signals, and a one-sentence summary.
    The parsed result is returned in the response body immediately.

    **Phase 2 (async):** The raw file bytes are dispatched to a Celery worker
    that uploads the document to Cloudinary and records the asset URL in
    Firestore (``uploads/{upload_id}``).  The response includes ``upload_id``
    so the caller can track storage status if needed.

    After receiving this response the client should also call
    ``PATCH /api/v1/session/user-profile`` to persist the extracted data into
    the active session context.
    """
    filename = file.filename or "upload.bin"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '.{ext}'. Allowed: PDF, DOCX, TXT, MD.",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File exceeds the 10 MB limit.",
        )

    logger.info(
        "cv.upload_received",
        user_id=user.uid,
        filename=filename,
        size_bytes=len(data),
    )

    return await _analyse_and_store(
        data=data,
        filename=filename,
        ext=ext,
        content_type_hint=file.content_type,
        user=user,
        service=service,
        mgr=mgr,
    )


@router.post(
    "/import-url",
    response_model=CvUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Import and analyse a CV from a public URL",
)
async def import_cv_from_url(
    body: CvImportUrlRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CvService = Depends(get_cv_service),
    mgr: SessionManager = Depends(get_session_manager),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> CvUploadResponse:
    """Fetch a CV from a public link, then run the same analysis as an upload.

    The document is downloaded server-side with SSRF protection (public-host
    check, manual redirect re-validation, capped streaming). Once fetched, the
    bytes flow through the identical parse → session-store → Cloudinary path,
    so a URL import is indistinguishable from a file upload downstream.
    """
    url = str(body.url)
    try:
        data, filename = await fetch_remote_document(url, http_client)
    except UrlImportError as exc:
        logger.info("cv.url_import_rejected", user_id=user.uid, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _URL_ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported document type. Link to a PDF, DOCX, TXT, or MD file.",
        )

    logger.info(
        "cv.url_import_received",
        user_id=user.uid,
        filename=filename,
        size_bytes=len(data),
    )

    return await _analyse_and_store(
        data=data,
        filename=filename,
        ext=ext,
        content_type_hint=None,
        user=user,
        service=service,
        mgr=mgr,
    )


async def _analyse_and_store(
    *,
    data: bytes,
    filename: str,
    ext: str,
    content_type_hint: str | None,
    user: AuthenticatedUser,
    service: CvService,
    mgr: SessionManager,
) -> CvUploadResponse:
    """Shared CV pipeline used by both file-upload and URL-import.

    Phase 1 — synchronous Claude analysis (the primary returned value).
    Phase 1b — persist extracted text into the session for the CV agent.
    Phase 2 — fire-and-forget Cloudinary upload (failures are non-fatal).
    """
    # ── Phase 1: synchronous CV analysis ──────────────────────────────────────
    try:
        result: CvAnalysisResult = await service.parse_upload(data, filename)
    except Exception as exc:
        logger.error("cv.parse_failed", user_id=user.uid, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CV parsing failed — please try again.",
        ) from exc

    logger.info(
        "cv.parse_complete",
        user_id=user.uid,
        roles=len(result.roles),
        skills=len(result.skills),
        years=result.years_of_experience,
    )

    # ── Phase 1b: persist raw CV text in the session ──────────────────────────
    # The CV agent reads cv_document from plan_snapshot["cv"], which is only
    # populated when the agent pipeline already has CV bytes. As a reliable
    # fallback, we store the extracted text in user_profile.additional["cv_text"]
    # so the CV agent can use it regardless of how the pipeline is invoked.
    try:
        cv_text = _extract_raw_text(data, ext)
        if cv_text:
            session = await mgr.get_or_create(user.uid, user.email)
            profile = session.user_profile_context or UserProfileContext()
            profile.additional["cv_text"] = cv_text[:14_000]  # match LLM context cap
            profile.additional["career_path_suggestions"] = result.career_path_suggestions
            await mgr.set_user_profile_context(user.uid, profile, user.email)
            logger.info(
                "cv.text_stored_in_session",
                user_id=user.uid,
                cv_text_length=len(cv_text),
            )
    except Exception as exc:
        # Non-fatal — the structured analysis result is still returned
        logger.warning("cv.text_session_store_failed", user_id=user.uid, error=str(exc))

    # ── Phase 2: fire-and-forget Cloudinary upload ────────────────────────────
    upload_id = str(uuid4())
    content_type = detect_content_type(filename, content_type_hint)
    rtype = resource_type_for(content_type)
    folder = cloudinary_folder(settings.cloudinary_upload_folder, "cvs", user.uid)

    task_payload = UploadTaskPayload(
        upload_id=upload_id,
        user_id=user.uid,
        filename=filename,
        content_type=content_type,
        resource_type=rtype,
        folder_path=folder,
        file_b64=base64.b64encode(data).decode(),
        size_bytes=len(data),
        tags=["cv", user.uid],
    )

    try:
        upload_to_cloudinary.delay(task_payload.model_dump())
        logger.info(
            "cv.upload_dispatched",
            upload_id=upload_id,
            user_id=user.uid,
            resource_type=rtype,
            folder=folder,
        )
    except Exception as exc:
        # Background upload failure must NOT fail the request — the analysis
        # result has already been computed and is the primary value returned.
        logger.error(
            "cv.upload_dispatch_failed",
            upload_id=upload_id,
            user_id=user.uid,
            error=str(exc),
        )

    return CvUploadResponse(analysis=result, upload_id=upload_id)
