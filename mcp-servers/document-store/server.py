"""Document Store MCP Server — entry point.

Exposes four JSON-RPC 2.0 methods:
  upload_document   — store a base64-encoded document (PDF, DOCX, etc.)
  get_document      — retrieve document metadata (and optionally content)
  list_documents    — list all documents for a user (filterable by type)
  delete_document   — permanently delete a document

Transport: HTTP POST to / (JSON-RPC 2.0)
Health:    GET /livez, GET /readyz
Metrics:   GET /metrics (Prometheus)

Storage backend is selected via BLOB_STORAGE_PROVIDER env var:
  local  — files on local disk (default, good for dev/test)
  azure  — Azure Blob Storage
  s3     — AWS S3 or S3-compatible (e.g. localstack, minio)

Run (from mcp-servers/document-store/):
    uvicorn server:app --host 0.0.0.0 --port 3009
"""
from __future__ import annotations

import os
import sys

_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)

import json
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from clients.base_client import BaseStorageClient
from config import get_settings
from tools.delete_document import handle_delete_document
from tools.get_document import handle_get_document
from tools.list_documents import handle_list_documents
from tools.upload_document import handle_upload_document
from shared.auth import verify_api_key
from shared.base_server import (
    CorrelationIdMiddleware,
    _attach_trace_context,
    _configure_logging,
    _configure_sentry,
    _configure_tracing,
)
from shared.error_handler import (
    JsonRpcError,
    JsonRpcErrorCode,
    make_error_response,
    make_success_response,
)
from shared.rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)

_settings = get_settings()


def _build_storage_client() -> BaseStorageClient:
    """Construct storage client from settings. Raises if configuration is incomplete."""
    provider = _settings.storage_provider

    if provider == "azure":
        from clients.azure_blob_client import AzureBlobStorageClient

        if not _settings.azure_storage_connection_string:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING is required for azure storage provider"
            )
        return AzureBlobStorageClient(
            connection_string=_settings.azure_storage_connection_string.get_secret_value(),
            container=_settings.azure_storage_container,
        )

    if provider == "cloudinary":
        from clients.cloudinary_client import CloudinaryStorageClient

        if not _settings.cloudinary_cloud_name or not _settings.cloudinary_api_key or not _settings.cloudinary_api_secret:
            raise RuntimeError(
                "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET "
                "are required for cloudinary storage provider"
            )
        return CloudinaryStorageClient(
            cloud_name=_settings.cloudinary_cloud_name,
            api_key=_settings.cloudinary_api_key.get_secret_value(),
            api_secret=_settings.cloudinary_api_secret.get_secret_value(),
            upload_folder=_settings.cloudinary_upload_folder,
        )

    # Default: local filesystem
    from clients.local_client import LocalStorageClient

    return LocalStorageClient(base_path=_settings.local_storage_path)


def create_app(
    *,
    storage: BaseStorageClient | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """
    Application factory — accepts pre-built dependencies for test injection.
    When called without arguments the production defaults are built at lifespan startup.
    """
    # Mutable containers so lifespan can swap in the real instances
    _state: dict[str, Any] = {
        "storage": storage,
        "rate_limiter": rate_limiter or RateLimiter(redis_url=_settings.redis_url),
        "ready": storage is not None,  # pre-injected = already ready
    }

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN001
        _configure_logging()
        _configure_sentry()
        _configure_tracing("document_store")

        rl: RateLimiter = _state["rate_limiter"]
        try:
            await rl.connect()
            logger.info("document_store.redis_connected")
        except Exception as exc:
            logger.warning("document_store.redis_unavailable", error=str(exc))

        if _state["storage"] is None:
            try:
                _state["storage"] = _build_storage_client()
                logger.info(
                    "document_store.storage_initialized",
                    provider=_settings.storage_provider,
                )
                _state["ready"] = True
            except Exception as exc:
                logger.error(
                    "document_store.storage_init_failed",
                    provider=_settings.storage_provider,
                    error=str(exc),
                )

        yield

        await rl.close()
        logger.info("document_store.shutdown")

    fastapi_app = FastAPI(
        title="MCP Document Store Server",
        version="0.1.0",
        description="JSON-RPC 2.0 document storage tool server for Career Roadmap AI",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    fastapi_app.add_middleware(CorrelationIdMiddleware, server_id="document_store")

    # ── health ─────────────────────────────────────────────────────────────────

    @fastapi_app.get("/livez", include_in_schema=False)
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @fastapi_app.get("/readyz", include_in_schema=False)
    async def readyz():  # noqa: ANN201
        storage_client: BaseStorageClient | None = _state.get("storage")
        storage_ok = False
        if storage_client is not None:
            try:
                storage_ok = await storage_client.health_check()
            except Exception:
                pass

        redis_ok = False
        try:
            rl = _state["rate_limiter"]
            if rl._client:
                await rl._client.ping()
                redis_ok = True
        except Exception:
            pass

        checks = {
            "storage": "ok" if storage_ok else "error",
            "redis": "ok" if redis_ok else "degraded",
        }
        overall = "ok" if storage_ok else "error"
        status_code = 200 if storage_ok else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall,
                "server_id": "document_store",
                "provider": _settings.storage_provider,
                "checks": checks,
            },
        )

    @fastapi_app.get("/metrics", include_in_schema=False)
    async def metrics():  # noqa: ANN201
        from fastapi.responses import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ── JSON-RPC dispatcher ────────────────────────────────────────────────────

    @fastapi_app.post("/", include_in_schema=False)
    async def rpc_endpoint(request: Request) -> JSONResponse:
        request_id = None
        method = ""
        try:
            body = await request.body()
            try:
                payload: dict[str, Any] = json.loads(body)
            except json.JSONDecodeError:
                return JSONResponse(
                    make_error_response(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error")
                )

            request_id = payload.get("id")
            method = str(payload.get("method", ""))
            params: dict[str, Any] = payload.get("params") or {}

            if payload.get("jsonrpc") != "2.0" or not method:
                return JSONResponse(
                    make_error_response(
                        request_id, JsonRpcErrorCode.INVALID_REQUEST, "Invalid JSON-RPC 2.0 request"
                    )
                )

            verify_api_key(x_mcp_api_key=request.headers.get("X-MCP-API-Key", ""))
            _attach_trace_context(request)

            storage_client: BaseStorageClient | None = _state.get("storage")
            if storage_client is None:
                return JSONResponse(
                    make_error_response(
                        request_id,
                        JsonRpcErrorCode.INTERNAL_ERROR,
                        "Storage backend not initialized — check server logs",
                    )
                )

            rl: RateLimiter = _state["rate_limiter"]

            common = dict(
                params=params,
                request=request,
                storage=storage_client,
                rate_limiter=rl,
                rate_limit=_settings.rate_limit_per_minute,
            )

            if method == "upload_document":
                result = await handle_upload_document(
                    **common,
                    max_file_size_bytes=_settings.max_file_size_mb * 1024 * 1024,
                    max_documents_per_user=_settings.max_documents_per_user,
                )
            elif method == "get_document":
                result = await handle_get_document(**common)
            elif method == "list_documents":
                result = await handle_list_documents(**common)
            elif method == "delete_document":
                result = await handle_delete_document(**common)
            else:
                return JSONResponse(
                    make_error_response(
                        request_id, JsonRpcErrorCode.METHOD_NOT_FOUND, f"Method '{method}' not found"
                    )
                )

            return JSONResponse(make_success_response(request_id, result))

        except JsonRpcError as exc:
            return JSONResponse(make_error_response(request_id, exc.code, exc.message, exc.data))
        except Exception as exc:
            logger.error("rpc.unhandled_error", method=method, error=str(exc), exc_info=True)
            return JSONResponse(
                make_error_response(request_id, JsonRpcErrorCode.INTERNAL_ERROR, "Internal server error")
            )

    return fastapi_app


# Module-level app instance for uvicorn
app = create_app()


def main() -> None:
    import os
    import uvicorn

    is_dev = _settings.environment == "development"
    workers = int(os.getenv("MCP_WORKERS", "1"))
    uvicorn.run(
        "server:app",
        host=_settings.host,
        port=_settings.port,
        reload=is_dev,
        workers=1 if is_dev else workers,
        log_level=_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
