"""BM25 sparse encoder for hybrid Pinecone search.

Wraps ``pinecone-text`` BM25Encoder with:
- Domain corpus fitting and JSON serialisation
- Cloudinary persistence (upload/download params)
- Automatic Cloudinary load on construction — so workers always get the
  domain-fitted encoder without requiring BM25_ENCODER_PATH to be set
- Graceful fallback to MS-MARCO pre-trained weights when neither a local
  file nor a Cloudinary asset exists

Load priority in __init__:
  1. ``params_path`` arg or ``BM25_ENCODER_PATH`` env var (local file, fastest)
  2. Cloudinary download (synchronous; runs when Cloudinary is configured and
     no local file is found — ensures domain-fitted weights are used after
     ``fit_bm25_encoder`` has run at least once)
  3. MS-MARCO default (pre-trained on 8.8M passages — decent fallback)

Usage:
  # Fit on corpus and persist
  enc = BM25SparseEncoder()
  enc.fit([chunk.content for chunk in all_chunks])
  await enc.save_to_cloudinary()

  # At retriever / worker startup — automatically gets domain-fitted weights
  enc = BM25SparseEncoder()
  sparse = enc.encode_query("Senior Python engineer Zurich")
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.rag.models import SparseVector
from agents.rag.observability import RAG_BM25_ENCODE_DURATION, RAG_BM25_ENCODE_TOTAL

logger = get_logger(__name__)

_CLOUDINARY_PUBLIC_ID = "career-roadmap/bm25_encoder_params.json"


class BM25SparseEncoder:
    """Thin wrapper around pinecone-text BM25Encoder.

    Produces sparse vectors compatible with Pinecone hybrid search.
    Thread-safe for reads; fit/save must be called before serving traffic.

    On construction the encoder is loaded via the priority chain described in
    the module docstring so every worker process gets domain-fitted weights
    automatically once ``fit_bm25_encoder`` has uploaded them to Cloudinary.
    """

    def __init__(self, *, params_path: str | None = None) -> None:
        try:
            from pinecone_text.sparse import BM25Encoder  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "pinecone-text package is required. "
                "Add it to pyproject.toml: pinecone-text>=0.9.0"
            ) from exc

        self._BM25Encoder = BM25Encoder

        # Priority 1 — explicit local file
        resolved = params_path or agent_settings.bm25_encoder_path
        if resolved and Path(resolved).exists():
            self._encoder = BM25Encoder().load(resolved)
            logger.info("rag.bm25.loaded_from_file", path=resolved)
            return

        # Priority 2 — Cloudinary (sync download; skipped if not configured)
        cloudinary_encoder = _load_from_cloudinary_sync(BM25Encoder)
        if cloudinary_encoder is not None:
            self._encoder = cloudinary_encoder
            return

        # Priority 3 — MS-MARCO pre-trained fallback
        self._encoder = BM25Encoder.default()
        logger.info("rag.bm25.using_ms_marco_default")

    # ── Fitting ──────────────────────────────────────────────────────────────

    def fit(self, corpus: list[str]) -> None:
        """Fit BM25 on domain text. Call once after bulk ingestion."""
        self._encoder.fit(corpus)
        logger.info("rag.bm25.fitted", corpus_size=len(corpus))

    # ── Encoding ─────────────────────────────────────────────────────────────

    def encode_documents(self, texts: list[str]) -> list[SparseVector]:
        """Encode document texts as sparse vectors for Pinecone upsert."""
        import time
        t0 = time.monotonic()
        try:
            raw: list[dict[str, Any]] = self._encoder.encode_documents(texts)
            RAG_BM25_ENCODE_DURATION.observe(time.monotonic() - t0)
            RAG_BM25_ENCODE_TOTAL.labels(mode="document", status="success").inc(len(texts))
            return [SparseVector(indices=r["indices"], values=r["values"]) for r in raw]
        except Exception as exc:
            RAG_BM25_ENCODE_DURATION.observe(time.monotonic() - t0)
            RAG_BM25_ENCODE_TOTAL.labels(mode="document", status="error").inc(len(texts))
            logger.error("rag.bm25.encode_documents_failed", error=str(exc))
            raise

    def encode_query(self, text: str) -> SparseVector:
        """Encode a query string as a sparse vector for hybrid retrieval."""
        import time
        t0 = time.monotonic()
        try:
            raw: list[dict[str, Any]] = self._encoder.encode_queries([text])
            RAG_BM25_ENCODE_DURATION.observe(time.monotonic() - t0)
            RAG_BM25_ENCODE_TOTAL.labels(mode="query", status="success").inc()
            r = raw[0]
            return SparseVector(indices=r["indices"], values=r["values"])
        except Exception as exc:
            RAG_BM25_ENCODE_DURATION.observe(time.monotonic() - t0)
            RAG_BM25_ENCODE_TOTAL.labels(mode="query", status="error").inc()
            logger.error("rag.bm25.encode_query_failed", error=str(exc))
            raise

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Dump fitted params to a local JSON file."""
        self._encoder.dump(path)
        logger.info("rag.bm25.saved_to_file", path=path)

    async def save_to_cloudinary(self) -> str:
        """Upload fitted params JSON to Cloudinary. Returns the public_id."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        self.save(tmp_path)
        try:
            from agents.rag.storage.cloudinary_client import get_cloudinary_client
            client = get_cloudinary_client()
            if client is None:
                logger.warning("rag.bm25.cloudinary_not_configured")
                return ""
            public_id = await asyncio.to_thread(
                _upload_raw, client, tmp_path, _CLOUDINARY_PUBLIC_ID
            )
            logger.info("rag.bm25.saved_to_cloudinary", public_id=public_id)
            return public_id
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @classmethod
    async def load_from_cloudinary(cls) -> "BM25SparseEncoder":
        """Download fitted params from Cloudinary and return a new encoder.

        Falls back to the full priority-chain constructor (which also tries
        Cloudinary synchronously) on any error.
        """
        try:
            from agents.rag.storage.cloudinary_client import get_cloudinary_client
            client = get_cloudinary_client()
            if client is None:
                logger.warning("rag.bm25.cloudinary_not_configured_using_default")
                return cls()
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmp_path = tmp.name

            downloaded = await asyncio.to_thread(
                _download_raw, client, _CLOUDINARY_PUBLIC_ID, tmp_path
            )
            if downloaded:
                enc = cls(params_path=tmp_path)
                Path(tmp_path).unlink(missing_ok=True)
                return enc
        except Exception as exc:
            logger.warning("rag.bm25.async_cloudinary_load_failed", error=str(exc))
        return cls()


# ── Sync Cloudinary helpers ───────────────────────────────────────────────────


def _load_from_cloudinary_sync(bm25_encoder_cls: Any) -> Any | None:
    """Synchronously try to download and load domain-fitted BM25 params.

    Called from ``BM25SparseEncoder.__init__`` so every worker process
    gets the domain-fitted encoder without needing ``BM25_ENCODER_PATH``
    set in the environment.  Returns the loaded encoder object, or None
    when Cloudinary is unconfigured or the asset does not exist yet.
    """
    try:
        from agents.rag.storage.cloudinary_client import get_cloudinary_client
        client = get_cloudinary_client()
        if client is None:
            return None

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        success = _download_raw(client, _CLOUDINARY_PUBLIC_ID, tmp_path)
        if not success:
            Path(tmp_path).unlink(missing_ok=True)
            return None

        encoder = bm25_encoder_cls().load(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        logger.info("rag.bm25.loaded_from_cloudinary_sync")
        return encoder

    except Exception as exc:
        logger.debug("rag.bm25.cloudinary_sync_load_skipped", reason=str(exc))
        return None


def _upload_raw(client: Any, local_path: str, public_id: str) -> str:
    import cloudinary.uploader  # type: ignore[import-untyped]
    result = cloudinary.uploader.upload(
        local_path,
        resource_type="raw",
        public_id=public_id,
        overwrite=True,
    )
    return str(result.get("public_id", public_id))


def _download_raw(client: Any, public_id: str, dest_path: str) -> bool:
    import urllib.request
    import cloudinary  # type: ignore[import-untyped]
    url = cloudinary.utils.cloudinary_url(public_id, resource_type="raw")[0]
    if not url:
        return False
    urllib.request.urlretrieve(url, dest_path)  # noqa: S310
    return Path(dest_path).stat().st_size > 0
