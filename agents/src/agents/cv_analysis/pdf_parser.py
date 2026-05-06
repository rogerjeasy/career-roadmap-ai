"""PDFParser — extract plain text from PDF bytes or file-like objects.

Wraps pypdf for text-layer extraction. Falls back to treating input as
UTF-8 plain text when pypdf fails or the source is not a valid PDF.

Design: stateless, injectable, zero LLM calls. Inject a subclass in tests.
"""
from __future__ import annotations

import io
import time
from typing import BinaryIO

from opentelemetry.trace import Status, StatusCode

from agents.core.logging import get_logger
from agents.core.observability import CV_PDF_PARSE_DURATION, get_tracer

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.pdf_parser")


class PDFParser:
    """Extract raw text from PDF documents.

    Inject a custom subclass or mock in tests to avoid real PDF processing.
    """

    def extract_text(
        self,
        source: bytes | BinaryIO | str,
        *,
        correlation_id: str = "",
    ) -> str:
        """Return the full text content of a CV document.

        Accepts:
        - ``str``      — already-extracted plain text (pass-through)
        - ``bytes``    — raw PDF bytes
        - ``BinaryIO`` — file-like object pointing to a PDF
        """
        with _tracer.start_as_current_span("cv.pdf_parse") as span:
            span.set_attribute("correlation_id", correlation_id)
            span.set_attribute("input_type", type(source).__name__)
            t0 = time.monotonic()

            if isinstance(source, str):
                CV_PDF_PARSE_DURATION.observe(time.monotonic() - t0)
                span.set_attribute("method", "passthrough")
                span.set_attribute("text_length", len(source))
                span.set_status(Status(StatusCode.OK))
                return source

            try:
                text = self._extract_with_pypdf(source)
                CV_PDF_PARSE_DURATION.observe(time.monotonic() - t0)
                span.set_attribute("method", "pypdf")
                span.set_attribute("text_length", len(text))
                span.set_status(Status(StatusCode.OK))
                logger.info(
                    "cv.pdf_parsed",
                    method="pypdf",
                    text_length=len(text),
                    correlation_id=correlation_id,
                )
                return text

            except Exception as exc:
                CV_PDF_PARSE_DURATION.observe(time.monotonic() - t0)
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("method", "fallback_utf8")
                logger.warning(
                    "cv.pdf_parse_failed",
                    error=str(exc),
                    fallback="utf8",
                    correlation_id=correlation_id,
                )
                raw: bytes
                if hasattr(source, "read"):
                    raw = source.read()  # type: ignore[union-attr]
                else:
                    raw = source  # type: ignore[assignment]
                return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

    def _extract_with_pypdf(self, source: bytes | BinaryIO) -> str:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        buffer = io.BytesIO(source) if isinstance(source, bytes) else source
        reader = PdfReader(buffer)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
