"""One-off script: upload all existing KB source files to Cloudinary.

Run this after configuring Cloudinary credentials to backfill all documents
that were ingested before the archiving step was added to the ingestion tasks.

Usage (from repo root):
    cd agents
    poetry run python scripts/upload_kb_to_cloudinary.py

Environment variables required (or set in .env):
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from the repo root or agents/ directory.
_HERE = Path(__file__).resolve().parent
_AGENTS_ROOT = _HERE.parent
_SRC = _AGENTS_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_KB_DIR = _AGENTS_ROOT / "data" / "knowledge-base"

# Maps (relative filename, doc_type_label, cloudinary public_id)
_SOURCE_FILES: list[dict[str, str]] = [
    {
        "path": str(_KB_DIR / "career_kb_real.json"),
        "doc_type": "career_kb",
        "public_id": "kb/career_kb/career_kb_real.json",
    },
    {
        "path": str(_KB_DIR / "market_reports_real.json"),
        "doc_type": "market_report",
        "public_id": "kb/market_report/market_reports_real.json",
    },
    {
        "path": str(_KB_DIR / "role_templates_real.json"),
        "doc_type": "role_template",
        "public_id": "kb/role_template/role_templates_real.json",
    },
    {
        "path": str(_KB_DIR / "swiss_eu_market_real.json"),
        "doc_type": "swiss_eu_market",
        "public_id": "kb/swiss_eu_market/swiss_eu_market_real.json",
    },
    {
        "path": str(_KB_DIR / "esco_occupations_enriched.csv"),
        "doc_type": "esco",
        "public_id": "kb/esco/esco_occupations_enriched.csv",
    },
    {
        "path": str(_KB_DIR / "esco_skills.csv"),
        "doc_type": "esco",
        "public_id": "kb/esco/esco_skills.csv",
    },
    {
        "path": str(_KB_DIR / "onet_occupations_enriched.csv"),
        "doc_type": "onet",
        "public_id": "kb/onet/onet_occupations_enriched.csv",
    },
]


async def main() -> None:
    from agents.rag.tasks.ingestion_tasks import _upload_sources  # noqa: PLC0415

    existing = [e for e in _SOURCE_FILES if Path(e["path"]).exists()]
    missing = [e["path"] for e in _SOURCE_FILES if not Path(e["path"]).exists()]

    if missing:
        print(f"[warn] {len(missing)} file(s) not found and will be skipped:")
        for m in missing:
            print(f"       {m}")

    if not existing:
        print("[error] No files found to upload. Check KB_DIR:", _KB_DIR)
        sys.exit(1)

    print(f"\nUploading {len(existing)} file(s) to Cloudinary...")
    result = await _upload_sources(existing)

    print(
        f"\nDone. uploaded={result['uploaded']}  "
        f"failed={result['failed']}  "
        f"total={result['total']}"
    )
    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
