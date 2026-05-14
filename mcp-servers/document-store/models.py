"""Pydantic models for the Document Store MCP server."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    CV = "cv"
    PORTFOLIO = "portfolio"
    CERTIFICATE = "certificate"
    COVER_LETTER = "cover_letter"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class StoredDocument(BaseModel):
    """Metadata record returned for every document operation."""
    document_id: str
    user_id: str
    filename: str
    document_type: DocumentType
    content_type: str                    # MIME type e.g. "application/pdf"
    size_bytes: int
    storage_path: str                    # Provider-specific path (opaque to callers)
    download_url: str | None = None      # Pre-signed / direct URL; None for local (no public URL)
    created_at: str                      # ISO-8601 UTC
    updated_at: str                      # ISO-8601 UTC
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_dump_api(self) -> dict[str, Any]:
        return self.model_dump()


# ── Request params ────────────────────────────────────────────────────────────

class UploadDocumentParams(BaseModel):
    user_id: str = Field(description="Authenticated user ID")
    filename: str = Field(description="Original filename including extension", max_length=255)
    document_type: DocumentType = Field(description="Document category")
    content_type: str = Field(
        description="MIME type of the document (e.g. 'application/pdf')",
        default="application/octet-stream",
    )
    content_base64: str = Field(
        description="Base64-encoded file content. Max decoded size 10 MB.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional user-defined metadata (e.g. {'language': 'en', 'target_role': 'SWE'})",
    )


class GetDocumentParams(BaseModel):
    user_id: str = Field(description="Authenticated user ID")
    document_id: str = Field(description="Document ID returned by upload_document")
    include_content: bool = Field(
        default=False,
        description="If true, include base64-encoded file content in the response",
    )


class ListDocumentsParams(BaseModel):
    user_id: str = Field(description="Authenticated user ID")
    document_type: DocumentType | None = Field(
        default=None,
        description="Filter by document type. Omit to list all types.",
    )
    limit: int = Field(default=20, ge=1, le=100)


class DeleteDocumentParams(BaseModel):
    user_id: str = Field(description="Authenticated user ID")
    document_id: str = Field(description="Document ID to delete")
