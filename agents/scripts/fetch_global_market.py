"""Master merge script — assembles the full global-market knowledge base.

Calls all 5 regional fetch scripts in sequence, merges their output into a
single JSON file at agents/data/knowledge-base/global_market_real.json.
Deduplication is performed by doc_id; regional curated docs take precedence
over ILO supplement docs when doc_ids collide.

Regional scripts invoked:
  fetch_oceania_market.py  → Oceania (AU, NZ, FJ, PG)
  fetch_asia_market.py     → Asia 14 countries (SG, IN, JP, CN, KR, PH, MY, TH, ID, VN, BD, HK, PK, LK)
  fetch_africa_market.py   → Africa 16 countries (NG, ZA, KE, ET, GH, TZ, UG, RW, AO, EG, MA, SN, CI, CM, DZ, TN*)
  fetch_latam_market.py    → LATAM 17 countries (BR, MX, AR, CO, CL, PE, EC, BO, UY, PY, PA, CR, GT, HN, DO, JM, TT)
  fetch_mena_market.py     → MENA 11 countries (AE, SA, QA, KW, BH, OM, TR, IL, JO, TN, plus ILO for DZ, IQ, LB)

Output:
  agents/data/knowledge-base/global_market_real.json

Usage:
  python fetch_global_market.py                           # full run, all regions
  python fetch_global_market.py --regions oceania asia    # selective regions
  python fetch_global_market.py --dry-run                 # validate, no write
  python fetch_global_market.py --no-cache                # bypass ILO cache
  python fetch_global_market.py --start-year 2020         # narrow ILO years
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# ── Resolve scripts dir ────────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

_REPO_ROOT = _SCRIPTS_DIR.parent
_OUTPUT_FILE = _REPO_ROOT / "data" / "knowledge-base" / "global_market_real.json"

# ── Doc normalisation ─────────────────────────────────────────────────────────
# Older regional scripts (e.g. fetch_oceania_market.py) emit flat documents:
#   {"id": "...", "title": "...", "content": "...", "continent": "Oceania", ...}
# Newer scripts emit the standard nested shape:
#   {"doc_id": "...", "title": "...", "content": "...", "metadata": {...}}
# This normaliser converts flat docs to the standard shape so the merge and the
# GlobalMarketLoader both see a consistent structure.

_TOP_LEVEL_FIELDS = frozenset({"doc_id", "id", "title", "content", "metadata"})


def _normalise_doc(doc: dict) -> dict:
    """Return a copy of doc in standard {doc_id, title, content, metadata} shape."""
    if "metadata" in doc:
        # Already standard — just ensure doc_id is present.
        if "doc_id" not in doc and "id" in doc:
            doc = dict(doc)
            doc["doc_id"] = doc.pop("id")
        return doc
    # Flat doc: promote metadata fields out of top-level.
    doc_id = doc.get("doc_id") or doc.get("id", "")
    title = doc.get("title", "")
    content = doc.get("content", "")
    metadata = {k: v for k, v in doc.items() if k not in _TOP_LEVEL_FIELDS}
    # doc_type default so GlobalMarketLoader recognises it.
    metadata.setdefault("doc_type", "global_market")
    return {
        "doc_id": doc_id,
        "title": title,
        "content": content,
        "metadata": metadata,
    }


# ── Region registry ────────────────────────────────────────────────────────────

_REGION_MODULES: dict[str, str] = {
    "oceania": "fetch_oceania_market",
    "asia":    "fetch_asia_market",
    "africa":  "fetch_africa_market",
    "latam":   "fetch_latam_market",
    "mena":    "fetch_mena_market",
}


def _load_region(
    region_name: str,
    *,
    start_year: int,
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """Import a regional module and call its build_all_docs function."""
    import importlib
    module_name = _REGION_MODULES[region_name]
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        print(f"[WARN] Cannot import {module_name}: {exc}")
        return []

    if not hasattr(mod, "build_all_docs"):
        print(f"[WARN] {module_name} has no build_all_docs function")
        return []

    print(f"\n{'='*60}")
    print(f"[Global] Processing region: {region_name.upper()}")
    print(f"{'='*60}")

    t0 = time.monotonic()
    # Pass dry_run=True so regional scripts don't write their own files;
    # we do a single consolidated write here.
    docs = mod.build_all_docs(
        start_year=start_year,
        use_cache=use_cache,
        dry_run=True,
    )
    elapsed = time.monotonic() - t0
    print(f"[Global] {region_name.upper()} done: {len(docs)} docs in {elapsed:.1f}s")
    return docs


def build_global_kb(
    regions: list[str],
    *,
    start_year: int,
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """Merge all regional docs into one deduped list."""
    all_docs: list[dict] = []
    for region in regions:
        if region not in _REGION_MODULES:
            print(f"[WARN] Unknown region '{region}', skipping")
            continue
        region_docs = _load_region(
            region,
            start_year=start_year,
            use_cache=use_cache,
            dry_run=dry_run,
        )
        all_docs.extend(region_docs)

    # Normalise all docs to standard shape before deduplication.
    all_docs = [_normalise_doc(d) for d in all_docs]

    # Deduplication: first doc with a given doc_id wins (curated > ILO supplement
    # because regional scripts always put curated docs first in their lists).
    seen: dict[str, dict] = {}
    for doc in all_docs:
        doc_id = doc.get("doc_id") or ""
        if doc_id and doc_id not in seen:
            seen[doc_id] = doc
        elif not doc_id:
            # Docs without a doc_id get a generated fallback key so they're kept.
            fallback_key = f"__no_id_{len(seen)}"
            seen[fallback_key] = doc

    merged = list(seen.values())

    print(f"\n{'='*60}")
    print(f"[Global] Merge complete")
    print(f"  Total docs before dedup : {len(all_docs)}")
    print(f"  Total docs after dedup  : {len(merged)}")
    print(f"{'='*60}")

    # Summary by region / continent
    continent_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}
    for doc in merged:
        meta = doc.get("metadata", {})
        cont = meta.get("continent", "unknown")
        country = meta.get("country", "unknown")
        continent_counts[cont] = continent_counts.get(cont, 0) + 1
        country_counts[country] = country_counts.get(country, 0) + 1

    print("\n[Global] Docs by continent:")
    for cont, n in sorted(continent_counts.items()):
        print(f"  {cont:20s}: {n:5d}")

    print("\n[Global] Top 20 countries by doc count:")
    top20 = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    for country, n in top20:
        print(f"  {country:8s}: {n}")

    if not dry_run:
        _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
        size_kb = _OUTPUT_FILE.stat().st_size / 1024
        print(f"\n[Global] Written: {_OUTPUT_FILE} ({size_kb:.0f} KB)")
    else:
        print("\n[Global] Dry run — output file not written")

    return merged


# ── CLI ────────────────────────────────────────────────────────────────────────

_ALL_REGIONS = list(_REGION_MODULES.keys())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and merge global labour-market data for RAG KB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available regions: {', '.join(_ALL_REGIONS)}",
    )
    parser.add_argument(
        "--regions",
        nargs="+",
        default=_ALL_REGIONS,
        choices=_ALL_REGIONS,
        metavar="REGION",
        help="Regions to include (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip writing output")
    parser.add_argument("--no-cache", action="store_true", help="Bypass ILO API disk cache")
    parser.add_argument("--start-year", type=int, default=2018, help="Earliest ILO data year")
    args = parser.parse_args()

    t_total = time.monotonic()
    docs = build_global_kb(
        args.regions,
        start_year=args.start_year,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )
    elapsed_total = time.monotonic() - t_total

    print(f"\n[Global] Finished in {elapsed_total:.1f}s — {len(docs)} documents total")


if __name__ == "__main__":
    main()
