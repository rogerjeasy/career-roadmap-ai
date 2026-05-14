"""Fetch real career KB articles from Wikipedia + BLS data.

Sources
-------
1. BLS OES national wage estimates (local Excel/zip, public domain)
   Annual median wages for all ~800 SOC codes.
   Download: https://www.bls.gov/oes/tables.htm → May 2024 National → oesm24nat.zip

2. BLS Public Data API v2 (optional, requires free API key)
   10-year employment projections (growth rate, projected openings).
   Register at https://data.bls.gov/registrationEngine/

3. Wikipedia MediaWiki API (CC BY-SA 4.0, no auth required)
   Full career narrative articles per occupation.

Output
------
  career_kb_real.json — ready for CareerKBLoader ingestion

Usage
-----
  cd agents

  # Wikipedia only (no BLS data):
  python -m scripts.fetch_career_kb --output-dir data/knowledge-base

  # With BLS OES wages (download oesm24nat.zip from bls.gov first):
  python -m scripts.fetch_career_kb \\
    --oes-file "C:/Users/User/Downloads/oesm24nat.zip" \\
    --output-dir data/knowledge-base

  # Full enrichment including BLS employment projections:
  python -m scripts.fetch_career_kb \\
    --oes-file "C:/Users/User/Downloads/oesm24nat.zip" \\
    --bls-key YOUR_KEY \\
    --output-dir data/knowledge-base

  # Limit to specific occupations for testing:
  python -m scripts.fetch_career_kb --limit 20 --output-dir data/knowledge-base

  # Resume interrupted run (skips occupations already in the output file):
  python -m scripts.fetch_career_kb --resume --output-dir data/knowledge-base
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# Force UTF-8 + line-buffered output so progress lines appear immediately on Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# Load .env from apps/api so BLS_API_KEY is available when the script is run
# standalone (not via the FastAPI/Celery process that already has it loaded).
_ENV_FILE = Path(__file__).resolve().parents[2] / "apps" / "api" / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        # Manual fallback when python-dotenv is not installed in this venv.
        for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                if _k not in os.environ:
                    os.environ[_k] = _v.strip().strip('"').strip("'")

# ── Constants ─────────────────────────────────────────────────────────────────

# User-Agent is mandatory for Wikipedia API per their terms of service.
# See https://www.mediawiki.org/wiki/API:Etiquette
_WIKI_USER_AGENT = (
    "CareerRoadmapAI/1.0 (career-coaching-platform; "
    "contact: rogerjeasybavibidila@gmail.com) python-urllib/3.12"
)

_WIKI_API = "https://en.wikipedia.org/w/api.php"

# BLS OES 2024 national estimates download instructions (BLS blocks automated access):
#   1. Go to https://www.bls.gov/oes/tables.htm
#   2. Under "National" → click "May 2024 National Occupational Employment and Wage Estimates"
#   3. Download the national Excel/zip file (oesm24nat.zip or oesnat24.xlsx)
#   4. Pass the path to --oes-file
_BLS_OES_DOWNLOAD_PAGE = "https://www.bls.gov/oes/tables.htm"

# BLS Public Data API v2
_BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Wikipedia API request delay (seconds) — be polite to the API
_WIKI_DELAY = 0.5

# BLS API delay between batch requests
_BLS_DELAY = 1.0

# Max Wikipedia extract length (characters) per article
_MAX_EXTRACT_CHARS = 5000

# Max Wikipedia extract length for intro-only fallback
_MAX_INTRO_CHARS = 2000

# O*NET Web Services API (free key from https://services.onetcenter.org/developer/)
_ONET_BASE = "https://services.onetcenter.org/ws"
_ONET_DELAY = 0.5  # seconds between O*NET requests


# ── BLS OES wage loader ───────────────────────────────────────────────────────

def load_bls_oes_wages(
    oes_file: str | None = None,
    cache_path: Path | None = None,
) -> dict[str, dict]:
    """Load BLS OES national wage estimates from a locally downloaded file.

    BLS blocks automated bulk-file downloads (returns 403), so the file must
    be downloaded manually:
      1. Go to https://www.bls.gov/oes/tables.htm
      2. Under "National" → click "May 2024 National Occupational Employment
         and Wage Estimates"
      3. Download oesm24nat.zip (or the .xlsx directly)
      4. Pass the path via --oes-file

    Returns a dict keyed by 6-digit SOC code (e.g. '151252') with fields:
      occ_title, a_median, a_mean, tot_emp
    """
    try:
        import openpyxl  # noqa: PLC0415
    except ImportError:
        print("  openpyxl not installed — skipping BLS OES wages.")
        return {}

    # Return from JSON cache if already parsed
    if cache_path and cache_path.exists():
        print(f"  Loading BLS OES wages from cache: {cache_path.name}")
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"    {len(data):,} occupation wage records loaded.")
        return data

    if not oes_file:
        print(
            "  BLS OES wages skipped — no --oes-file provided.\n"
            f"  Download from: {_BLS_OES_DOWNLOAD_PAGE}\n"
            "  Then re-run with: --oes-file /path/to/oesm24nat.zip"
        )
        return {}

    oes_path = Path(oes_file)
    if not oes_path.exists():
        print(f"  WARNING: OES file not found: {oes_path} — wages will be skipped.")
        return {}

    # Support both .zip (containing the Excel) and plain .xlsx/.xls
    print(f"  Loading BLS OES data from {oes_path.name} ...")
    raw: bytes
    if oes_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(oes_path) as zf:
            # Find the first .xlsx file inside the archive
            xlsx_names = [n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls"))]
            if not xlsx_names:
                print("  WARNING: No Excel file found inside the zip — wages skipped.")
                return {}
            print(f"    Reading {xlsx_names[0]} from archive ...")
            raw = zf.read(xlsx_names[0])
    else:
        raw = oes_path.read_bytes()

    print("  Parsing OES Excel (this takes ~30 s for the full file) ...")
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Locate column indices from header row
    header = [str(c).strip().upper() if c else "" for c in rows[0]]
    wanted = ("OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN", "A_MEAN")
    col = {name: header.index(name) for name in wanted if name in header}
    if "OCC_CODE" not in col:
        print("  WARNING: Could not parse BLS OES Excel column headers — wages skipped.")
        return {}

    wages: dict[str, dict] = {}

    def _parse_num(v: object) -> float | None:
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    for row in rows[1:]:
        code = str(row[col["OCC_CODE"]] or "").strip().replace("-", "").replace(".", "")
        if not code or len(code) < 6:
            continue
        title = str(row[col.get("OCC_TITLE", 0)] or "").strip()
        wages[code[:6]] = {
            "occ_title": title,
            "a_median": _parse_num(row[col.get("A_MEDIAN", 0)]),
            "a_mean": _parse_num(row[col.get("A_MEAN", 0)]),
            "tot_emp": _parse_num(row[col.get("TOT_EMP", 0)]),
        }

    print(f"    {len(wages):,} occupation wage records parsed.")

    if cache_path:
        cache_path.write_text(json.dumps(wages, ensure_ascii=False), encoding="utf-8")
        print(f"    Cached to {cache_path.name}")

    return wages


# ── BLS API v2 employment projections ─────────────────────────────────────────

def fetch_bls_projections(soc_codes: list[str], bls_key: str) -> dict[str, dict]:
    """Fetch 10-year employment projections for a list of SOC codes via BLS API v2.

    Returns dict keyed by 6-digit SOC code with fields:
      growth_rate_pct, projected_openings, proj_period
    """
    # BLS Employment Projections series ID format: EP{occ_6digit}{datatype}
    # 05 = percent change in employment
    # 06 = numeric change in employment
    # 07 = occupational openings (annual average)
    if not bls_key:
        return {}

    results: dict[str, dict] = {}
    # Process in batches of 25 (conservative to avoid hitting limits)
    batch_size = 25
    ep_types = {"05": "growth_rate_pct", "07": "projected_openings"}

    for i in range(0, len(soc_codes), batch_size):
        batch = soc_codes[i : i + batch_size]
        series_ids = [
            f"EP{code}{dtype}"
            for code in batch
            for dtype in ep_types
        ]

        payload = json.dumps({
            "seriesid": series_ids,
            "registrationkey": bls_key,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                _BLS_API_BASE,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": _WIKI_USER_AGENT,
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"  WARNING: BLS API batch {i // batch_size + 1} failed: {exc}")
            time.sleep(_BLS_DELAY)
            continue

        for series in data.get("Results", {}).get("series", []):
            sid = series.get("seriesID", "")
            code = sid[2:8]  # extract 6-digit SOC
            dtype_key = sid[8:]
            field = ep_types.get(dtype_key)
            if not field or not series.get("data"):
                continue
            val_str = series["data"][0].get("value", "")
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                continue
            if code not in results:
                results[code] = {}
            results[code][field] = val

        time.sleep(_BLS_DELAY)
        print(f"  BLS projections: batch {i // batch_size + 1}/{(len(soc_codes) + batch_size - 1) // batch_size} done")

    return results


# ── O*NET Web Services enrichment ────────────────────────────────────────────

def fetch_onet_data(
    onet_code: str,
    username: str,
    password: str,
) -> dict | None:
    """Fetch O*NET occupation details (description, tasks, technology skills).

    Calls two endpoints:
      /occupations/{code}          — description and bright outlook tags
      /occupations/{code}/summary/tasks — core job tasks

    Auth: HTTP Basic. Register free at https://services.onetcenter.org/developer/
    Set ONET_USERNAME and ONET_PASSWORD in apps/api/.env.

    Returns dict with keys: description, tasks, technology_skills  or None on error.
    """
    if not username or not password:
        return None

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "User-Agent": _WIKI_USER_AGENT,
    }

    def _get(url: str) -> dict | None:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                print(f"  WARN O*NET {url[-40:]}: HTTP {exc.code}")
            return None
        except Exception as exc:
            print(f"  WARN O*NET {url[-40:]}: {exc}")
            return None

    code_enc = urllib.parse.quote(onet_code)
    result: dict = {}

    # 1. Basic occupation record (description + bright_outlook)
    occ = _get(f"{_ONET_BASE}/occupations/{code_enc}")
    if occ:
        desc = occ.get("description", "")
        if desc:
            result["description"] = desc
        tags = occ.get("tags", {})
        if isinstance(tags, dict):
            bright = tags.get("bright_outlook", False)
            if bright:
                result["bright_outlook"] = True

    # 2. Core tasks
    time.sleep(_ONET_DELAY)
    tasks_resp = _get(f"{_ONET_BASE}/occupations/{code_enc}/summary/tasks")
    if tasks_resp:
        task_items = tasks_resp.get("task", [])
        if not isinstance(task_items, list):
            task_items = [task_items] if task_items else []
        core = [
            t["name"] for t in task_items
            if isinstance(t, dict) and t.get("category") == "Core" and t.get("name")
        ][:6]
        if not core:
            core = [t["name"] for t in task_items[:6] if isinstance(t, dict) and t.get("name")]
        if core:
            result["tasks"] = core

    # 3. Technology skills
    time.sleep(_ONET_DELAY)
    tech_resp = _get(f"{_ONET_BASE}/occupations/{code_enc}/summary/technology_skills")
    if tech_resp:
        categories = tech_resp.get("category", [])
        if not isinstance(categories, list):
            categories = [categories] if categories else []
        tech_names: list[str] = []
        for cat in categories[:4]:
            examples = cat.get("example", [])
            if isinstance(examples, dict):
                examples = [examples]
            for ex in (examples if isinstance(examples, list) else [])[:3]:
                name = ex.get("name", "") if isinstance(ex, dict) else ""
                if name:
                    tech_names.append(name)
        if tech_names:
            result["technology_skills"] = tech_names[:10]

    return result if result else None


# ── Wikipedia article fetcher ─────────────────────────────────────────────────

def _wiki_request(params: dict) -> dict:
    """Make a Wikipedia API request and return parsed JSON."""
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = _WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _WIKI_USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search_wikipedia(query: str) -> str | None:
    """Return the best-matching Wikipedia page title for an occupation query."""
    try:
        data = _wiki_request({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "srnamespace": 0,
        })
        results = data.get("query", {}).get("search", [])
        if results:
            return results[0]["title"]
    except Exception:
        pass
    return None


def _fetch_wiki_extract(title: str) -> tuple[str, str] | None:
    """Fetch the full text extract + canonical URL for a Wikipedia article.

    Returns (extract_text, page_url) or None if the article doesn't exist.
    """
    try:
        data = _wiki_request({
            "action": "query",
            "titles": title,
            "prop": "extracts|info",
            "inprop": "url",
            "exintro": False,
            "explaintext": True,
        })
        pages = data.get("query", {}).get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        if not pages:
            return None
        page = pages[0]
        if "missing" in page:
            return None
        extract = page.get("extract", "").strip()
        url = page.get("fullurl", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}")
        if not extract:
            return None
        return extract[:_MAX_EXTRACT_CHARS], url
    except Exception:
        return None


def fetch_wikipedia_article(occupation_title: str) -> tuple[str, str] | None:
    """Fetch Wikipedia content for an occupation.

    Tries exact title first, then falls back to a search query.
    Returns (article_text, wikipedia_url) or None if nothing found.
    """
    # 1. Exact title
    result = _fetch_wiki_extract(occupation_title)
    if result:
        return result

    # 2. Search and take the top result
    found_title = _search_wikipedia(f"{occupation_title} occupation career")
    if found_title and found_title.lower() != occupation_title.lower():
        result = _fetch_wiki_extract(found_title)
        if result:
            return result

    return None


# ── Content assembly ──────────────────────────────────────────────────────────

def _build_content(
    occ: dict,
    wiki_text: str | None,
    wage: dict | None,
    projection: dict | None,
    onet_data: dict | None = None,
) -> str:
    """Assemble the final article content for a KB document."""
    parts: list[str] = []

    title = occ["occ_title"]
    parts.append(title)
    parts.append("=" * len(title))
    parts.append("")

    # O*NET description (authoritative, structured) before Wikipedia narrative
    if onet_data and onet_data.get("description"):
        parts.append(onet_data["description"])
        if onet_data.get("bright_outlook"):
            parts.append("[ Bright Outlook: projected to grow faster than average ]")
        parts.append("")

    if wiki_text:
        parts.append(wiki_text)
        parts.append("")

    # O*NET tasks
    if onet_data and onet_data.get("tasks"):
        parts.append("Key Job Tasks (O*NET)")
        parts.append("-" * 22)
        for task in onet_data["tasks"]:
            parts.append(f"• {task}")
        parts.append("")

    # O*NET technology skills
    if onet_data and onet_data.get("technology_skills"):
        parts.append("Common Technologies Used (O*NET)")
        parts.append("-" * 32)
        parts.append(", ".join(onet_data["technology_skills"]))
        parts.append("")

    # Real salary data
    if wage and wage.get("a_median"):
        median = int(wage["a_median"])
        mean = int(wage.get("a_mean") or 0)
        emp = wage.get("tot_emp")
        parts.append("Compensation (BLS OES 2024)")
        parts.append("-" * 28)
        parts.append(f"Median annual wage: ${median:,}")
        if mean:
            parts.append(f"Mean annual wage:   ${mean:,}")
        if emp:
            parts.append(f"Total employment:   {int(emp):,}")
        parts.append("")

    # Real growth projections
    if projection:
        growth = projection.get("growth_rate_pct")
        openings = projection.get("projected_openings")
        parts.append("10-Year Employment Outlook (BLS Employment Projections)")
        parts.append("-" * 54)
        if growth is not None:
            direction = "growth" if growth >= 0 else "decline"
            parts.append(f"Projected employment change: {growth:+.1f}% ({direction})")
        if openings is not None:
            parts.append(f"Annual average openings: {int(openings):,}")
        parts.append("")

    return "\n".join(parts).strip()


def _soc_to_key(soc_code: str) -> str:
    """Convert 'XX-XXXX.XX' to 6-digit key used in wage/projection dicts."""
    return soc_code.replace("-", "").replace(".", "")[:6]


# ── Main pipeline ─────────────────────────────────────────────────────────────

def fetch_career_kb(
    output_dir: str,
    bls_key: str = "",
    oes_file: str = "",
    limit: int = 0,
    resume: bool = False,
    onet_csv: str = "",
) -> list[dict]:
    """Fetch and assemble real career KB articles.

    Parameters
    ----------
    output_dir:
        Directory to write career_kb_real.json.
    bls_key:
        Optional BLS API v2 key for employment projections.
    oes_file:
        Path to locally downloaded BLS OES file (oesm24nat.zip or .xlsx).
        If omitted, wage data is skipped.
    limit:
        If > 0, process only this many occupations (for testing).
    resume:
        If True, skip occupations already present in the output file.
    onet_csv:
        Path to onet_occupations_enriched.csv. Defaults to
        <output_dir>/onet_occupations_enriched.csv.
    """
    import csv  # noqa: PLC0415

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "career_kb_real.json"
    cache_wages = out / ".bls_oes_wages_cache.json"

    # ── 1. Load occupation list from O*NET CSV ────────────────────────────────
    csv_path = Path(onet_csv) if onet_csv else out / "onet_occupations_enriched.csv"
    if not csv_path.exists():
        print(f"ERROR: O*NET CSV not found at {csv_path}")
        print("Run prepare_real_data.py first to generate onet_occupations_enriched.csv")
        sys.exit(1)

    occupations: list[dict] = []
    seen_codes: set[str] = set()
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code_raw = row.get("conceptUri", "").replace("onet:", "").strip()
            title = row.get("preferredLabel", "").strip()
            if not title or code_raw in seen_codes:
                continue
            seen_codes.add(code_raw)
            # Normalise code to XX-XXXX.XX format
            code = code_raw if "-" in code_raw else (
                f"{code_raw[:2]}-{code_raw[2:6]}.{code_raw[6:]}"
                if len(code_raw) >= 7 else code_raw
            )
            occupations.append({"onet_code": code, "occ_title": title})

    print(f"  {len(occupations):,} occupations loaded from O*NET CSV")

    if limit:
        occupations = occupations[:limit]
        print(f"  Limiting to first {limit} occupations (--limit flag)")

    # ── 2. Resume: load already-fetched records ───────────────────────────────
    existing: dict[str, dict] = {}
    if resume and output_file.exists():
        for rec in json.loads(output_file.read_text(encoding="utf-8")):
            existing[rec.get("onet_code", "")] = rec
        print(f"  Resuming: {len(existing):,} already-fetched records found")

    # ── 3. BLS OES wages (one-time load from local file) ─────────────────────
    print("\n[1/3] Loading BLS OES wage data ...")
    wages = load_bls_oes_wages(oes_file=oes_file or None, cache_path=cache_wages)

    # ── 4. BLS employment projections (optional, batched API) ─────────────────
    projections: dict[str, dict] = {}
    if bls_key:
        print("\n[2/4] Fetching BLS employment projections via API ...")
        soc_keys = [_soc_to_key(o["onet_code"]) for o in occupations]
        projections = fetch_bls_projections(soc_keys, bls_key)
        print(f"  Projections fetched for {len(projections):,} occupations")
    else:
        print("\n[2/4] BLS projections skipped (no --bls-key provided)")

    # ── 5. O*NET credentials ───────────────────────────────────────────────────
    onet_username = os.getenv("ONET_USERNAME", "")
    onet_password = os.getenv("ONET_PASSWORD", "")
    if onet_username and onet_password:
        print(f"\n[3/4] O*NET enrichment enabled (username: {onet_username})")
        print(f"      ~{total * _ONET_DELAY * 2 / 60:.0f} additional minutes for tasks + tech skills")
    else:
        print(
            "\n[3/4] O*NET enrichment skipped — ONET_USERNAME / ONET_PASSWORD not set.\n"
            "      Register free at https://services.onetcenter.org/developer/ and add to apps/api/.env"
        )

    # ── 6. Wikipedia articles + O*NET (per occupation, with rate limiting) ──────
    total = len(occupations)
    onet_extra = f" + O*NET ({_ONET_DELAY * 2:.1f}s/occ)" if onet_username else ""
    print(f"\n[4/4] Processing {total:,} occupations (Wikipedia{onet_extra}) ...")
    print(f"      Estimated time: ~{total * (_WIKI_DELAY + ((_ONET_DELAY * 2) if onet_username else 0)) / 60:.0f} minutes\n")

    results: list[dict] = list(existing.values())
    fetched = 0
    skipped = 0
    failed = 0
    start_time = time.time()

    for idx, occ in enumerate(occupations, 1):
        code = occ["onet_code"]
        title = occ["occ_title"]

        if code in existing:
            skipped += 1
            # Still print progress so the terminal doesn't look frozen
            if idx % 25 == 0:
                pct = idx / total * 100
                elapsed = time.time() - start_time
                rate = max(idx - skipped, 1) / max(elapsed, 1)
                remaining = (total - idx) / rate if rate > 0 else 0
                print(
                    f"  [{idx:>4}/{total}] {pct:5.1f}%  "
                    f"skipped (already fetched) | "
                    f"ETA {remaining / 60:.1f} min"
                )
            continue

        wage = wages.get(_soc_to_key(code))
        projection = projections.get(_soc_to_key(code))

        # Fetch Wikipedia
        wiki_result = fetch_wikipedia_article(title)
        time.sleep(_WIKI_DELAY)

        if wiki_result:
            wiki_text, wiki_url = wiki_result
            wiki_status = "ok"
        else:
            wiki_text, wiki_url = None, None
            wiki_status = "no-wiki"
            failed += 1

        # Fetch O*NET structured data (description, tasks, technology skills)
        onet_result: dict | None = None
        onet_marker = " "
        if onet_username and onet_password:
            onet_result = fetch_onet_data(code, onet_username, onet_password)
            onet_marker = "O" if onet_result else "x"

        content = _build_content(occ, wiki_text, wage, projection, onet_data=onet_result)
        if not content.strip():
            continue

        # Tags from title words (simple, but real)
        tags = [w.lower() for w in title.replace("/", " ").split() if len(w) > 3][:6]
        # Add O*NET technology tags if available
        if onet_result and onet_result.get("technology_skills"):
            for tech in onet_result["technology_skills"][:3]:
                tag = tech.lower().split()[0]  # first word of tech name
                if len(tag) > 2 and tag not in tags:
                    tags.append(tag)

        results.append({
            "id": f"ooh-{code.replace('.', '-').replace(' ', '-')}",
            "title": title,
            "content": content,
            "source_url": wiki_url or "https://www.bls.gov/ooh/",
            "language": "en",
            "tags": tags[:8],
            "category": "career_kb",
            "onet_code": code,
            "median_wage_usd": int(wage["a_median"]) if wage and wage.get("a_median") else None,
            "employment_total": int(wage["tot_emp"]) if wage and wage.get("tot_emp") else None,
            "bright_outlook": onet_result.get("bright_outlook", False) if onet_result else False,
        })
        fetched += 1

        # Per-occupation progress line
        elapsed = time.time() - start_time
        active = idx - skipped
        rate = active / max(elapsed, 1)
        remaining = (total - idx) / rate if rate > 0 else 0
        wage_marker = "$" if wage and wage.get("a_median") else " "
        proj_marker = "P" if projection else " "
        print(
            f"  [{idx:>4}/{total}] {idx / total * 100:5.1f}%  "
            f"{wiki_status:<7}  {wage_marker}{proj_marker}{onet_marker}  "
            f"{title[:38]:<38}  ETA {remaining / 60:.1f} min"
        )

        if idx % 50 == 0:
            # Save progress checkpoint so a crash doesn't lose everything
            output_file.write_text(
                json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            size_kb = output_file.stat().st_size // 1024
            print(
                f"\n  --- checkpoint @ {idx}/{total} ---  "
                f"{fetched} fetched, {skipped} resumed, {failed} no-wiki  "
                f"({size_kb} KB written)\n"
            )

    # ── 6. Final write ────────────────────────────────────────────────────────
    output_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    size_kb = output_file.stat().st_size // 1024
    print(
        f"\nDone. {len(results):,} records → {output_file.name} ({size_kb:,} KB)"
    )
    print(
        f"  Wikipedia: {fetched} fetched, {skipped} skipped (resume), {failed} no article found"
    )
    if wages:
        matched = sum(1 for r in results if r.get("median_wage_usd"))
        print(f"  BLS wages matched: {matched}/{len(results)}")
    if projections:
        proj_matched = sum(1 for r in results if projections.get(_soc_to_key(r.get("onet_code", ""))))
        print(f"  BLS projections matched: {proj_matched}/{len(results)}")
    if onet_username:
        onet_matched = sum(1 for r in results if r.get("bright_outlook") is not None)
        bright = sum(1 for r in results if r.get("bright_outlook"))
        print(f"  O*NET enriched: {onet_matched}/{len(results)}  ({bright} bright-outlook occupations)")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description="Fetch real career KB articles from Wikipedia + BLS data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default=_default_out,
        help=f"Output directory (default: {_default_out})",
    )
    parser.add_argument(
        "--oes-file", default="",
        help=(
            "Path to locally downloaded BLS OES file (oesm24nat.zip or .xlsx). "
            "Download from https://www.bls.gov/oes/tables.htm "
            "(National → May 2024 → oesm24nat.zip). "
            "If omitted, wage data is skipped."
        ),
    )
    parser.add_argument(
        "--bls-key", default="",
        help="BLS Public Data API v2 key (optional, for employment projections)",
    )
    parser.add_argument(
        "--onet-csv", default="",
        help="Path to onet_occupations_enriched.csv (default: <output-dir>/onet_occupations_enriched.csv)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only the first N occupations (0 = all, useful for testing)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip occupations already present in the output file",
    )
    args = parser.parse_args()

    # Fall back to environment variable for BLS key (loaded from apps/api/.env above)
    bls_key = args.bls_key or os.getenv("BLS_API_KEY", "")

    if not bls_key:
        print(
            "NOTE: No BLS API key provided. Employment projections will be skipped.\n"
            "      Set --bls-key or BLS_API_KEY in apps/api/.env to enable projections.\n"
        )

    fetch_career_kb(
        output_dir=args.output_dir,
        bls_key=bls_key,
        oes_file=args.oes_file,
        limit=args.limit,
        resume=args.resume,
        onet_csv=args.onet_csv,
    )

    print(
        "\nNext step - ingest into Pinecone:\n"
        "  POST /api/v1/admin/kb/ingest\n"
        "  {'doc_types': ['career_kb'], "
        "'source_overrides': {'career_kb': '<output-dir>/career_kb_real.json'}}"
    )


if __name__ == "__main__":
    main()
