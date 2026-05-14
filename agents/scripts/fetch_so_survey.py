"""fetch_so_survey.py — Download and convert Stack Overflow Developer Survey to rich KB documents.

Sources
-------
Stack Overflow Annual Developer Survey — https://survey.stackoverflow.co/datasets/
  Licensed under ODbL 1.0. Free to download, ~30 MB CSV per year.
  ~65,000–95,000 respondents per year (2022–2025).

What this script produces
-------------------------
~60–75 market-report documents across three tiers:

  Tier 1 — Global documents (15):
    • Survey overview + yearly respondent / salary trends
    • Salary by developer role (IC vs PM, YoY change, industry split)
    • Salary by years of professional experience (growth curves per role)
    • International salary comparison (30+ countries with context)
    • Technology salary premium (which tools command higher pay)
    • Programming language adoption — multi-year trend table
    • Web framework & library adoption trends
    • Database technology adoption trends
    • Cloud platform and infrastructure adoption
    • AI tool adoption + developer sentiment (2023–latest)
    • Developer tools, IDEs, and collaboration software
    • Remote work and employment-type trends
    • Education level + learning paths & resources
    • Job satisfaction breakdown by role, company size, country
    • Skills gap: most-desired technologies not yet in use

  Tier 2 — Per-country deep dives (up to 25 countries, n ≥ 50):
    • Full salary profile: by role, by YoE, P25 / Median / P75
    • Top languages, frameworks, databases, cloud platforms
    • Desired vs used technology comparison
    • Remote work, org size, job satisfaction, education

  Tier 3 — Per-role deep dives (up to 18 roles, n ≥ 100):
    • Salary by country (top 15) and by experience band
    • Top technologies used + desired
    • AI tool adoption, remote work patterns, IC/PM split
    • Top industries, org size distribution

All documents are appended to market_reports_real.json, replacing any prior so-survey-* docs.

Usage
-----
  cd agents

  # Auto-download 2024 + 2023 survey data and process:
  python -m scripts.fetch_so_survey --output-dir data/knowledge-base

  # Use previously downloaded survey CSV/ZIP files:
  python -m scripts.fetch_so_survey \\
      --survey-dir C:/Users/User/Downloads \\
      --output-dir data/knowledge-base

  # Specific years only:
  python -m scripts.fetch_so_survey --years 2025 2024 2023 2022

  # Dry-run (build docs, do NOT write output):
  python -m scripts.fetch_so_survey --dry-run

Manual download
---------------
  The SO datasets landing page is no longer public. To download manually:

  2024: https://survey.stackoverflow.co/2024/  →  Methodology tab  →  "Download data"
        Or: kaggle datasets download -d stackoverflow/stack-overflow-2024-developer-survey
  2023: https://cdn.stackoverflow.co/files/jo7n4k8s/production/49915bfd46d0902c3564fd9a06b509d08a20488c.zip/stack-overflow-developer-survey-2023.zip
  2022: https://info.stackoverflow.com/rs/719-EMH-566/images/stack-overflow-developer-survey-2022.zip

  Place the ZIP (or extracted CSV) in --survey-dir.  The script auto-extracts ZIPs.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

csv.field_size_limit(10_000_000)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# ── Column aliases (normalised across survey years 2022–2025) ──────────────────
_COL_COMP            = ["ConvertedCompYearly", "ConvertedSalary"]
_COL_DEVTYPE         = ["DevType"]
_COL_COUNTRY         = ["Country"]
_COL_YEARS_PRO       = ["YearsCodePro"]
_COL_YEARS_CODE      = ["YearsCode"]
_COL_EMPLOYMENT      = ["Employment"]
_COL_REMOTE          = ["RemoteWork", "WorkLoc", "WorkRemote"]
_COL_LANGUAGE        = ["LanguageHaveWorkedWith", "LanguageWorkedWith"]
_COL_LANGUAGE_WANT   = ["LanguageWantToWorkWith"]
_COL_DATABASE        = ["DatabaseHaveWorkedWith", "DatabaseWorkedWith"]
_COL_DATABASE_WANT   = ["DatabaseWantToWorkWith"]
_COL_PLATFORM        = ["PlatformHaveWorkedWith", "PlatformWorkedWith"]
_COL_PLATFORM_WANT   = ["PlatformWantToWorkWith"]
_COL_FRAMEWORK       = ["WebframeHaveWorkedWith", "WebframeWorkedWith", "FrameworkHaveWorkedWith"]
_COL_FRAMEWORK_WANT  = ["WebframeWantToWorkWith", "FrameworkWantToWorkWith"]
_COL_MISC_TECH       = ["MiscTechHaveWorkedWith", "MiscTechWorkedWith"]
_COL_MISC_WANT       = ["MiscTechWantToWorkWith"]
_COL_TOOLS           = ["ToolsTechHaveWorkedWith", "ToolsTechWorkedWith"]
_COL_TOOLS_WANT      = ["ToolsTechWantToWorkWith"]
_COL_COLLAB          = ["NEWCollabToolsHaveWorkedWith", "CollabToolsHaveWorkedWith"]
_COL_COLLAB_WANT     = ["NEWCollabToolsWantToWorkWith", "CollabToolsWantToWorkWith"]
_COL_OS              = ["OpSysProfessional use", "OpSysProfessionaluse", "OpSys"]
_COL_AI_SEARCH       = ["AISearchHaveWorkedWith", "AISearchDevHaveWorkedWith"]
_COL_AI_SEARCH_WANT  = ["AISearchWantToWorkWith", "AISearchDevWantToWorkWith"]
_COL_AI_DEV          = ["AIDevHaveWorkedWith"]
_COL_AI_DEV_WANT     = ["AIDevWantToWorkWith"]
_COL_AI_MODELS       = ["AIModelsHaveWorkedWith"]
_COL_AI_SENT         = ["AISent"]
_COL_AI_SELECT       = ["AISelect"]
_COL_ORG_SIZE        = ["OrgSize"]
_COL_ED_LEVEL        = ["EdLevel"]
_COL_LEARN_CODE      = ["LearnCode"]
_COL_LEARN_ONLINE    = ["LearnCodeOnline"]
_COL_JOB_SAT         = ["JobSat", "JobSatisfaction"]
_COL_IC_OR_PM        = ["ICorPM"]
_COL_INDUSTRY        = ["Industry"]
_COL_MAIN_BRANCH     = ["MainBranch"]
_COL_AGE             = ["Age"]

# ── Dev-type normalisation map ────────────────────────────────────────────────
_DEVTYPE_NORM: dict[str, str] = {
    "Developer, full-stack":                          "Full-Stack Developer",
    "Developer, back-end":                            "Back-End Developer",
    "Developer, front-end":                           "Front-End Developer",
    "Developer, mobile":                              "Mobile Developer",
    "Data scientist or machine learning specialist":  "Data Scientist / ML",
    "Data or business analyst":                       "Data / Business Analyst",
    "Engineer, data":                                 "Data Engineer",
    "DevOps specialist":                              "DevOps / SRE",
    "Cloud infrastructure engineer":                  "Cloud Engineer",
    "Security professional":                          "Security Engineer",
    "Developer, embedded applications or devices":    "Embedded / IoT Developer",
    "Engineering manager":                            "Engineering Manager",
    "Senior Executive (C-Suite, VP, etc.)":           "CTO / VP Engineering",
    "Developer, QA or test":                          "QA / Test Engineer",
    "Research & Development role":                    "R&D Engineer",
    "System administrator":                           "Sysadmin / IT Ops",
    "Database administrator":                         "Database Administrator",
    "Developer, game or graphics":                    "Game / Graphics Developer",
    "Academic researcher":                            "Academic Researcher",
    "Developer, desktop or enterprise applications":  "Desktop / Enterprise Developer",
    "Student":                                        "Student",
    "Other (please specify):":                        "Other",
}

# ── Experience bands ──────────────────────────────────────────────────────────
_XP_BANDS: list[tuple[str, float, float]] = [
    ("< 1 year",    0.0,  0.9),
    ("1–2 years",   1.0,  2.9),
    ("3–5 years",   3.0,  5.9),
    ("6–10 years",  6.0, 10.9),
    ("11–20 years", 11.0, 20.9),
    ("20+ years",   21.0, 999.0),
]

# ── Countries for per-country deep-dive documents ────────────────────────────
_COUNTRY_DOCS: list[str] = [
    "Switzerland", "Germany", "United Kingdom", "France", "Netherlands",
    "Sweden", "Norway", "Denmark", "Finland", "Austria", "Belgium",
    "Poland", "Spain", "Portugal", "Italy", "Ireland",
    "Czech Republic", "Romania", "Hungary",
    "United States of America", "Canada", "Australia",
    "India", "Brazil", "Singapore",
]

# Countries shown in global salary comparison table
_FEATURED_COUNTRIES: list[str] = [
    "United States of America", "Switzerland", "Germany", "United Kingdom",
    "Netherlands", "Australia", "Canada", "France", "Sweden", "Norway",
    "Denmark", "Ireland", "Austria", "Finland", "Belgium",
    "Poland", "Brazil", "India", "Spain", "Portugal",
    "Czech Republic", "Italy", "Singapore", "Japan",
]

# Country → region tag (for Pinecone metadata)
_COUNTRY_REGION: dict[str, str] = {
    "Switzerland": "Switzerland", "Germany": "EU", "France": "EU",
    "Netherlands": "EU", "Sweden": "EU", "Norway": "EU", "Denmark": "EU",
    "Finland": "EU", "Austria": "EU", "Belgium": "EU", "Poland": "EU",
    "Spain": "EU", "Portugal": "EU", "Italy": "EU", "Ireland": "EU",
    "Czech Republic": "EU", "Romania": "EU", "Hungary": "EU",
    "United Kingdom": "Europe",
    "United States of America": "North America", "Canada": "North America",
    "Australia": "APAC", "India": "APAC", "Singapore": "APAC", "Japan": "APAC",
    "Brazil": "South America",
}

# ── Education level normalisation ─────────────────────────────────────────────
_ED_NORM: dict[str, str] = {
    "Bachelor's degree (B.A., B.S., B.Eng., etc.)":               "Bachelor's degree",
    "Master's degree (M.A., M.S., M.Eng., MBA, etc.)":            "Master's degree",
    "Some college/university study without earning a degree":      "Some college (no degree)",
    "Secondary school (e.g. American high school, German Realschule or Gymnasium, etc.)":
                                                                   "Secondary school",
    "Associate degree (A.A., A.S., etc.)":                        "Associate degree",
    "Other doctoral degree (Ph.D., Ed.D., etc.)":                  "PhD / Doctoral",
    "Professional degree (JD, MD, Ph.D, Ed.D, etc.)":             "Professional degree",
    "Primary/elementary school":                                   "Primary school",
    "Something else":                                              "Other",
}

# ── Download URL candidates per year ─────────────────────────────────────────
_UA = (
    "CareerRoadmapAI/1.0 (career-coaching-platform; "
    "contact: rogerjeasy@gmail.com) python-urllib/3.12"
)
_DATASETS_PAGE = "https://survey.stackoverflow.co/datasets/"
_DOWNLOAD_CANDIDATES: dict[int, list[str]] = {
    # URLs verified against cdn.stackoverflow.co (Sanity CDN) as of 2026-05.
    # The hash in the path is content-addressed; if a URL returns 404, the file
    # was re-published and the hash changed — check survey.stackoverflow.co/2024/
    # methodology for a "Download data" link, or use Kaggle as fallback.
    2025: [
        # Try scraping the methodology page first (see _scrape_download_links)
        "https://cdn.stackoverflow.co/files/jo7n4k8s/production/stack-overflow-developer-survey-2025.zip",
    ],
    2024: [
        # Kaggle mirror (free account required): kaggle datasets download -d stackoverflow/stack-overflow-2024-developer-survey
        "https://cdn.stackoverflow.co/files/jo7n4k8s/production/stack-overflow-developer-survey-2024.zip",
    ],
    2023: [
        # Verified working (HEAD 200) as of 2026-05
        "https://cdn.stackoverflow.co/files/jo7n4k8s/production/49915bfd46d0902c3564fd9a06b509d08a20488c.zip/stack-overflow-developer-survey-2023.zip",
    ],
    2022: [
        "https://info.stackoverflow.com/rs/719-EMH-566/images/stack-overflow-developer-survey-2022.zip",
        "https://cdn.stackoverflow.co/files/jo7n4k8s/production/stack-overflow-developer-survey-2022.zip",
    ],
}

# ── Download helpers ───────────────────────────────────────────────────────────

def _http_get_bytes(url: str, timeout: int = 120) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        print(f"    HTTP {exc.code}: {url[:80]}")
    except Exception as exc:
        print(f"    Error: {exc} — {url[:80]}")
    return None


def _scrape_download_links(year: int) -> list[str]:
    """Try to parse download links for a given year from the datasets landing page."""
    raw = _http_get_bytes(_DATASETS_PAGE, timeout=15)
    if not raw:
        return []
    html = raw.decode("utf-8", errors="replace")
    # Look for href patterns containing the year
    pattern = rf'href=["\']([^"\']*{year}[^"\']*\.zip)["\']'
    matches = re.findall(pattern, html, re.IGNORECASE)
    links: list[str] = []
    for m in matches:
        if m.startswith("http"):
            links.append(m)
        elif m.startswith("/"):
            links.append(f"https://survey.stackoverflow.co{m}")
    return links


def _find_survey_csv(directory: Path, year: int) -> Path | None:
    """Locate a survey CSV or ZIP for the given year inside a directory."""
    if not directory.exists():
        return None
    year_str = str(year)
    # Check for ZIP files first, extract CSV from them
    for f in sorted(directory.iterdir()):
        if year_str in f.name and f.suffix.lower() == ".zip":
            return _extract_csv_from_zip(f, year)
    # Already-extracted CSVs
    patterns = [
        f"survey_results_public_{year}.csv",
        f"results_{year}.txt",
        f"stack-overflow-developer-survey-{year}.csv",
        f"survey_results_public.csv",  # flat extraction without year suffix
    ]
    for name in patterns:
        p = directory / name
        if p.exists():
            return p
    # Fuzzy: any CSV/txt with the year in the name
    for f in sorted(directory.iterdir()):
        if year_str in f.name and f.suffix.lower() in (".csv", ".txt"):
            return f
    return None


def _extract_csv_from_zip(zip_path: Path, year: int) -> Path | None:
    """Extract the survey CSV from a ZIP and return the extracted path."""
    extract_dir = zip_path.parent / f"so_survey_{year}"
    extract_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not csv_names:
                return None
            # Prefer the largest file (results CSV)
            best = max(csv_names, key=lambda n: zf.getinfo(n).file_size)
            extracted = extract_dir / Path(best).name
            if not extracted.exists():
                print(f"    Extracting {best} from {zip_path.name} ...")
                extracted.write_bytes(zf.read(best))
            return extracted
    except Exception as exc:
        print(f"    WARN: Could not read {zip_path.name}: {exc}")
    return None


def download_survey(year: int, cache_dir: Path) -> Path | None:
    """Download the survey data for a given year into cache_dir.

    Returns the path to the CSV, or None if download fails.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check cache first
    existing = _find_survey_csv(cache_dir, year)
    if existing:
        return existing

    print(f"  Downloading {year} survey data ...")
    # Collect all candidate URLs
    candidates = list(_DOWNLOAD_CANDIDATES.get(year, []))
    scraped = _scrape_download_links(year)
    for link in scraped:
        if link not in candidates:
            candidates.insert(0, link)  # scraped links take priority

    for url in candidates:
        print(f"    Trying: {url[:90]} ...")
        data = _http_get_bytes(url, timeout=180)
        if not data:
            continue
        suffix = ".zip" if url.lower().endswith(".zip") or data[:2] == b"PK" else ".csv"
        dest = cache_dir / f"stack-overflow-developer-survey-{year}{suffix}"
        dest.write_bytes(data)
        print(f"    Saved {len(data) // 1024:,} KB → {dest.name}")
        if suffix == ".zip":
            csv_path = _extract_csv_from_zip(dest, year)
            if csv_path:
                return csv_path
        else:
            return dest

    print(
        f"  WARN: Could not auto-download {year} survey.\n"
        f"        Manual download: {_DATASETS_PAGE}\n"
        f"        Place the CSV or ZIP in: {cache_dir}"
    )
    return None


# ── CSV parsing helpers ────────────────────────────────────────────────────────

def _find_col(header: list[str], aliases: list[str]) -> str | None:
    h_map = {h.lower().strip(): h for h in header}
    for alias in aliases:
        if alias.lower().strip() in h_map:
            return h_map[alias.lower().strip()]
    return None


def _detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return "\t" if line.count("\t") > line.count(",") else ","


def _parse_comp(val: str) -> float | None:
    try:
        v = float(str(val).replace(",", "").strip())
        return v if 10_000 <= v <= 3_000_000 else None
    except (ValueError, TypeError):
        return None


def _parse_years(val: str) -> float | None:
    if not val or val.strip() in ("NA", ""):
        return None
    val = val.strip()
    if "Less than 1" in val or val == "< 1 year":
        return 0.5
    if "More than 50" in val:
        return 52.0
    try:
        return float(val)
    except ValueError:
        return None


def _split(val: str) -> list[str]:
    if not val or val.strip() in ("NA", ""):
        return []
    return [v.strip() for v in val.split(";") if v.strip()]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * p / 100.0
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _fmt_usd(v: float) -> str:
    return f"${int(round(v / 1000)) * 1000:,}"


def _top_n(counter: collections.Counter, n: int, total: int | None = None) -> list[tuple[str, int, float]]:
    """Return [(label, count, pct)] for top n items."""
    result = []
    for label, cnt in counter.most_common(n):
        pct = cnt / total * 100 if total else 0.0
        result.append((label, cnt, pct))
    return result


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_year(path: Path, year: int) -> dict:  # noqa: C901 (complexity is intentional)
    """Stream one survey CSV and return all aggregated statistics.

    The returned dict contains global counters, salary lists indexed in
    multiple dimensions, and per-country / per-role breakdowns.
    """
    sep = _detect_sep(path)

    def _dd_list() -> collections.defaultdict:
        return collections.defaultdict(list)

    def _dd_counter() -> collections.defaultdict:
        return collections.defaultdict(collections.Counter)

    def _dd_dd_list() -> collections.defaultdict:
        return collections.defaultdict(_dd_list)

    stats: dict = {
        "year": year, "total": 0, "total_with_salary": 0,

        # ── Global salary lists
        "salary_all":         [],
        "salary_by_role":     _dd_list(),
        "salary_by_country":  _dd_list(),
        "salary_by_xp":       _dd_list(),
        "salary_by_ed":       _dd_list(),
        "salary_by_ic_pm":    _dd_list(),
        "salary_by_industry": _dd_list(),
        # Technology salary premium — salary of users of each tech
        "salary_by_lang":     _dd_list(),
        "salary_by_framework": _dd_list(),
        "salary_by_db":       _dd_list(),
        "salary_by_platform": _dd_list(),
        "salary_by_misc":     _dd_list(),

        # ── Global adoption counters
        "lang_counts":        collections.Counter(),
        "lang_want_counts":   collections.Counter(),
        "db_counts":          collections.Counter(),
        "db_want_counts":     collections.Counter(),
        "platform_counts":    collections.Counter(),
        "platform_want_counts": collections.Counter(),
        "framework_counts":   collections.Counter(),
        "framework_want_counts": collections.Counter(),
        "misc_tech_counts":   collections.Counter(),
        "misc_want_counts":   collections.Counter(),
        "tools_counts":       collections.Counter(),
        "tools_want_counts":  collections.Counter(),
        "collab_counts":      collections.Counter(),
        "collab_want_counts": collections.Counter(),
        "os_counts":          collections.Counter(),
        "ai_search_counts":   collections.Counter(),
        "ai_search_want":     collections.Counter(),
        "ai_dev_counts":      collections.Counter(),
        "ai_dev_want":        collections.Counter(),
        "ai_model_counts":    collections.Counter(),
        "ai_sent_counts":     collections.Counter(),

        # ── Global demographic / work counters
        "remote_counts":      collections.Counter(),
        "org_size_counts":    collections.Counter(),
        "employment_counts":  collections.Counter(),
        "ed_level_counts":    collections.Counter(),
        "learn_code_counts":  collections.Counter(),
        "learn_online_counts": collections.Counter(),
        "job_sat_counts":     collections.Counter(),
        "ic_pm_counts":       collections.Counter(),
        "industry_counts":    collections.Counter(),
        "main_branch_counts": collections.Counter(),
        "age_counts":         collections.Counter(),

        # ── Per-country breakdowns
        "country_total":             collections.defaultdict(int),
        "country_lang_counts":       _dd_counter(),
        "country_lang_want":         _dd_counter(),
        "country_framework_counts":  _dd_counter(),
        "country_framework_want":    _dd_counter(),
        "country_db_counts":         _dd_counter(),
        "country_db_want":           _dd_counter(),
        "country_platform_counts":   _dd_counter(),
        "country_remote_counts":     _dd_counter(),
        "country_org_size_counts":   _dd_counter(),
        "country_ed_counts":         _dd_counter(),
        "country_job_sat_counts":    _dd_counter(),
        "country_role_counts":       _dd_counter(),
        "country_ai_counts":         _dd_counter(),
        "country_salary_by_role":    _dd_dd_list(),
        "country_salary_by_xp":      _dd_dd_list(),

        # ── Per-role breakdowns
        "role_total":                collections.defaultdict(int),
        "role_country_salary":       _dd_dd_list(),
        "role_xp_salary":            _dd_dd_list(),
        "role_lang_counts":          _dd_counter(),
        "role_framework_counts":     _dd_counter(),
        "role_db_counts":            _dd_counter(),
        "role_platform_counts":      _dd_counter(),
        "role_ai_counts":            _dd_counter(),
        "role_remote_counts":        _dd_counter(),
        "role_org_size_counts":      _dd_counter(),
        "role_ic_pm_counts":         _dd_counter(),
        "role_lang_want":            _dd_counter(),
        "role_framework_want":       _dd_counter(),
        "role_job_sat_counts":       _dd_counter(),
        "role_industry_counts":      _dd_counter(),
    }

    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)
        raw_header = reader.fieldnames or []
        header = [h.strip().strip('"') for h in raw_header]
        reader.fieldnames = header

        # Resolve column names
        c = {
            "comp":         _find_col(header, _COL_COMP),
            "devtype":      _find_col(header, _COL_DEVTYPE),
            "country":      _find_col(header, _COL_COUNTRY),
            "years_pro":    _find_col(header, _COL_YEARS_PRO),
            "years_code":   _find_col(header, _COL_YEARS_CODE),
            "employment":   _find_col(header, _COL_EMPLOYMENT),
            "remote":       _find_col(header, _COL_REMOTE),
            "lang":         _find_col(header, _COL_LANGUAGE),
            "lang_want":    _find_col(header, _COL_LANGUAGE_WANT),
            "db":           _find_col(header, _COL_DATABASE),
            "db_want":      _find_col(header, _COL_DATABASE_WANT),
            "platform":     _find_col(header, _COL_PLATFORM),
            "platform_want": _find_col(header, _COL_PLATFORM_WANT),
            "framework":    _find_col(header, _COL_FRAMEWORK),
            "framework_want": _find_col(header, _COL_FRAMEWORK_WANT),
            "misc":         _find_col(header, _COL_MISC_TECH),
            "misc_want":    _find_col(header, _COL_MISC_WANT),
            "tools":        _find_col(header, _COL_TOOLS),
            "tools_want":   _find_col(header, _COL_TOOLS_WANT),
            "collab":       _find_col(header, _COL_COLLAB),
            "collab_want":  _find_col(header, _COL_COLLAB_WANT),
            "os":           _find_col(header, _COL_OS),
            "ai_search":    _find_col(header, _COL_AI_SEARCH),
            "ai_search_want": _find_col(header, _COL_AI_SEARCH_WANT),
            "ai_dev":       _find_col(header, _COL_AI_DEV),
            "ai_dev_want":  _find_col(header, _COL_AI_DEV_WANT),
            "ai_models":    _find_col(header, _COL_AI_MODELS),
            "ai_sent":      _find_col(header, _COL_AI_SENT),
            "org_size":     _find_col(header, _COL_ORG_SIZE),
            "ed_level":     _find_col(header, _COL_ED_LEVEL),
            "learn_code":   _find_col(header, _COL_LEARN_CODE),
            "learn_online": _find_col(header, _COL_LEARN_ONLINE),
            "job_sat":      _find_col(header, _COL_JOB_SAT),
            "ic_pm":        _find_col(header, _COL_IC_OR_PM),
            "industry":     _find_col(header, _COL_INDUSTRY),
            "main_branch":  _find_col(header, _COL_MAIN_BRANCH),
            "age":          _find_col(header, _COL_AGE),
        }
        found = [k for k, v in c.items() if v]
        print(f"    {len(found)}/{len(c)} columns resolved: {', '.join(found[:12])}{'...' if len(found) > 12 else ''}")

        def _get(row: dict, key: str) -> str:
            col = c.get(key)
            return (row.get(col or "", "") or "").strip() if col else ""

        for row in reader:
            row = {k.strip().strip('"'): v for k, v in row.items() if k}
            stats["total"] += 1

            country  = _get(row, "country")
            roles    = [_DEVTYPE_NORM.get(dt, dt) for dt in _split(_get(row, "devtype"))]
            langs    = _split(_get(row, "lang"))
            langs_w  = _split(_get(row, "lang_want"))
            dbs      = _split(_get(row, "db"))
            dbs_w    = _split(_get(row, "db_want"))
            platforms = _split(_get(row, "platform"))
            plat_w   = _split(_get(row, "platform_want"))
            frameworks = _split(_get(row, "framework"))
            fw_w     = _split(_get(row, "framework_want"))
            miscs    = _split(_get(row, "misc"))
            miscs_w  = _split(_get(row, "misc_want"))
            tools    = _split(_get(row, "tools"))
            tools_w  = _split(_get(row, "tools_want"))
            collabs  = _split(_get(row, "collab"))
            collab_w = _split(_get(row, "collab_want"))
            oss      = _split(_get(row, "os"))
            ai_s     = _split(_get(row, "ai_search"))
            ai_sw    = _split(_get(row, "ai_search_want"))
            ai_d     = _split(_get(row, "ai_dev"))
            ai_dw    = _split(_get(row, "ai_dev_want"))
            ai_m     = _split(_get(row, "ai_models"))
            remote   = _get(row, "remote")
            org_size = _get(row, "org_size")
            ed_raw   = _get(row, "ed_level")
            ed_level = _ED_NORM.get(ed_raw, ed_raw) if ed_raw else ""
            learn    = _split(_get(row, "learn_code"))
            learn_on = _split(_get(row, "learn_online"))
            job_sat  = _get(row, "job_sat")
            ic_pm    = _get(row, "ic_pm")
            industry = _get(row, "industry")
            main_br  = _get(row, "main_branch")
            age      = _get(row, "age")
            employ   = _split(_get(row, "employment"))
            ai_sent  = _get(row, "ai_sent")

            xp = _parse_years(_get(row, "years_pro"))
            xp_band: str | None = None
            for band, lo, hi in _XP_BANDS:
                if xp is not None and lo <= xp <= hi:
                    xp_band = band
                    break

            # ── Global counters (all respondents) ─────────────────────────────
            for t in langs:       stats["lang_counts"][t] += 1
            for t in langs_w:     stats["lang_want_counts"][t] += 1
            for t in dbs:         stats["db_counts"][t] += 1
            for t in dbs_w:       stats["db_want_counts"][t] += 1
            for t in platforms:   stats["platform_counts"][t] += 1
            for t in plat_w:      stats["platform_want_counts"][t] += 1
            for t in frameworks:  stats["framework_counts"][t] += 1
            for t in fw_w:        stats["framework_want_counts"][t] += 1
            for t in miscs:       stats["misc_tech_counts"][t] += 1
            for t in miscs_w:     stats["misc_want_counts"][t] += 1
            for t in tools:       stats["tools_counts"][t] += 1
            for t in tools_w:     stats["tools_want_counts"][t] += 1
            for t in collabs:     stats["collab_counts"][t] += 1
            for t in collab_w:    stats["collab_want_counts"][t] += 1
            for t in oss:         stats["os_counts"][t] += 1
            for t in ai_s:        stats["ai_search_counts"][t] += 1
            for t in ai_sw:       stats["ai_search_want"][t] += 1
            for t in ai_d:        stats["ai_dev_counts"][t] += 1
            for t in ai_dw:       stats["ai_dev_want"][t] += 1
            for t in ai_m:        stats["ai_model_counts"][t] += 1
            for t in learn:       stats["learn_code_counts"][t] += 1
            for t in learn_on:    stats["learn_online_counts"][t] += 1
            for t in employ:      stats["employment_counts"][t] += 1
            if remote:            stats["remote_counts"][remote] += 1
            if org_size:          stats["org_size_counts"][org_size] += 1
            if ed_level:          stats["ed_level_counts"][ed_level] += 1
            if job_sat:           stats["job_sat_counts"][job_sat] += 1
            if ic_pm:             stats["ic_pm_counts"][ic_pm] += 1
            if industry:          stats["industry_counts"][industry] += 1
            if main_br:           stats["main_branch_counts"][main_br] += 1
            if age:               stats["age_counts"][age] += 1
            if ai_sent:           stats["ai_sent_counts"][ai_sent] += 1

            # ── Per-country counters ───────────────────────────────────────────
            if country:
                stats["country_total"][country] += 1
                for t in langs:      stats["country_lang_counts"][country][t] += 1
                for t in langs_w:    stats["country_lang_want"][country][t] += 1
                for t in frameworks: stats["country_framework_counts"][country][t] += 1
                for t in fw_w:       stats["country_framework_want"][country][t] += 1
                for t in dbs:        stats["country_db_counts"][country][t] += 1
                for t in dbs_w:      stats["country_db_want"][country][t] += 1
                for t in platforms:  stats["country_platform_counts"][country][t] += 1
                if remote:           stats["country_remote_counts"][country][remote] += 1
                if org_size:         stats["country_org_size_counts"][country][org_size] += 1
                if ed_level:         stats["country_ed_counts"][country][ed_level] += 1
                if job_sat:          stats["country_job_sat_counts"][country][job_sat] += 1
                for role in roles:   stats["country_role_counts"][country][role] += 1
                for t in (ai_s + ai_d + ai_m):
                    stats["country_ai_counts"][country][t] += 1

            # ── Per-role counters ─────────────────────────────────────────────
            for role in roles:
                stats["role_total"][role] += 1
                for t in langs:      stats["role_lang_counts"][role][t] += 1
                for t in langs_w:    stats["role_lang_want"][role][t] += 1
                for t in frameworks: stats["role_framework_counts"][role][t] += 1
                for t in fw_w:       stats["role_framework_want"][role][t] += 1
                for t in dbs:        stats["role_db_counts"][role][t] += 1
                for t in platforms:  stats["role_platform_counts"][role][t] += 1
                for t in (ai_s + ai_d + ai_m):
                    stats["role_ai_counts"][role][t] += 1
                if remote:           stats["role_remote_counts"][role][remote] += 1
                if org_size:         stats["role_org_size_counts"][role][org_size] += 1
                if ic_pm:            stats["role_ic_pm_counts"][role][ic_pm] += 1
                if industry:         stats["role_industry_counts"][role][industry] += 1
                if job_sat:          stats["role_job_sat_counts"][role][job_sat] += 1

            # ── Salary-gated stats ────────────────────────────────────────────
            comp = _parse_comp(_get(row, "comp"))
            if comp is None:
                continue
            stats["total_with_salary"] += 1
            stats["salary_all"].append(comp)

            if country:
                stats["salary_by_country"][country].append(comp)
            if ed_level:
                stats["salary_by_ed"][ed_level].append(comp)
            if ic_pm:
                stats["salary_by_ic_pm"][ic_pm].append(comp)
            if industry:
                stats["salary_by_industry"][industry].append(comp)
            if xp_band:
                stats["salary_by_xp"][xp_band].append(comp)

            for t in langs:      stats["salary_by_lang"][t].append(comp)
            for t in frameworks: stats["salary_by_framework"][t].append(comp)
            for t in dbs:        stats["salary_by_db"][t].append(comp)
            for t in platforms:  stats["salary_by_platform"][t].append(comp)
            for t in miscs:      stats["salary_by_misc"][t].append(comp)

            for role in roles:
                stats["salary_by_role"][role].append(comp)
                if country:
                    stats["role_country_salary"][role][country].append(comp)
                if xp_band:
                    stats["role_xp_salary"][role][xp_band].append(comp)
            if country:
                for role in roles:
                    stats["country_salary_by_role"][country][role].append(comp)
                if xp_band:
                    stats["country_salary_by_xp"][country][xp_band].append(comp)

    global_med = _percentile(stats["salary_all"], 50)
    print(
        f"    {stats['total']:,} respondents  "
        f"{stats['total_with_salary']:,} with salary  "
        f"global median {_fmt_usd(global_med)}"
    )
    return stats


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _salary_row(label: str, vals: list[float], prev_vals: list[float] | None = None,
                year: int | None = None, prev_year: int | None = None) -> str:
    if not vals:
        return ""
    p25 = _percentile(vals, 25)
    med = _percentile(vals, 50)
    p75 = _percentile(vals, 75)
    yoy = ""
    if prev_vals and len(prev_vals) >= 30:
        prev_med = _percentile(prev_vals, 50)
        delta = (med - prev_med) / prev_med * 100
        yr_label = f"{prev_year}→{year}" if prev_year else ""
        yoy = f"  ({delta:+.1f}% {yr_label})"
    return (
        f"  {label:<42} {len(vals):>5,}  {_fmt_usd(p25):>9}  "
        f"{_fmt_usd(med):>9}  {_fmt_usd(p75):>9}{yoy}"
    )


def _tech_table(lines: list[str], header: str, items: list[tuple[str, int, float]],
                width: int = 38) -> None:
    if not items:
        return
    lines += [header, "─" * (width + 18),
              f"  {'Technology':<{width}} {'Users':>7}  {'% of all':>9}"]
    for label, cnt, pct in items:
        lines.append(f"  {label:<{width}} {cnt:>7,}  {pct:>8.1f}%")
    lines.append("")


def _pct_table(lines: list[str], header: str, items: list[tuple[str, int, float]],
               width: int = 42) -> None:
    if not items:
        return
    lines += [header, "─" * (width + 12)]
    for label, cnt, pct in items:
        bar = "█" * int(pct / 4)
        lines.append(f"  {label:<{width}} {pct:5.1f}%  {bar}")
    lines.append("")


# ── Tier 1: Global document builders ─────────────────────────────────────────


def _survey_overview_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Stack Overflow Developer Survey — Overview {years[0]}–{latest}"
    lines = [heading, "=" * len(heading), "",
             "The Stack Overflow Annual Developer Survey is the world's largest developer",
             "survey, tracking technology adoption, compensation, and working conditions.",
             f"Data is publicly available under ODbL 1.0 at survey.stackoverflow.co/datasets/",
             ""]

    lines += [f"{'Year':<6} {'Respondents':>13}  {'With Salary':>13}  {'Global Median (USD)':>20}",
              "─" * 60]
    for y in years:
        s = all_stats[y]
        med = _percentile(s["salary_all"], 50) if s["salary_all"] else 0
        lines.append(
            f"  {y:<4} {s['total']:>13,}  {s['total_with_salary']:>13,}  {_fmt_usd(med):>20}"
        )
    lines.append("")

    # Professional developer breakdown
    s_latest = all_stats[latest]
    branch_total = sum(s_latest["main_branch_counts"].values())
    if branch_total > 0:
        lines += [f"Respondent Profile ({latest})", "─" * 30]
        for branch, cnt in s_latest["main_branch_counts"].most_common(5):
            pct = cnt / branch_total * 100
            lines.append(f"  {branch[:60]:<60} {pct:.1f}%")
        lines.append("")

    # Top 15 languages
    total = s_latest["total"]
    lines += [f"Top 15 Programming Languages ({latest})", "─" * 40]
    for lang, cnt in s_latest["lang_counts"].most_common(15):
        pct = cnt / total * 100
        lines.append(f"  {lang:<32} {pct:5.1f}%")
    lines.append("")

    # AI adoption summary if available
    ai_combined: collections.Counter = collections.Counter()
    ai_combined.update(s_latest["ai_search_counts"])
    ai_combined.update(s_latest["ai_dev_counts"])
    ai_combined.update(s_latest["ai_model_counts"])
    if ai_combined:
        lines += [f"Top AI Tools ({latest})", "─" * 30]
        for tool, cnt in ai_combined.most_common(8):
            pct = cnt / total * 100
            lines.append(f"  {tool:<40} {pct:5.1f}%")
        lines.append("")

    lines += [
        f"Note: Salary figures are self-reported USD gross annual compensation.",
        f"      US respondents typically represent ~25–35% of responses and skew the global median.",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}",
        f"        https://survey.stackoverflow.co/datasets/",
    ]
    return {
        "id": f"so-survey-global-overview-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Developer Survey Overview",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["developer-survey", "stackoverflow", "overview", "technology", str(latest)],
    }


def _role_salary_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    prev = latest - 1
    s = all_stats[latest]
    sp = all_stats.get(prev, {})
    heading = f"Developer Salary Benchmarks by Role {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"Based on {s['total_with_salary']:,} full responses with salary data",
             f"(N={s['total']:,} total respondents, {latest} Stack Overflow Annual Developer Survey).",
             "Compensation in USD gross annual. Self-reported figures.",
             ""]

    lines += [f"{'Role':<42} {'N':>6}  {'P25':>9}  {'Median':>9}  {'P75':>9}  YoY",
              "─" * 90]
    role_rows = [
        (role, vals)
        for role, vals in s["salary_by_role"].items()
        if len(vals) >= 80 and role not in ("Student", "Other")
    ]
    role_rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)
    for role, vals in role_rows[:20]:
        prev_vals = sp.get("salary_by_role", {}).get(role, [])
        row = _salary_row(role, vals, prev_vals, latest, prev)
        if row:
            lines.append(row)

    lines += ["", "P25 = 25th percentile, P75 = 75th percentile."]

    # IC vs PM salary split
    ic_pm_data = {k: v for k, v in s["salary_by_ic_pm"].items() if len(v) >= 30}
    if ic_pm_data:
        lines += ["", "Individual Contributor vs People Manager Salary", "─" * 50,
                  f"{'Category':<40} {'N':>6}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for category, vals in sorted(ic_pm_data.items(), key=lambda x: -_percentile(x[1], 50)):
            row = _salary_row(category, vals)
            if row:
                lines.append(row)

    # Top industries by salary
    ind_rows = [(ind, vals) for ind, vals in s["salary_by_industry"].items() if len(vals) >= 50]
    ind_rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)
    if ind_rows:
        lines += ["", f"Median Salary by Industry ({latest})", "─" * 55,
                  f"{'Industry':<40} {'N':>6}  {'Median':>9}"]
        for ind, vals in ind_rows[:12]:
            med = _percentile(vals, 50)
            lines.append(f"  {ind:<40} {len(vals):>6,}  {_fmt_usd(med):>9}")

    lines += ["",
              f"Source: Stack Overflow Annual Developer Survey {latest}",
              "Note: Samples vary by role. Roles with < 80 salary responses excluded."]
    return {
        "id": f"so-survey-salary-by-role-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "developer", "compensation", "role", "stackoverflow", str(latest)],
    }


def _xp_salary_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    heading = f"Developer Salary by Years of Experience {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "How compensation grows with professional coding experience.",
             f"Based on {s['total_with_salary']:,} salary responses, {latest} Stack Overflow Survey.",
             ""]

    # Global XP curve
    lines += ["Global Salary Growth Curve", "─" * 60,
              f"{'Experience':<16} {'N':>6}  {'P25':>9}  {'Median':>9}  {'P75':>9}  Uplift vs junior",
              "─" * 72]
    junior_med: float | None = None
    for band, _, _ in _XP_BANDS:
        vals = s["salary_by_xp"].get(band, [])
        if not vals:
            continue
        med = _percentile(vals, 50)
        if junior_med is None:
            junior_med = med
        uplift = f"  baseline" if junior_med == med else f"  +{(med - junior_med) / junior_med * 100:.0f}%"
        lines.append(
            f"  {band:<14} {len(vals):>6,}  "
            f"{_fmt_usd(_percentile(vals,25)):>9}  "
            f"{_fmt_usd(med):>9}  "
            f"{_fmt_usd(_percentile(vals,75)):>9}{uplift}"
        )
    lines.append("")

    # Per-role XP curves for key roles
    key_roles = ["Full-Stack Developer", "Back-End Developer", "Data Scientist / ML",
                 "DevOps / SRE", "Engineering Manager", "Data Engineer"]
    for role in key_roles:
        role_xp = s["role_xp_salary"].get(role, {})
        xp_rows = [(b, role_xp.get(b, [])) for b, _, _ in _XP_BANDS if role_xp.get(b)]
        if len(xp_rows) < 3:
            continue
        lines += [f"{role} — Salary by Experience", "─" * 55,
                  f"{'Experience':<16} {'N':>6}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for band, vals in xp_rows:
            if len(vals) >= 20:
                lines.append(
                    f"  {band:<14} {len(vals):>6,}  "
                    f"{_fmt_usd(_percentile(vals,25)):>9}  "
                    f"{_fmt_usd(_percentile(vals,50)):>9}  "
                    f"{_fmt_usd(_percentile(vals,75)):>9}"
                )
        lines.append("")

    lines += [
        "Key insight: Developers with 6–10 years of experience typically earn 2–3× the",
        "median of those with < 1 year. Growth accelerates at the senior/staff transition.",
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
    ]
    return {
        "id": f"so-survey-salary-by-experience-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "experience", "career-growth", "compensation", "stackoverflow", str(latest)],
    }


def _country_salary_comparison_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    prev = latest - 1
    s_cur = all_stats[latest]
    s_prev = all_stats.get(prev, {})
    heading = f"Developer Salary by Country {prev}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"Median gross annual compensation in USD for professional developers.",
             f"Combined {prev} and {latest} Stack Overflow Annual Developer Survey.",
             ""]

    lines += [f"{'Country':<34} {'Region':<14} {prev} Median   {latest} Median  YoY   N",
              "─" * 88]
    country_rows: list[tuple[str, str, float | None, float, int]] = []
    for country in _FEATURED_COUNTRIES:
        cur_vals  = s_cur["salary_by_country"].get(country, [])
        prev_vals = s_prev.get("salary_by_country", {}).get(country, [])
        if len(cur_vals) < 25:
            continue
        cur_med  = _percentile(cur_vals, 50)
        prev_med = _percentile(prev_vals, 50) if len(prev_vals) >= 25 else None
        region = _COUNTRY_REGION.get(country, "Other")
        country_rows.append((country, region, prev_med, cur_med, len(cur_vals)))

    country_rows.sort(key=lambda x: x[3], reverse=True)
    for country, region, prev_med, cur_med, n in country_rows:
        prev_str = _fmt_usd(prev_med) if prev_med else "  n/a    "
        yoy_str = ""
        if prev_med:
            delta = (cur_med - prev_med) / prev_med * 100
            yoy_str = f"  {delta:+.1f}%"
        lines.append(
            f"  {country:<32} {region:<14} {prev_str:>9}   {_fmt_usd(cur_med):>9}  "
            f"{yoy_str:<7}  n={n}"
        )

    lines += [
        "",
        "Note: All figures in USD. Local purchasing power not adjusted.",
        "      Countries with < 25 salary responses excluded.",
        f"Source: Stack Overflow Annual Developer Survey {prev} and {latest}.",
    ]
    return {
        "id": f"so-survey-salary-by-country-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "country", "compensation", "global", "stackoverflow", str(latest)],
    }


def _tech_salary_premium_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    heading = f"Technology Salary Premium Analysis {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "Which technologies correlate with higher developer compensation?",
             "Premium = (median salary of users) vs global median.",
             f"Global median: {_fmt_usd(_percentile(s['salary_all'], 50))}  "
             f"(N={s['total_with_salary']:,} salary responses)",
             "Caution: High-salary countries also adopt certain techs more — use as a",
             "directional signal, not an absolute causal claim.",
             ""]

    global_med = _percentile(s["salary_all"], 50)
    min_n = 200  # minimum users for reliable premium estimate

    def _premium_table(title: str, salary_dict: dict[str, list[float]]) -> None:
        rows = [
            (tech, vals)
            for tech, vals in salary_dict.items()
            if len(vals) >= min_n
        ]
        rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)
        if not rows:
            return
        lines.append(f"{title}")
        lines.append("─" * 72)
        lines.append(f"  {'Technology':<36} {'N':>6}  {'Median':>9}  {'vs Global':>10}  {'P75':>9}")
        lines.append("  " + "─" * 68)
        for tech, vals in rows[:15]:
            med = _percentile(vals, 50)
            p75 = _percentile(vals, 75)
            premium = (med - global_med) / global_med * 100
            sign = "+" if premium >= 0 else ""
            lines.append(
                f"  {tech:<36} {len(vals):>6,}  {_fmt_usd(med):>9}  "
                f"{sign}{premium:>8.1f}%  {_fmt_usd(p75):>9}"
            )
        lines.append("")

    _premium_table("Programming Languages — Salary Premium", s["salary_by_lang"])
    _premium_table("Web Frameworks & Libraries — Salary Premium", s["salary_by_framework"])
    _premium_table("Cloud & Infrastructure Platforms — Salary Premium", s["salary_by_platform"])
    _premium_table("Database Technologies — Salary Premium", s["salary_by_db"])
    _premium_table("Miscellaneous Technologies — Salary Premium", s["salary_by_misc"])

    lines += [
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
        "Methodology: Premium computed as (median salary of technology users) vs global",
        "             median of all respondents with salary data.",
    ]
    return {
        "id": f"so-survey-tech-salary-premium-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Technology Salary Premium",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "technology", "premium", "skills", "compensation", "stackoverflow", str(latest)],
    }


def _lang_adoption_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    heading = f"Programming Language Adoption Trends {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "% of all respondents who used each language in the past year.",
             f"Based on {', '.join(str(y) for y in years)} Stack Overflow Annual Developer Surveys.",
             ""]

    latest = years[-1]
    total_latest = all_stats[latest]["total"]
    top_langs = [lang for lang, cnt in all_stats[latest]["lang_counts"].most_common(30)
                 if cnt / total_latest >= 0.02]

    header_row = f"{'Language':<30}" + "".join(f"  {y}" for y in years)
    lines += [header_row, "─" * (30 + len(years) * 7)]
    for lang in top_langs:
        row = f"  {lang:<28}"
        for y in years:
            s = all_stats[y]
            pct = s["lang_counts"].get(lang, 0) / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    if len(years) >= 2:
        y1, y2 = years[-2], years[-1]
        t1, t2 = all_stats[y1]["total"], all_stats[y2]["total"]
        growers = []
        for lang in top_langs:
            p1 = all_stats[y1]["lang_counts"].get(lang, 0) / t1 * 100
            p2 = all_stats[y2]["lang_counts"].get(lang, 0) / t2 * 100
            if p1 > 1:
                growers.append((lang, p1, p2, p2 - p1))
        growers.sort(key=lambda x: x[3], reverse=True)
        lines += ["", f"Fastest Growing {y1}→{y2}", "─" * 30]
        for lang, p1, p2, delta in growers[:6]:
            lines.append(f"  {lang:<28} {p1:.1f}% → {p2:.1f}%  ({delta:+.1f} pp)")
        lines += ["", "Declining Languages", "─" * 30]
        for lang, p1, p2, delta in sorted(growers, key=lambda x: x[3])[:6]:
            if delta < 0:
                lines.append(f"  {lang:<28} {p1:.1f}% → {p2:.1f}%  ({delta:+.1f} pp)")

    # Most desired (want to learn)
    s_l = all_stats[latest]
    if s_l["lang_want_counts"]:
        lines += ["", f"Most Desired Languages (Want to Work With, {latest})", "─" * 50]
        for lang, cnt in s_l["lang_want_counts"].most_common(12):
            pct = cnt / s_l["total"] * 100
            lines.append(f"  {lang:<32} {pct:5.1f}%")

    lines += ["",
              "Note: Respondents may list multiple languages; percentages sum > 100%.",
              f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}."]
    return {
        "id": f"so-survey-lang-adoption-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["programming-languages", "trends", "adoption", "stackoverflow"],
    }


def _framework_adoption_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Web Framework & Library Adoption {years[0]}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "% of respondents who worked with each framework or library.",
             ""]

    top = [fw for fw, cnt in all_stats[latest]["framework_counts"].most_common(20)
           if cnt / all_stats[latest]["total"] >= 0.02]
    lines += [f"{'Framework':<30}" + "".join(f"  {y}" for y in years),
              "─" * (30 + len(years) * 7)]
    for fw in top:
        row = f"  {fw:<28}"
        for y in years:
            s = all_stats[y]
            pct = s["framework_counts"].get(fw, 0) / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    s_l = all_stats[latest]
    if s_l["framework_want_counts"]:
        lines += ["", f"Most Desired Frameworks (Want to Work With, {latest})", "─" * 50]
        for fw, cnt in s_l["framework_want_counts"].most_common(12):
            pct = cnt / s_l["total"] * 100
            lines.append(f"  {fw:<32} {pct:5.1f}%")

    lines += ["", f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}."]
    return {
        "id": f"so-survey-framework-adoption-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Technology Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["frameworks", "libraries", "web", "trends", "stackoverflow"],
    }


def _db_adoption_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Database Technology Adoption {years[0]}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "% of respondents who worked with each database technology.",
             ""]

    top = [db for db, cnt in all_stats[latest]["db_counts"].most_common(20)
           if cnt / all_stats[latest]["total"] >= 0.01]
    lines += [f"{'Database':<30}" + "".join(f"  {y}" for y in years),
              "─" * (30 + len(years) * 7)]
    for db in top:
        row = f"  {db:<28}"
        for y in years:
            s = all_stats[y]
            pct = s["db_counts"].get(db, 0) / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    s_l = all_stats[latest]
    if s_l["db_want_counts"]:
        lines += ["", f"Most Desired Databases (Want to Work With, {latest})", "─" * 48]
        for db, cnt in s_l["db_want_counts"].most_common(12):
            pct = cnt / s_l["total"] * 100
            lines.append(f"  {db:<32} {pct:5.1f}%")

    lines += ["", f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}."]
    return {
        "id": f"so-survey-db-adoption-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Technology Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["databases", "sql", "nosql", "trends", "stackoverflow"],
    }


def _cloud_adoption_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Cloud & Infrastructure Platform Adoption {years[0]}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "% of respondents who worked with each cloud or infrastructure platform.",
             ""]

    top = [pl for pl, cnt in all_stats[latest]["platform_counts"].most_common(15)
           if cnt / all_stats[latest]["total"] >= 0.01]
    lines += [f"{'Platform':<30}" + "".join(f"  {y}" for y in years),
              "─" * (30 + len(years) * 7)]
    for pl in top:
        row = f"  {pl:<28}"
        for y in years:
            s = all_stats[y]
            pct = s["platform_counts"].get(pl, 0) / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    s_l = all_stats[latest]
    if s_l["platform_want_counts"]:
        lines += ["", f"Most Desired Platforms (Want to Work With, {latest})", "─" * 48]
        for pl, cnt in s_l["platform_want_counts"].most_common(10):
            pct = cnt / s_l["total"] * 100
            lines.append(f"  {pl:<32} {pct:5.1f}%")

    lines += ["", f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}."]
    return {
        "id": f"so-survey-cloud-adoption-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Technology Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["cloud", "aws", "azure", "gcp", "infrastructure", "stackoverflow"],
    }


def _ai_adoption_doc(all_stats: dict[int, dict], idx: int) -> dict:
    ai_years = {y: s for y, s in all_stats.items() if y >= 2023}
    if not ai_years:
        # Fall back to all years if no 2023+ data
        ai_years = all_stats
    years = sorted(ai_years)
    latest = years[-1]
    heading = f"AI Tool Adoption & Developer Sentiment {years[0]}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "Tracking AI coding assistant, search, and model usage across the developer community.",
             "AI-specific survey questions were introduced in the 2023 edition.",
             ""]

    for y in years:
        s = ai_years[y]
        total = s["total"]
        combined: collections.Counter = collections.Counter()
        combined.update(s["ai_search_counts"])
        combined.update(s["ai_dev_counts"])
        combined.update(s["ai_model_counts"])
        if not combined:
            continue
        lines += [f"── {y} AI Tool Usage (% of all {total:,} respondents) ──────────────────",
                  f"  {'Tool':<42} {'% using':>8}",
                  "  " + "─" * 52]
        for tool, cnt in combined.most_common(15):
            pct = cnt / total * 100
            lines.append(f"  {tool:<42} {pct:>7.1f}%")

        # Want to use
        ai_want: collections.Counter = collections.Counter()
        ai_want.update(s["ai_search_want"])
        ai_want.update(s["ai_dev_want"])
        if ai_want:
            lines += ["", f"  Most Desired AI Tools ({y}):"]
            for tool, cnt in ai_want.most_common(8):
                pct = cnt / total * 100
                lines.append(f"    {tool:<40} {pct:.1f}%")

        # Sentiment
        sent = s["ai_sent_counts"]
        if sent:
            total_sent = sum(sent.values())
            lines += ["", f"  Developer Sentiment Toward AI ({y}):"]
            for sentiment, cnt in sorted(sent.items(), key=lambda x: -x[1]):
                pct = cnt / total_sent * 100
                lines.append(f"    {sentiment[:55]:<55} {pct:.1f}%")
        lines.append("")

    lines += [f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}."]
    return {
        "id": f"so-survey-ai-adoption-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "AI & Technology Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["ai", "copilot", "chatgpt", "llm", "tools", "trends", "stackoverflow"],
    }


def _tools_ide_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    total = s["total"]
    heading = f"Developer Tools, IDEs & Collaboration Software {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"Based on {total:,} respondents, {latest} Stack Overflow Annual Developer Survey.",
             ""]

    if s["tools_counts"]:
        _tech_table(lines, f"Developer Tools & IDEs ({latest})",
                    _top_n(s["tools_counts"], 20, total))
    if s["collab_counts"]:
        _tech_table(lines, f"Collaboration & Project Management Tools ({latest})",
                    _top_n(s["collab_counts"], 15, total))
    if s["misc_tech_counts"]:
        _tech_table(lines, f"Miscellaneous Technologies & Libraries ({latest})",
                    _top_n(s["misc_tech_counts"], 15, total))
    if s["os_counts"]:
        _tech_table(lines, f"Operating System (Professional Use, {latest})",
                    _top_n(s["os_counts"], 8, total))
    if s["tools_want_counts"]:
        lines += [f"Most Desired Tools (Want to Work With, {latest})", "─" * 48]
        for tool, cnt in s["tools_want_counts"].most_common(12):
            pct = cnt / total * 100
            lines.append(f"  {tool:<40} {pct:5.1f}%")
        lines.append("")

    lines += [f"Source: Stack Overflow Annual Developer Survey {latest}."]
    return {
        "id": f"so-survey-tools-ide-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Developer Tools",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["tools", "ide", "vscode", "collaboration", "developer", "stackoverflow"],
    }


def _remote_work_doc(all_stats: dict[int, dict], idx: int) -> dict:
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Remote Work & Employment Trends {years[0]}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "Work arrangement and employment type distribution among developers.",
             ""]

    all_remote_vals: set[str] = set()
    for s in all_stats.values():
        all_remote_vals.update(s["remote_counts"].keys())
    sorted_vals = sorted(all_remote_vals,
                         key=lambda v: all_stats[latest]["remote_counts"].get(v, 0),
                         reverse=True)

    lines += [f"{'Work Arrangement':<44}" + "".join(f"  {y}" for y in years),
              "─" * (44 + len(years) * 7)]
    for val in sorted_vals[:8]:
        row = f"  {val:<42}"
        for y in years:
            s = all_stats[y]
            total_r = sum(s["remote_counts"].values())
            cnt = s["remote_counts"].get(val, 0)
            pct = cnt / total_r * 100 if total_r else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)
    lines.append("")

    # Employment type breakdown
    s_latest = all_stats[latest]
    total_emp = sum(s_latest["employment_counts"].values())
    if total_emp:
        lines += [f"Employment Type ({latest})", "─" * 50]
        for emp, cnt in s_latest["employment_counts"].most_common(8):
            pct = cnt / total_emp * 100
            lines.append(f"  {emp:<50} {pct:5.1f}%")
        lines.append("")

    # Remote by country (featured)
    lines += [f"Remote Work Distribution by Country ({latest})", "─" * 55]
    for country in ["United States of America", "Germany", "Switzerland", "United Kingdom",
                    "France", "Netherlands", "India", "Brazil"]:
        rc = s_latest["country_remote_counts"].get(country)
        if not rc:
            continue
        total_rc = sum(rc.values())
        if total_rc < 30:
            continue
        top_mode, top_cnt = rc.most_common(1)[0]
        pct = top_cnt / total_rc * 100
        lines.append(f"  {country:<34} top mode: {top_mode:<20} ({pct:.0f}% of {total_rc:,})")
    lines.append("")

    lines += [f"Source: Stack Overflow Annual Developer Survey {years[0]}–{latest}."]
    return {
        "id": f"so-survey-remote-work-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Work Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["remote-work", "hybrid", "employment", "workplace", "stackoverflow"],
    }


def _education_learning_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    total = s["total"]
    heading = f"Developer Education Level & Learning Paths {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"How developers were educated, how they learned to code, and salary by education.",
             f"Based on {total:,} respondents, {latest} Stack Overflow Annual Developer Survey.",
             ""]

    # Education level distribution
    if s["ed_level_counts"]:
        total_ed = sum(s["ed_level_counts"].values())
        lines += [f"Highest Education Level ({latest})", "─" * 50,
                  f"{'Level':<44} {'% of devs':>10}  Median Salary"]
        for level, cnt in s["ed_level_counts"].most_common(10):
            pct = cnt / total_ed * 100
            sal_vals = s["salary_by_ed"].get(level, [])
            sal_str = _fmt_usd(_percentile(sal_vals, 50)) if sal_vals else "n/a"
            lines.append(f"  {level:<42} {pct:>8.1f}%  {sal_str}")
        lines.append("")

    # How developers learned to code
    if s["learn_code_counts"]:
        total_learn = sum(s["learn_code_counts"].values())
        lines += [f"How Developers Learned to Code ({latest})", "─" * 50,
                  f"{'Method':<50} {'% citing':>10}"]
        for method, cnt in s["learn_code_counts"].most_common(12):
            pct = cnt / total_learn * 100
            lines.append(f"  {method[:48]:<48} {pct:>8.1f}%")
        lines.append("")

    # Online learning resources
    if s["learn_online_counts"]:
        total_online = sum(s["learn_online_counts"].values())
        lines += [f"Online Learning Resources Used ({latest})", "─" * 50]
        for resource, cnt in s["learn_online_counts"].most_common(15):
            pct = cnt / total_online * 100
            lines.append(f"  {resource[:48]:<48} {pct:5.1f}%")
        lines.append("")

    lines += [
        "Key insight: Most professional developers (>50%) are largely self-taught or",
        "learned through online resources, regardless of formal education level.",
        "Bachelor's degrees remain the modal credential but are not required for high salaries.",
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
    ]
    return {
        "id": f"so-survey-education-learning-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Education & Learning",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["education", "learning", "bootcamp", "university", "self-taught", "stackoverflow"],
    }


def _job_satisfaction_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    total = s["total"]
    heading = f"Developer Job Satisfaction {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             "How satisfied are professional developers with their work?",
             f"Based on {total:,} respondents, {latest} Stack Overflow Annual Developer Survey.",
             ""]

    # Global satisfaction distribution
    if s["job_sat_counts"]:
        total_sat = sum(s["job_sat_counts"].values())
        _pct_table(lines, f"Overall Job Satisfaction ({latest})",
                   [(k, v, v / total_sat * 100) for k, v in s["job_sat_counts"].most_common()])

    # Satisfaction by role
    lines += [f"Job Satisfaction by Role ({latest})", "─" * 60,
              f"{'Role':<42} {'Most Common Response':<32} {'% satisfied'}"]
    for role, sat_counter in sorted(
        s["role_job_sat_counts"].items(),
        key=lambda x: sum(x[1].values()),
        reverse=True,
    )[:15]:
        total_role_sat = sum(sat_counter.values())
        if total_role_sat < 30:
            continue
        top_response, top_cnt = sat_counter.most_common(1)[0]
        pct = top_cnt / total_role_sat * 100
        lines.append(f"  {role:<40} {top_response[:30]:<32} {pct:.0f}%")
    lines.append("")

    # Satisfaction by country
    lines += [f"Job Satisfaction by Country — Top and Bottom ({latest})", "─" * 60]
    country_satisfaction: list[tuple[str, float]] = []
    for country, sat_counter in s["country_job_sat_counts"].items():
        if country not in _FEATURED_COUNTRIES:
            continue
        total_c = sum(sat_counter.values())
        if total_c < 30:
            continue
        # Score: assume responses are ordinal and compute % "very/slightly satisfied"
        satisfied = sum(cnt for resp, cnt in sat_counter.items()
                        if "satisfied" in resp.lower() or "happy" in resp.lower())
        country_satisfaction.append((country, satisfied / total_c * 100))

    country_satisfaction.sort(key=lambda x: x[1], reverse=True)
    if country_satisfaction:
        lines += [f"{'Country':<34} {'% satisfied or happy':>22}"]
        for country, pct in country_satisfaction[:10]:
            lines.append(f"  {country:<32} {pct:>20.1f}%")
        lines += ["", "Lowest satisfaction:"]
        for country, pct in country_satisfaction[-5:]:
            lines.append(f"  {country:<32} {pct:>20.1f}%")
    lines.append("")

    lines += [f"Source: Stack Overflow Annual Developer Survey {latest}."]
    return {
        "id": f"so-survey-job-satisfaction-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Work Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["job-satisfaction", "workplace", "happiness", "developer", "stackoverflow"],
    }


def _skills_gap_doc(all_stats: dict[int, dict], idx: int) -> dict:
    latest = max(all_stats)
    s = all_stats[latest]
    total = s["total"]
    heading = f"Developer Skills Gap: Desired vs Current Technology Use {latest}"
    lines = [heading, "=" * len(heading), "",
             "Technologies developers WANT to use vs those they currently use.",
             "The gap = (want to work with %) – (have worked with %).",
             "A positive gap means high demand for learning that technology.",
             f"Based on {total:,} respondents, {latest} Stack Overflow Annual Developer Survey.",
             ""]

    def _gap_table(title: str, have: collections.Counter, want: collections.Counter) -> None:
        rows = []
        all_techs = set(have.keys()) | set(want.keys())
        for tech in all_techs:
            have_pct = have.get(tech, 0) / total * 100
            want_pct = want.get(tech, 0) / total * 100
            gap = want_pct - have_pct
            if have_pct >= 0.5 or want_pct >= 0.5:
                rows.append((tech, have_pct, want_pct, gap))
        rows.sort(key=lambda x: x[3], reverse=True)
        if not rows:
            return
        lines.append(title)
        lines.append("─" * 72)
        lines.append(f"  {'Technology':<32} {'Have %':>7}  {'Want %':>7}  {'Gap':>7}")
        lines.append("  " + "─" * 56)
        lines.append(f"  {'— Most Desired (positive gap) —':<56}")
        for tech, hp, wp, gap in rows[:12]:
            sign = "+" if gap > 0 else ""
            lines.append(f"  {tech:<32} {hp:>6.1f}%  {wp:>6.1f}%  {sign}{gap:>5.1f}%")
        lines.append(f"  {'— Most Declining (negative gap) —':<56}")
        for tech, hp, wp, gap in sorted(rows, key=lambda x: x[3])[:8]:
            if gap < 0:
                lines.append(f"  {tech:<32} {hp:>6.1f}%  {wp:>6.1f}%  {gap:>6.1f}%")
        lines.append("")

    _gap_table(f"Programming Languages — Skills Gap ({latest})",
               s["lang_counts"], s["lang_want_counts"])
    _gap_table(f"Web Frameworks — Skills Gap ({latest})",
               s["framework_counts"], s["framework_want_counts"])
    _gap_table(f"Cloud Platforms — Skills Gap ({latest})",
               s["platform_counts"], s["platform_want_counts"])
    _gap_table(f"Databases — Skills Gap ({latest})",
               s["db_counts"], s["db_want_counts"])

    lines += [f"Source: Stack Overflow Annual Developer Survey {latest}."]
    return {
        "id": f"so-survey-skills-gap-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global", "sub_region": "Skills & Hiring Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["skills-gap", "desired-technologies", "learning", "career", "stackoverflow"],
    }


# ── Tier 2: Per-country deep-dive documents ───────────────────────────────────

def _country_deep_dive_doc(country: str, all_stats: dict[int, dict], idx: int) -> dict | None:
    latest = max(all_stats)
    s = all_stats[latest]

    # Minimum sample checks
    country_n = s["country_total"].get(country, 0)
    if country_n < 50:
        return None

    region = _COUNTRY_REGION.get(country, "Global")
    heading = f"{country} — Developer Salary & Market Profile {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"Based on {country_n:,} respondents from {country}",
             f"in the {latest} Stack Overflow Annual Developer Survey.",
             ""]

    # Salary overview vs global
    country_sal = s["salary_by_country"].get(country, [])
    global_med = _percentile(s["salary_all"], 50)
    if country_sal:
        c_med = _percentile(country_sal, 50)
        c_p25 = _percentile(country_sal, 25)
        c_p75 = _percentile(country_sal, 75)
        premium = (c_med - global_med) / global_med * 100 if global_med else 0
        sign = "+" if premium >= 0 else ""
        lines += [
            "Salary Overview (USD Gross Annual)",
            "─" * 40,
            f"  Respondents with salary data:  {len(country_sal):,}",
            f"  25th percentile (P25):         {_fmt_usd(c_p25)}",
            f"  Median:                        {_fmt_usd(c_med)}",
            f"  75th percentile (P75):         {_fmt_usd(c_p75)}",
            f"  vs global median:              {sign}{premium:.1f}%",
            "",
        ]

    # Salary by role
    role_sal = s["country_salary_by_role"].get(country, {})
    role_rows = [(r, v) for r, v in role_sal.items() if len(v) >= 10]
    role_rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)
    if role_rows:
        lines += [f"Salary by Developer Role ({country}, {latest})", "─" * 66,
                  f"  {'Role':<40} {'N':>5}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for role, vals in role_rows[:12]:
            row = _salary_row(role, vals)
            if row:
                lines.append(row)
        lines.append("")

    # Salary by experience
    xp_sal = s["country_salary_by_xp"].get(country, {})
    xp_rows = [(b, xp_sal.get(b, [])) for b, _, _ in _XP_BANDS if xp_sal.get(b)]
    xp_rows = [(b, v) for b, v in xp_rows if len(v) >= 10]
    if xp_rows:
        lines += [f"Salary by Years of Experience ({country})", "─" * 58,
                  f"  {'Experience':<16} {'N':>5}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for band, vals in xp_rows:
            lines.append(
                f"  {band:<16} {len(vals):>5,}  "
                f"{_fmt_usd(_percentile(vals,25)):>9}  "
                f"{_fmt_usd(_percentile(vals,50)):>9}  "
                f"{_fmt_usd(_percentile(vals,75)):>9}"
            )
        lines.append("")

    # Top languages (used & desired)
    c_lang = s["country_lang_counts"].get(country)
    c_lang_w = s["country_lang_want"].get(country)
    if c_lang:
        lines += [f"Top Programming Languages ({country}, {latest})", "─" * 50,
                  f"  {'Language':<30} {'Used %':>8}  {'Desired %':>10}"]
        for lang, cnt in c_lang.most_common(12):
            used_pct  = cnt / country_n * 100
            want_cnt  = c_lang_w.get(lang, 0) if c_lang_w else 0
            want_pct  = want_cnt / country_n * 100
            lines.append(f"  {lang:<30} {used_pct:>7.1f}%  {want_pct:>9.1f}%")
        lines.append("")

    # Top frameworks (used & desired)
    c_fw = s["country_framework_counts"].get(country)
    c_fw_w = s["country_framework_want"].get(country)
    if c_fw:
        lines += [f"Top Web Frameworks ({country}, {latest})", "─" * 50,
                  f"  {'Framework':<30} {'Used %':>8}  {'Desired %':>10}"]
        for fw, cnt in c_fw.most_common(10):
            used_pct = cnt / country_n * 100
            want_cnt = c_fw_w.get(fw, 0) if c_fw_w else 0
            want_pct = want_cnt / country_n * 100
            lines.append(f"  {fw:<30} {used_pct:>7.1f}%  {want_pct:>9.1f}%")
        lines.append("")

    # Top databases
    c_db = s["country_db_counts"].get(country)
    if c_db:
        lines += [f"Top Databases ({country}, {latest})", "─" * 40]
        for db, cnt in c_db.most_common(8):
            pct = cnt / country_n * 100
            lines.append(f"  {db:<30} {pct:5.1f}%")
        lines.append("")

    # Top cloud platforms
    c_pl = s["country_platform_counts"].get(country)
    if c_pl:
        lines += [f"Top Cloud Platforms ({country}, {latest})", "─" * 40]
        for pl, cnt in c_pl.most_common(6):
            pct = cnt / country_n * 100
            lines.append(f"  {pl:<30} {pct:5.1f}%")
        lines.append("")

    # AI tool adoption
    c_ai = s["country_ai_counts"].get(country)
    if c_ai:
        lines += [f"AI Tools Used ({country}, {latest})", "─" * 40]
        for tool, cnt in c_ai.most_common(8):
            pct = cnt / country_n * 100
            lines.append(f"  {tool:<40} {pct:5.1f}%")
        lines.append("")

    # Remote work
    c_remote = s["country_remote_counts"].get(country)
    if c_remote:
        total_remote = sum(c_remote.values())
        _pct_table(lines, f"Remote Work Arrangement ({country})",
                   [(k, v, v / total_remote * 100) for k, v in c_remote.most_common()])

    # Org size
    c_org = s["country_org_size_counts"].get(country)
    if c_org:
        total_org = sum(c_org.values())
        lines += [f"Company Size Distribution ({country})", "─" * 48]
        for size, cnt in c_org.most_common(8):
            pct = cnt / total_org * 100
            lines.append(f"  {size[:46]:<46} {pct:5.1f}%")
        lines.append("")

    # Education level
    c_ed = s["country_ed_counts"].get(country)
    if c_ed:
        total_ed = sum(c_ed.values())
        lines += [f"Education Level ({country})", "─" * 40]
        for level, cnt in c_ed.most_common(6):
            pct = cnt / total_ed * 100
            lines.append(f"  {level:<42} {pct:5.1f}%")
        lines.append("")

    # Job satisfaction
    c_sat = s["country_job_sat_counts"].get(country)
    if c_sat:
        total_sat = sum(c_sat.values())
        lines += [f"Job Satisfaction ({country})", "─" * 40]
        for resp, cnt in c_sat.most_common(6):
            pct = cnt / total_sat * 100
            lines.append(f"  {resp[:46]:<46} {pct:5.1f}%")
        lines.append("")

    lines += [
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
        "Note: All salary figures in USD gross annual (self-reported). Sample sizes",
        "      vary; role-level data with n < 10 excluded from salary tables.",
    ]

    tags = [_slug(country), "salary", "developer", "market", "stackoverflow", str(latest)]
    if country in ("Switzerland", "Germany", "France", "Netherlands", "Sweden"):
        tags += ["eu", "europe"]
    if country == "Switzerland":
        tags.append("swiss")

    return {
        "id": f"so-survey-country-{_slug(country)}-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": region,
        "sub_region": country,
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": tags,
    }


# ── Tier 3: Per-role deep-dive documents ──────────────────────────────────────

def _role_deep_dive_doc(role: str, all_stats: dict[int, dict], idx: int) -> dict | None:
    latest = max(all_stats)
    prev = latest - 1
    s = all_stats[latest]
    sp = all_stats.get(prev, {})

    role_n = s["role_total"].get(role, 0)
    if role_n < 100:
        return None

    heading = f"{role} — Global Market Profile {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), "",
             f"Based on {role_n:,} respondents identifying as {role}",
             f"in the {latest} Stack Overflow Annual Developer Survey.",
             ""]

    # Global salary for this role
    role_sal = s["salary_by_role"].get(role, [])
    if role_sal:
        global_med = _percentile(s["salary_all"], 50)
        r_med = _percentile(role_sal, 50)
        r_p25 = _percentile(role_sal, 25)
        r_p75 = _percentile(role_sal, 75)
        premium = (r_med - global_med) / global_med * 100 if global_med else 0
        sign = "+" if premium >= 0 else ""
        lines += [
            "Global Compensation (USD Gross Annual)",
            "─" * 42,
            f"  Respondents with salary data:  {len(role_sal):,}",
            f"  25th percentile (P25):         {_fmt_usd(r_p25)}",
            f"  Median:                        {_fmt_usd(r_med)}",
            f"  75th percentile (P75):         {_fmt_usd(r_p75)}",
            f"  vs all-developer global median: {sign}{premium:.1f}%",
        ]
        # YoY
        prev_role_sal = sp.get("salary_by_role", {}).get(role, [])
        if len(prev_role_sal) >= 30:
            prev_med = _percentile(prev_role_sal, 50)
            yoy = (r_med - prev_med) / prev_med * 100
            lines.append(f"  YoY change ({prev}→{latest}):            {yoy:+.1f}%")
        lines.append("")

    # Salary by country
    rc_sal = s["role_country_salary"].get(role, {})
    country_rows = [
        (country, vals)
        for country, vals in rc_sal.items()
        if len(vals) >= 10 and country in _FEATURED_COUNTRIES
    ]
    country_rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)
    if country_rows:
        lines += [f"Salary by Country (top countries, n ≥ 10)", "─" * 62,
                  f"  {'Country':<30} {'N':>5}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for country, vals in country_rows[:15]:
            lines.append(
                f"  {country:<30} {len(vals):>5,}  "
                f"{_fmt_usd(_percentile(vals,25)):>9}  "
                f"{_fmt_usd(_percentile(vals,50)):>9}  "
                f"{_fmt_usd(_percentile(vals,75)):>9}"
            )
        lines.append("")

    # Salary by experience
    rxp_sal = s["role_xp_salary"].get(role, {})
    xp_rows = [(b, rxp_sal.get(b, [])) for b, _, _ in _XP_BANDS if rxp_sal.get(b)]
    xp_rows = [(b, v) for b, v in xp_rows if len(v) >= 10]
    if xp_rows:
        lines += [f"Salary by Years of Experience", "─" * 54,
                  f"  {'Experience':<16} {'N':>5}  {'P25':>9}  {'Median':>9}  {'P75':>9}"]
        for band, vals in xp_rows:
            lines.append(
                f"  {band:<16} {len(vals):>5,}  "
                f"{_fmt_usd(_percentile(vals,25)):>9}  "
                f"{_fmt_usd(_percentile(vals,50)):>9}  "
                f"{_fmt_usd(_percentile(vals,75)):>9}"
            )
        lines.append("")

    # Technologies
    role_total_for_pct = role_n
    for label, counter_key in [
        (f"Most Used Programming Languages", "role_lang_counts"),
        (f"Most Used Web Frameworks", "role_framework_counts"),
        (f"Most Used Databases", "role_db_counts"),
        (f"Most Used Cloud Platforms", "role_platform_counts"),
    ]:
        counter = s[counter_key].get(role)
        if not counter:
            continue
        lines += [f"{label} ({role}, {latest})", "─" * 52]
        want_key = counter_key.replace("_counts", "_want")
        want_counter = s.get(want_key, {}).get(role, collections.Counter())
        lines.append(f"  {'Technology':<34} {'Used %':>8}  {'Desired %':>10}")
        for tech, cnt in counter.most_common(10):
            used_pct = cnt / role_total_for_pct * 100
            want_cnt = want_counter.get(tech, 0)
            want_pct = want_cnt / role_total_for_pct * 100
            lines.append(f"  {tech:<34} {used_pct:>7.1f}%  {want_pct:>9.1f}%")
        lines.append("")

    # AI tool adoption
    role_ai = s["role_ai_counts"].get(role)
    if role_ai:
        lines += [f"AI Tool Adoption ({role}, {latest})", "─" * 48]
        for tool, cnt in role_ai.most_common(8):
            pct = cnt / role_total_for_pct * 100
            lines.append(f"  {tool:<40} {pct:5.1f}%")
        lines.append("")

    # Remote work
    role_remote = s["role_remote_counts"].get(role)
    if role_remote:
        total_remote = sum(role_remote.values())
        lines += [f"Remote Work ({role})", "─" * 40]
        for mode, cnt in role_remote.most_common():
            pct = cnt / total_remote * 100
            lines.append(f"  {mode:<42} {pct:5.1f}%")
        lines.append("")

    # IC vs PM split
    role_ic_pm = s["role_ic_pm_counts"].get(role)
    if role_ic_pm:
        total_ic_pm = sum(role_ic_pm.values())
        lines += [f"Individual Contributor vs Manager ({role})", "─" * 44]
        for category, cnt in role_ic_pm.most_common():
            pct = cnt / total_ic_pm * 100
            lines.append(f"  {category:<40} {pct:5.1f}%")
        lines.append("")

    # Top industries
    role_ind = s["role_industry_counts"].get(role)
    if role_ind:
        total_ind = sum(role_ind.values())
        lines += [f"Top Industries Employing {role}", "─" * 48]
        for ind, cnt in role_ind.most_common(8):
            pct = cnt / total_ind * 100
            lines.append(f"  {ind[:48]:<48} {pct:5.1f}%")
        lines.append("")

    # Org size
    role_org = s["role_org_size_counts"].get(role)
    if role_org:
        total_org = sum(role_org.values())
        lines += [f"Company Size Distribution ({role})", "─" * 46]
        for size, cnt in role_org.most_common(6):
            pct = cnt / total_org * 100
            lines.append(f"  {size[:44]:<44} {pct:5.1f}%")
        lines.append("")

    lines += [
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
        "Note: Salary data in USD gross annual (self-reported).",
        "      Country-level data requires n ≥ 10 per role × country cell.",
    ]

    role_tag = _slug(role)
    return {
        "id": f"so-survey-role-{role_tag}-{idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": role,
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", role_tag, "developer", "role", "compensation", "stackoverflow", str(latest)],
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_surveys(
    survey_dir: str | None,
    output_dir: str,
    years: list[int] | None = None,
    dry_run: bool = False,
    skip_download: bool = False,
) -> list[dict]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    output_file = out_path / "market_reports_real.json"

    target_years = years or [2025, 2024, 2023, 2022]
    cache_dir = out_path / ".so_survey_cache"
    all_stats: dict[int, dict] = {}

    for year in sorted(target_years, reverse=True):
        print(f"\n[{year}] Locating survey data ...")
        csv_path: Path | None = None

        # 1. Check user-supplied survey_dir
        if survey_dir:
            csv_path = _find_survey_csv(Path(survey_dir), year)
            if csv_path:
                print(f"    Found in survey-dir: {csv_path.name}")

        # 2. Check cache
        if not csv_path and not skip_download:
            cached = _find_survey_csv(cache_dir, year)
            if cached:
                csv_path = cached
                print(f"    Found in cache: {csv_path.name}")

        # 3. Auto-download
        if not csv_path and not skip_download:
            csv_path = download_survey(year, cache_dir)

        if not csv_path:
            print(f"    SKIP {year}: no survey file found. See --help for manual download instructions.")
            continue

        print(f"    Processing {csv_path} ...")
        try:
            all_stats[year] = extract_year(csv_path, year)
        except Exception as exc:
            print(f"    ERROR processing {year}: {exc}")
            continue

    if not all_stats:
        print("No survey data processed. Aborting.")
        return []

    print(f"\nBuilding documents from years: {sorted(all_stats.keys())} ...")

    docs: list[dict] = []
    doc_idx = 1

    # ── Tier 1: Global documents ──────────────────────────────────────────────
    global_builders = [
        _survey_overview_doc,
        _role_salary_doc,
        _xp_salary_doc,
        _country_salary_comparison_doc,
        _tech_salary_premium_doc,
        _lang_adoption_doc,
        _framework_adoption_doc,
        _db_adoption_doc,
        _cloud_adoption_doc,
        _ai_adoption_doc,
        _tools_ide_doc,
        _remote_work_doc,
        _education_learning_doc,
        _job_satisfaction_doc,
        _skills_gap_doc,
    ]
    for builder in global_builders:
        try:
            doc = builder(all_stats, doc_idx)
            if doc:
                docs.append(doc)
                print(f"  [G{doc_idx:02d}] {doc['title'][:72]}")
                doc_idx += 1
        except Exception as exc:
            print(f"  WARN: {builder.__name__} failed: {exc}")

    # ── Tier 2: Per-country deep-dive documents ───────────────────────────────
    print(f"\n  Building per-country documents ...")
    for country in _COUNTRY_DOCS:
        try:
            doc = _country_deep_dive_doc(country, all_stats, doc_idx)
            if doc:
                docs.append(doc)
                print(f"  [C{doc_idx:02d}] {doc['title'][:72]}")
                doc_idx += 1
        except Exception as exc:
            print(f"  WARN: country doc {country} failed: {exc}")

    # ── Tier 3: Per-role deep-dive documents ──────────────────────────────────
    print(f"\n  Building per-role documents ...")
    latest = max(all_stats)
    s_latest = all_stats[latest]
    # Produce role docs ordered by role population
    roles_by_size = sorted(
        s_latest["role_total"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    for role, n in roles_by_size:
        if role in ("Student", "Other"):
            continue
        try:
            doc = _role_deep_dive_doc(role, all_stats, doc_idx)
            if doc:
                docs.append(doc)
                print(f"  [R{doc_idx:02d}] {doc['title'][:72]}")
                doc_idx += 1
        except Exception as exc:
            print(f"  WARN: role doc {role} failed: {exc}")

    print(f"\n  Total SO survey documents built: {len(docs)}")

    if dry_run:
        print("  [dry-run] Output NOT written.")
        return docs

    # ── Merge into market_reports_real.json ───────────────────────────────────
    existing: list[dict] = []
    if output_file.exists():
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        before = len(existing)
        existing = [d for d in existing if not d.get("id", "").startswith("so-survey-")]
        print(f"\n  Loaded {before} existing docs, kept {len(existing)} non-SO docs")

    combined = existing + docs
    output_file.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(
        f"  Written: {output_file}  ({size_kb:,} KB, {len(combined)} total documents)"
    )
    print(f"  {len(existing)} existing docs + {len(docs)} new SO survey docs")
    return docs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description="Download and convert Stack Overflow Developer Survey to KB market-report documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default=_default_out,
        help=f"Directory to write market_reports_real.json (default: {_default_out})",
    )
    parser.add_argument(
        "--survey-dir", default=None,
        help=(
            "Directory containing already-downloaded survey files "
            "(CSV or ZIP, any name containing the year). "
            "If omitted, the script attempts auto-download."
        ),
    )
    parser.add_argument(
        "--years", type=int, nargs="+", default=None,
        help="Which survey years to process (default: 2025 2024 2023 2022)",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Do not attempt auto-download; only use --survey-dir files.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build documents and print stats but do NOT write any files.",
    )
    args = parser.parse_args()

    docs = process_surveys(
        survey_dir=args.survey_dir,
        output_dir=args.output_dir,
        years=args.years,
        dry_run=args.dry_run,
        skip_download=args.skip_download,
    )

    if not args.dry_run and docs:
        print(
            "\nNext step — re-ingest market_reports namespace:\n"
            "  POST /api/v1/admin/kb/ingest\n"
            "  {\"doc_types\": [\"market_reports\"]}\n"
            "\nOr via Celery task:\n"
            "  rag.ingest_market_reports.delay(source_path='data/knowledge-base/market_reports_real.json')"
        )


if __name__ == "__main__":
    main()
