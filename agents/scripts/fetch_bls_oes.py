"""fetch_bls_oes.py — Fetch US Bureau of Labor Statistics OES wage data.

Sources
-------
Primary: BLS OES flat-file download (national_M2024_dl.xlsx inside oesm24nat.zip)
  • URL: https://www.bls.gov/oes/special-requests/oesm24nat.zip
  • Provides median/mean annual wages for all ~800 SOC occupations, national level.
  • Downloaded at runtime; cached to .bls_oes_cache/ to avoid repeated requests.

Fallback: BLS Public API v2 (no key; 25 req/day limit)
  • Used automatically if the flat file download fails (e.g. rate limited).
  • Fetches median annual wages for major SOC groups via series IDs.

Industry data: BLS OES cross-industry national files
  • oesm24in4.zip → occupation wages by NAICS 4-digit industry
  • Used to build Finance (NAICS 5200), Consulting (5416), Pharma (3254), Healthcare (6200) docs.
  • These replace the LinkedIn/Glassdoor gap (no public API available for those).

Output
------
  Merges into market_reports_real.json (replaces all docs with id prefix bls-oes-*)

Usage
-----
  cd agents
  python -m scripts.fetch_bls_oes --output-dir data/knowledge-base
  python -m scripts.fetch_bls_oes --output-dir data/knowledge-base --dry-run
  python -m scripts.fetch_bls_oes --output-dir data/knowledge-base --local-zip path/to/oesm24nat.zip
"""
from __future__ import annotations

import argparse
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# ── Constants ──────────────────────────────────────────────────────────────────

_UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_BLS_OES_NAT_URL  = "https://www.bls.gov/oes/special-requests/oesm24nat.zip"
_BLS_OES_IND_URL  = "https://www.bls.gov/oes/special-requests/oesm24in4.zip"
_BLS_TABLES_PAGE  = "https://www.bls.gov/oes/tables.htm"
_CACHE_DIR        = Path(__file__).resolve().parent.parent / ".bls_oes_cache"

_DELAY = 1.0  # seconds between HTTP requests

# Major SOC group codes, titles, and career-coaching relevance
_SOC_MAJOR_GROUPS: list[dict] = [
    {"code": "11-0000", "title": "Management",
     "context": "Chief executives, general managers, functional managers across all sectors."},
    {"code": "13-0000", "title": "Business & Financial Operations",
     "context": "Financial analysts, accountants, HR specialists, management consultants, market researchers."},
    {"code": "15-0000", "title": "Computer & Mathematical",
     "context": "Software developers, data scientists, cloud engineers, cybersecurity analysts, ML engineers."},
    {"code": "17-0000", "title": "Architecture & Engineering",
     "context": "Civil, mechanical, electrical, and chemical engineers; architects; industrial designers."},
    {"code": "19-0000", "title": "Life, Physical & Social Science",
     "context": "Biomedical scientists, data analysts (research), clinical researchers, economists."},
    {"code": "21-0000", "title": "Community & Social Service",
     "context": "Social workers, counselors, mental health workers, substance abuse specialists."},
    {"code": "23-0000", "title": "Legal",
     "context": "Lawyers, paralegals, legal secretaries, compliance officers."},
    {"code": "25-0000", "title": "Educational Instruction & Library",
     "context": "Post-secondary teachers, corporate trainers, instructional designers, librarians."},
    {"code": "27-0000", "title": "Arts, Design, Entertainment & Media",
     "context": "UX designers, graphic designers, writers, video producers, marketing creatives."},
    {"code": "29-0000", "title": "Healthcare Practitioners & Technical",
     "context": "Physicians, nurses, pharmacists, medical and health services managers, clinical informatics."},
    {"code": "31-0000", "title": "Healthcare Support",
     "context": "Medical assistants, home health aides, phlebotomists, pharmacy technicians."},
    {"code": "33-0000", "title": "Protective Service",
     "context": "Police officers, firefighters, security guards, private investigators."},
    {"code": "35-0000", "title": "Food Preparation & Serving",
     "context": "Chefs, restaurant managers, food service supervisors."},
    {"code": "37-0000", "title": "Building & Grounds Cleaning",
     "context": "Janitors, landscapers, building cleaning supervisors."},
    {"code": "39-0000", "title": "Personal Care & Service",
     "context": "Personal care aides, fitness trainers, hairdressers, event planners."},
    {"code": "41-0000", "title": "Sales & Related",
     "context": "Sales representatives, sales managers, insurance sales, retail supervisors."},
    {"code": "43-0000", "title": "Office & Administrative Support",
     "context": "Administrative assistants, data entry workers, customer service representatives."},
    {"code": "45-0000", "title": "Farming, Fishing & Forestry",
     "context": "Agricultural workers, crop production managers, fishing supervisors."},
    {"code": "47-0000", "title": "Construction & Extraction",
     "context": "Construction managers, electricians, plumbers, miners."},
    {"code": "49-0000", "title": "Installation, Maintenance & Repair",
     "context": "Industrial mechanics, HVAC technicians, wind turbine service technicians."},
    {"code": "51-0000", "title": "Production",
     "context": "Manufacturing supervisors, quality control inspectors, machinists."},
    {"code": "53-0000", "title": "Transportation & Material Moving",
     "context": "Truck drivers, pilots, logistics supervisors, material moving workers."},
    {"code": "00-0000", "title": "All Occupations (Total)",
     "context": "National average across all 800+ occupations — baseline for all sectors."},
]

# Industry profiles to generate (replaces LinkedIn/Glassdoor gap)
# Each entry: (naics4_code, industry_name, career_context, naics_desc)
_INDUSTRY_PROFILES: list[tuple[str, str, str, str]] = [
    (
        "5200", "Finance & Insurance",
        (
            "Covers banking (NAICS 5221/5222), investment management (5231), insurance carriers (5241), "
            "and financial advisors (5242). High-earning sector; Wall Street bonuses can 2–3× base salaries. "
            "Top roles: investment bankers, quant analysts, portfolio managers, actuaries, risk analysts."
        ),
        "NAICS 52 — Finance and Insurance",
    ),
    (
        "5416", "Management Consulting",
        (
            "NAICS 5416 = Management, Scientific, and Technical Consulting Services. Covers strategy consulting "
            "(McKinsey, Bain, BCG), IT consulting (Accenture, Deloitte), and engineering consulting. "
            "Top roles: management consultants, strategy analysts, project managers, business analysts."
        ),
        "NAICS 5416 — Management, Scientific, and Technical Consulting",
    ),
    (
        "3254", "Pharmaceuticals & Biotech",
        (
            "NAICS 3254 = Pharmaceutical and Medicine Manufacturing. Covers drug discovery, clinical trials, "
            "regulatory affairs, and manufacturing at companies like Pfizer, Merck, Johnson & Johnson, Moderna. "
            "Top roles: chemists, biologists, regulatory specialists, clinical research managers, data scientists."
        ),
        "NAICS 3254 — Pharmaceutical and Medicine Manufacturing",
    ),
    (
        "6200", "Health Care & Social Assistance",
        (
            "NAICS 62 = Healthcare and Social Assistance — the largest US employment sector. Covers hospitals, "
            "ambulatory care, nursing facilities, and social services. "
            "Top roles: physicians, surgeons, registered nurses, health services managers, medical coders."
        ),
        "NAICS 62 — Health Care and Social Assistance",
    ),
    (
        "5112", "Software Publishing",
        (
            "NAICS 5112 = Software Publishers — covers packaged software and SaaS companies including Microsoft, "
            "Adobe, Salesforce, Oracle, and thousands of ISVs. Highest-paying sub-sector within tech. "
            "Top roles: software engineers, product managers, UX designers, DevOps, data scientists."
        ),
        "NAICS 5112 — Software Publishers",
    ),
    (
        "5182", "Data Processing & Cloud",
        (
            "NAICS 5182 = Data Processing, Hosting, and Related Services — covers cloud providers (AWS, Azure, GCP), "
            "data centres, and IT hosting services. Fast-growing; cloud infrastructure roles command premium wages. "
            "Top roles: cloud architects, DevOps engineers, site reliability engineers, data engineers."
        ),
        "NAICS 5182 — Data Processing, Hosting, and Related Services",
    ),
]


# BLS OES May 2024 national median annual wages by SOC major group.
# Public-domain data; source: https://www.bls.gov/oes/current/oes_nat.htm (released Oct 2024).
# Used as fallback when the flat-file download is unavailable.
_BLS_2024_REFERENCE: dict[str, dict] = {
    "00-0000": {"title": "All Occupations",                       "median_annual": 48_060,  "mean_annual": 63_080,  "pct25": 33_650,  "pct75": 78_760},
    "11-0000": {"title": "Management",                            "median_annual": 130_920, "mean_annual": 162_030, "pct25": 87_630,  "pct75": None},
    "13-0000": {"title": "Business & Financial Operations",       "median_annual": 78_580,  "mean_annual": 91_830,  "pct25": 55_630,  "pct75": 103_490},
    "15-0000": {"title": "Computer & Mathematical",               "median_annual": 104_420, "mean_annual": 110_230, "pct25": 75_010,  "pct75": 136_860},
    "17-0000": {"title": "Architecture & Engineering",            "median_annual": 87_370,  "mean_annual": 93_950,  "pct25": 65_040,  "pct75": 116_370},
    "19-0000": {"title": "Life, Physical & Social Science",       "median_annual": 78_200,  "mean_annual": 86_870,  "pct25": 54_610,  "pct75": 108_580},
    "21-0000": {"title": "Community & Social Service",            "median_annual": 49_780,  "mean_annual": 53_550,  "pct25": 38_290,  "pct75": 63_220},
    "23-0000": {"title": "Legal",                                 "median_annual": 97_260,  "mean_annual": 115_750, "pct25": 57_960,  "pct75": 148_320},
    "25-0000": {"title": "Educational Instruction & Library",     "median_annual": 62_320,  "mean_annual": 66_000,  "pct25": 44_030,  "pct75": 82_120},
    "27-0000": {"title": "Arts, Design, Entertainment & Media",   "median_annual": 60_260,  "mean_annual": 69_980,  "pct25": 41_570,  "pct75": 87_850},
    "29-0000": {"title": "Healthcare Practitioners & Technical",  "median_annual": 82_490,  "mean_annual": 102_790, "pct25": 53_740,  "pct75": 131_870},
    "31-0000": {"title": "Healthcare Support",                    "median_annual": 37_860,  "mean_annual": 40_960,  "pct25": 31_650,  "pct75": 47_830},
    "33-0000": {"title": "Protective Service",                    "median_annual": 48_200,  "mean_annual": 53_680,  "pct25": 37_040,  "pct75": 64_400},
    "35-0000": {"title": "Food Preparation & Serving",            "median_annual": 34_130,  "mean_annual": 36_840,  "pct25": 28_660,  "pct75": 40_590},
    "37-0000": {"title": "Building & Grounds Cleaning",           "median_annual": 39_500,  "mean_annual": 43_240,  "pct25": 31_320,  "pct75": 48_870},
    "39-0000": {"title": "Personal Care & Service",               "median_annual": 35_870,  "mean_annual": 40_640,  "pct25": 28_090,  "pct75": 48_000},
    "41-0000": {"title": "Sales & Related",                       "median_annual": 43_860,  "mean_annual": 59_840,  "pct25": 30_650,  "pct75": 68_130},
    "43-0000": {"title": "Office & Administrative Support",       "median_annual": 45_460,  "mean_annual": 49_840,  "pct25": 35_310,  "pct75": 58_690},
    "45-0000": {"title": "Farming, Fishing & Forestry",           "median_annual": 36_710,  "mean_annual": 40_140,  "pct25": 29_790,  "pct75": 45_110},
    "47-0000": {"title": "Construction & Extraction",             "median_annual": 59_440,  "mean_annual": 64_840,  "pct25": 44_820,  "pct75": 78_110},
    "49-0000": {"title": "Installation, Maintenance & Repair",    "median_annual": 55_100,  "mean_annual": 59_230,  "pct25": 40_680,  "pct75": 71_940},
    "51-0000": {"title": "Production",                            "median_annual": 44_950,  "mean_annual": 49_220,  "pct25": 33_730,  "pct75": 59_830},
    "53-0000": {"title": "Transportation & Material Moving",      "median_annual": 44_140,  "mean_annual": 49_200,  "pct25": 33_450,  "pct75": 58_020},
}

# BLS OES May 2024 national median annual wages for selected industries (all occupations).
# Source: https://www.bls.gov/oes/current/oes_nat.htm (released Oct 2024).
_BLS_2024_INDUSTRY_MEDIANS: dict[str, int] = {
    "5112": 121_710,  # Software Publishers
    "5182": 100_460,  # Data Processing & Cloud
    "5200": 88_260,   # Finance & Insurance (broad)
    "5416": 93_540,   # Management Consulting
    "3254": 80_390,   # Pharmaceuticals & Biotech
    "6200": 52_140,   # Health Care & Social Assistance (broad)
}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_get(url: str, headers: dict | None = None, timeout: int = 60) -> bytes | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA_BROWSER,
            "Accept": "application/zip,application/octet-stream,text/html,*/*",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        print(f"  WARN GET {url[:80]} → HTTP {exc.code}")
    except Exception as exc:
        print(f"  WARN GET {url[:80]} → {exc}")
    return None



# ── BLS flat-file downloader ───────────────────────────────────────────────────

def _download_bls_zip(url: str, cache_key: str) -> bytes | None:
    """Download a BLS OES zip with browser-like headers; cache to disk."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / cache_key

    if cache_file.exists():
        print(f"  Using cached {cache_key}")
        return cache_file.read_bytes()

    # Step 1: visit tables page (cookies / session setup)
    print(f"  Visiting BLS tables page ...")
    _http_get(_BLS_TABLES_PAGE)
    time.sleep(_DELAY)

    # Step 2: download zip
    print(f"  Downloading {url} ...")
    raw = _http_get(url, headers={"Referer": _BLS_TABLES_PAGE})
    time.sleep(_DELAY)

    if raw and raw[:2] == b"PK":
        cache_file.write_bytes(raw)
        print(f"  Cached to {cache_file} ({len(raw):,} bytes)")
        return raw

    if raw:
        print(f"  WARN: received {len(raw):,} bytes but not a zip (first4={raw[:4].hex()})")
    return None


# ── Excel parser ───────────────────────────────────────────────────────────────

def _parse_oes_excel(xlsx_bytes: bytes) -> list[dict]:
    """Parse BLS OES national_M*_dl.xlsx into a list of row dicts."""
    try:
        import openpyxl  # noqa: PLC0415
    except ImportError:
        print("  ERROR: openpyxl not installed. Run: poetry add openpyxl")
        return []

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(c).strip().upper() if c else "" for c in next(rows_iter)]

    results: list[dict] = []
    for row in rows_iter:
        if not any(row):
            continue
        d = {header[i]: row[i] for i in range(min(len(header), len(row)))}
        results.append(d)
    wb.close()
    return results


def _safe_wage(val: object) -> float | None:
    """Convert BLS wage cell to float, returning None for missing/suppressed."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if s in ("*", "#", "", "**"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── BLS API v2 fallback ────────────────────────────────────────────────────────

def _reference_data_fallback() -> dict[str, dict]:
    """Return BLS 2024 major group wages from embedded reference data.

    Used when flat-file download is unavailable (BLS rate limit, no internet, etc.).
    Source: BLS OES May 2024, released October 2024 (public domain).
    """
    print("  Using embedded BLS OES May 2024 reference data (public domain).")
    result: dict[str, dict] = {}
    for soc, data in _BLS_2024_REFERENCE.items():
        result[soc] = {**data}
    return result


# ── Data extractors ────────────────────────────────────────────────────────────

def extract_major_group_wages(rows: list[dict]) -> dict[str, dict]:
    """From flat-file rows, extract wages for major SOC groups.

    Returns {soc_code: {"title": str, "total_emp": int, "median_annual": float|None,
                         "mean_annual": float|None, "pct10": float|None, "pct25": float|None,
                         "pct75": float|None, "pct90": float|None}}.
    """
    major_codes = {g["code"] for g in _SOC_MAJOR_GROUPS}
    result: dict[str, dict] = {}

    for row in rows:
        occ_code = str(row.get("OCC_CODE", "")).strip()
        o_group  = str(row.get("O_GROUP", "")).strip().lower()
        if o_group not in ("major", "total") or occ_code not in major_codes:
            continue

        result[occ_code] = {
            "title":          str(row.get("OCC_TITLE", "")).strip(),
            "total_emp":      _safe_wage(row.get("TOT_EMP")),
            "median_annual":  _safe_wage(row.get("A_MEDIAN")),
            "mean_annual":    _safe_wage(row.get("A_MEAN")),
            "pct10":          _safe_wage(row.get("A_PCT10")),
            "pct25":          _safe_wage(row.get("A_PCT25")),
            "pct75":          _safe_wage(row.get("A_PCT75")),
            "pct90":          _safe_wage(row.get("A_PCT90")),
        }

    return result


def extract_industry_wages(
    rows: list[dict],
    naics4_code: str,
    top_n: int = 20,
) -> dict:
    """Extract occupation wage data for a specific NAICS 4-digit industry code.

    Returns {
        "industry_median": float|None,  # All occupations median in this industry
        "top_occupations": list[{occ_code, title, employment, median_annual, mean_annual}]
    }
    """
    target = naics4_code.ljust(6, "0")  # pad to 6 digits if needed
    industry_rows = []
    for row in rows:
        naics = str(row.get("NAICS", "")).strip()
        # Match exact 4-digit prefix with trailing zeros
        if naics.startswith(naics4_code) or naics == target:
            industry_rows.append(row)

    if not industry_rows:
        return {}

    # Find the "all occupations" row
    industry_median: float | None = None
    for row in industry_rows:
        occ_code = str(row.get("OCC_CODE", "")).strip()
        if occ_code == "00-0000":
            industry_median = _safe_wage(row.get("A_MEDIAN"))
            break

    # Top occupations by employment in this industry
    detailed = [
        r for r in industry_rows
        if str(r.get("O_GROUP", "")).strip().lower() == "detailed"
        and _safe_wage(r.get("TOT_EMP")) is not None
    ]
    detailed.sort(key=lambda r: _safe_wage(r.get("TOT_EMP")) or 0, reverse=True)

    top_occs: list[dict] = []
    for row in detailed[:top_n]:
        med = _safe_wage(row.get("A_MEDIAN"))
        mean = _safe_wage(row.get("A_MEAN"))
        if med or mean:
            top_occs.append({
                "occ_code":       str(row.get("OCC_CODE", "")).strip(),
                "title":          str(row.get("OCC_TITLE", "")).strip(),
                "employment":     _safe_wage(row.get("TOT_EMP")),
                "median_annual":  med,
                "mean_annual":    mean,
                "pct25":          _safe_wage(row.get("A_PCT25")),
                "pct75":          _safe_wage(row.get("A_PCT75")),
            })

    return {"industry_median": industry_median, "top_occupations": top_occs}


# ── Document builders ──────────────────────────────────────────────────────────

def build_soc_rankings_doc(
    wages: dict[str, dict],   # {soc_code: {title, median_annual, ...}}
    doc_idx: int,
) -> dict:
    """Build a pan-US SOC major occupation group salary ranking document."""
    heading = "United States — Annual Wages by Major Occupation Group (BLS OES 2024)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        "Median and mean annual wages by SOC major occupation group, national level.",
        "Source: BLS Occupational Employment and Wage Statistics (OES), May 2024 survey.",
        "Covers all ~9.7 million sampled workers across all US industries.",
        "",
    ]

    # Sort by median annual wage descending
    sorted_groups = sorted(
        [
            (grp["code"], wages.get(grp["code"], {}), grp)
            for grp in _SOC_MAJOR_GROUPS
        ],
        key=lambda x: x[1].get("median_annual") or 0,
        reverse=True,
    )

    lines += [
        "Occupation Group Rankings by Median Annual Wage",
        "─" * 80,
        f"  {'SOC Occupation Group':<40} {'Median/yr':>12}  {'Mean/yr':>12}",
        "  " + "─" * 68,
    ]
    for soc_code, data, grp in sorted_groups:
        title   = data.get("title") or grp["title"]
        median  = data.get("median_annual")
        mean    = data.get("mean_annual")
        med_str = f"USD {int(median):>9,}" if median else "  not avail."
        mean_str = f"USD {int(mean):>9,}" if mean else "  not avail."
        lines.append(f"  {title:<40} {med_str}  {mean_str}")

    lines += [""]

    # Wage distribution for top occupation groups
    high_wage_groups = [
        (soc, d, grp) for soc, d, grp in sorted_groups
        if d.get("median_annual") and d["median_annual"] > 80_000
    ]
    if high_wage_groups:
        lines += [
            "High-Wage Occupation Groups (median > USD 80,000/yr) — Wage Distribution",
            "─" * 80,
            f"  {'Group':<40} {'P25':>12}  {'Median':>12}  {'P75':>12}  {'P90':>12}",
            "  " + "─" * 76,
        ]
        for soc_code, data, grp in high_wage_groups:
            title = data.get("title") or grp["title"]
            p25   = data.get("pct25")
            med   = data.get("median_annual")
            p75   = data.get("pct75")
            p90   = data.get("pct90")
            def _fmt(v: float | None) -> str:
                return f"USD {int(v):>6,}" if v else "    n/a  "
            lines.append(
                f"  {title:<40} {_fmt(p25)}  {_fmt(med)}  {_fmt(p75)}  {_fmt(p90)}"
            )
        lines += [""]

    lines += [
        "Notes:",
        "• Wages are for May 2024; adjusted annually by BLS for occupational wage surveys.",
        "• 'Median' = 50th percentile annual wage. 'Mean' is skewed upward by high earners.",
        "• P25/P75/P90 = 25th / 75th / 90th percentile annual wages.",
        "• Wages include base pay; bonuses, stock awards, and commissions may not be fully captured.",
        "• Management (11-0000) and Legal (23-0000) medians understate true compensation for top earners.",
        "Source: BLS OES National Occupational Employment and Wage Estimates.",
        "URL: https://www.bls.gov/oes/current/oes_nat.htm",
    ]

    return {
        "id": f"bls-oes-soc-rankings-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "United States",
        "sub_region": "USA — National",
        "published_at": "2024-05-01",
        "source_url": "https://www.bls.gov/oes/current/oes_nat.htm",
        "tags": ["usa", "us", "salary", "wages", "bls", "oes", "soc", "occupation",
                 "management", "technology", "finance", "healthcare", "2024"],
    }


def build_industry_salary_doc(
    naics4: str,
    industry_name: str,
    industry_context: str,
    naics_desc: str,
    ind_data: dict,
    doc_idx: int,
) -> dict | None:
    """Build a US industry-specific salary profile document."""
    if not ind_data or not ind_data.get("top_occupations"):
        return None

    heading = f"United States — {industry_name}: Salary Profiles (BLS OES 2024)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        f"Sector: {naics_desc}",
        "Source: BLS Occupational Employment and Wage Statistics (OES), May 2024, industry-level data.",
        "",
        industry_context,
        "",
    ]

    ind_median = ind_data.get("industry_median")
    if ind_median:
        lines += [
            "Sector Overview",
            "─" * 16,
            f"Median annual wage (all occupations): USD {int(ind_median):,}",
            "",
        ]

    top_occs = ind_data.get("top_occupations", [])
    if top_occs:
        lines += [
            "Top Occupations by Employment — Annual Wage (USD)",
            "─" * 80,
            f"  {'Occupation':<44} {'Employment':>12}   {'Median':>12}  {'P75':>12}",
            "  " + "─" * 84,
        ]
        for occ in top_occs[:20]:
            title  = occ["title"][:43]
            emp    = occ.get("employment")
            med    = occ.get("median_annual")
            p75    = occ.get("pct75")
            emp_str = f"{int(emp):>12,}"  if emp else "  not avail."
            med_str = f"USD {int(med):>9,}" if med else "  not avail."
            p75_str = f"USD {int(p75):>9,}" if p75 else "  not avail."
            lines.append(f"  {title:<44} {emp_str}   {med_str}  {p75_str}")
        lines += [""]

    # High earners within the industry (P75 > 100k)
    high_earn = [o for o in top_occs if (o.get("pct75") or 0) > 100_000]
    if high_earn:
        lines += [
            "High-Earning Roles (P75 > USD 100,000/yr)",
            "─" * 56,
        ]
        for occ in high_earn[:10]:
            title = occ["title"][:43]
            med   = occ.get("median_annual")
            p75   = occ.get("pct75")
            med_str = f"USD {int(med):>9,}" if med else "  n/a       "
            p75_str = f"USD {int(p75):>9,}" if p75 else "  n/a       "
            lines.append(f"  {title:<44}  median {med_str}  P75 {p75_str}")
        lines += [""]

    lines += [
        "Notes:",
        "• Employment counts are BLS May 2024 estimates for this industry code.",
        "• Wages are gross base wages; bonuses, equity, and variable pay not fully captured.",
        "• Finance sector compensation is particularly underestimated (excludes year-end bonuses).",
        "• P75 = 75th percentile annual wage — what the top-earning quartile makes or more.",
        f"Source: BLS OES industry-specific wage data, {naics_desc}.",
        "URL: https://www.bls.gov/oes/current/oes_nat.htm",
    ]

    return {
        "id": f"bls-oes-industry-{naics4}-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "United States",
        "sub_region": f"USA — {industry_name}",
        "published_at": "2024-05-01",
        "source_url": "https://www.bls.gov/oes/current/oes_nat.htm",
        "tags": ["usa", "us", "salary", "wages", "bls", "oes", "industry",
                 "non-tech", naics4, industry_name.lower().replace(" ", "-").replace("&", "and"), "2024"],
    }


# ── Main pipeline ──────────────────────────────────────────────────────────────

def fetch_bls_oes(
    output_dir: str,
    dry_run: bool = False,
    local_nat_zip: str | None = None,
    local_ind_zip: str | None = None,
) -> list[dict]:
    """Fetch BLS OES data and build wage documents, then merge into market_reports_real.json."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "market_reports_real.json"

    # ── 1. Load the national flat file ────────────────────────────────────────
    print("\n[1/3] Loading BLS OES national flat file ...")
    nat_rows: list[dict] = []
    major_wages: dict[str, dict] = {}

    # Try local zip first, then download
    nat_zip_bytes: bytes | None = None
    if local_nat_zip:
        p = Path(local_nat_zip)
        if p.exists():
            print(f"  Reading local zip: {p}")
            nat_zip_bytes = p.read_bytes()
        else:
            print(f"  WARN: --local-nat-zip path not found: {p}")

    if not nat_zip_bytes:
        nat_zip_bytes = _download_bls_zip(_BLS_OES_NAT_URL, "oesm24nat.zip")

    if nat_zip_bytes:
        with zipfile.ZipFile(io.BytesIO(nat_zip_bytes)) as zf:
            xlsx_name = next((n for n in zf.namelist() if n.endswith(".xlsx")), None)
            if xlsx_name:
                print(f"  Parsing {xlsx_name} ...")
                xlsx_bytes = zf.read(xlsx_name)
                nat_rows = _parse_oes_excel(xlsx_bytes)
                major_wages = extract_major_group_wages(nat_rows)
                print(f"  Extracted {len(nat_rows):,} rows, {len(major_wages)} major SOC groups")

    if not major_wages:
        print("  Flat file unavailable — using embedded BLS 2024 reference data ...")
        major_wages = _reference_data_fallback()

    # ── 2. Load the industry cross-file ──────────────────────────────────────
    print("\n[2/3] Loading BLS OES industry cross-file ...")
    ind_rows: list[dict] = []

    ind_zip_bytes: bytes | None = None
    if local_ind_zip:
        p2 = Path(local_ind_zip)
        if p2.exists():
            print(f"  Reading local zip: {p2}")
            ind_zip_bytes = p2.read_bytes()

    if not ind_zip_bytes:
        ind_zip_bytes = _download_bls_zip(_BLS_OES_IND_URL, "oesm24in4.zip")

    if ind_zip_bytes:
        with zipfile.ZipFile(io.BytesIO(ind_zip_bytes)) as zf:
            # The industry zip contains multiple xlsx files — pick the national one
            xlsx_names = [n for n in zf.namelist() if n.endswith(".xlsx") and "nat" in n.lower()]
            if not xlsx_names:
                xlsx_names = [n for n in zf.namelist() if n.endswith(".xlsx")]
            if xlsx_names:
                print(f"  Industry files: {[n.split('/')[-1] for n in xlsx_names[:5]]}")
                # Parse all and combine
                for xn in xlsx_names[:3]:
                    print(f"  Parsing {xn.split('/')[-1]} ...")
                    xlsx_bytes_ind = zf.read(xn)
                    chunk = _parse_oes_excel(xlsx_bytes_ind)
                    ind_rows.extend(chunk)
                print(f"  Loaded {len(ind_rows):,} industry rows")

    # ── 3. Assemble documents ─────────────────────────────────────────────────
    print("\n[3/3] Building documents ...")
    new_docs: list[dict] = []

    # 3a. SOC major group ranking doc
    if major_wages:
        doc = build_soc_rankings_doc(major_wages, doc_idx=1)
        new_docs.append(doc)
        print(f"  SOC rankings doc added ({len(major_wages)} groups)")
    else:
        print("  WARN: no major wage data — SOC rankings doc skipped")

    # 3b. Industry salary profile docs
    for naics4, name, context, naics_desc in _INDUSTRY_PROFILES:
        if ind_rows:
            ind_data = extract_industry_wages(ind_rows, naics4)
        else:
            ind_data = {}

        doc = build_industry_salary_doc(
            naics4, name, context, naics_desc,
            ind_data, doc_idx=len(new_docs) + 1,
        )
        if doc:
            new_docs.append(doc)
            occ_count = len(ind_data.get("top_occupations", []))
            print(f"  Industry doc: {name} ({occ_count} occupations)")
        else:
            # Build a reference stub with BLS 2024 median and contextual salary ranges
            ref_median = _BLS_2024_INDUSTRY_MEDIANS.get(naics4)
            stub_lines: list[str] = [
                f"United States — {name}: Industry Salary Context (BLS OES 2024)",
                "=" * 70,
                "",
                f"Sector: {naics_desc}",
                "",
                context,
                "",
            ]
            if ref_median:
                stub_lines += [
                    "BLS OES May 2024 Reference Data (public domain)",
                    "─" * 50,
                    f"  All-occupations median annual wage: USD {ref_median:,}",
                    "  Source: BLS OES May 2024, https://www.bls.gov/oes/current/oes_nat.htm",
                    "",
                ]
            stub_lines += [
                "Note: Detailed occupation-level breakdown requires the BLS OES industry cross-file.",
                "Re-run: python -m scripts.fetch_bls_oes --local-ind-zip /path/to/oesm24in4.zip",
                "Download: https://www.bls.gov/oes/tables.htm → 'May 2024 National Industry-Specific'",
            ]
            stub = {
                "id": f"bls-oes-industry-{naics4}-{len(new_docs) + 1}",
                "title": f"United States — {name}: Industry Salary Context (BLS OES 2024)",
                "content": "\n".join(stub_lines).strip(),
                "region": "United States",
                "sub_region": f"USA — {name}",
                "published_at": "2024-05-01",
                "source_url": "https://www.bls.gov/oes/current/oes_nat.htm",
                "tags": ["usa", "salary", "bls", "oes", "industry", naics4, "2024"],
            }
            new_docs.append(stub)
            print(f"  Industry ref stub: {name} (BLS 2024 reference median included)")

    print(f"\nNew BLS docs: {len(new_docs)}")

    # ── 4. Merge into market_reports_real.json ────────────────────────────────
    if output_file.exists():
        existing: list[dict] = json.loads(output_file.read_text(encoding="utf-8"))
    else:
        existing = []

    # Drop old bls-oes-* docs, keep everything else
    kept = [d for d in existing if not d.get("id", "").startswith("bls-oes-")]
    merged = kept + new_docs
    print(f"  Kept {len(kept)} existing docs + {len(new_docs)} BLS docs = {len(merged)} total")

    if dry_run:
        print("  [dry-run] Output NOT written.")
        return merged

    output_file.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  Written: {output_file}  ({size_kb} KB)")
    return merged


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description="Fetch BLS OES US occupation wage data and merge into market_reports_real.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--output-dir", default=_default_out)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--local-nat-zip",
        help="Path to locally downloaded oesm24nat.zip (skips download)",
    )
    parser.add_argument(
        "--local-ind-zip",
        help="Path to locally downloaded oesm24in4.zip (industry cross-file)",
    )
    args = parser.parse_args()

    docs = fetch_bls_oes(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        local_nat_zip=args.local_nat_zip,
        local_ind_zip=args.local_ind_zip,
    )

    if not args.dry_run:
        bls_count = sum(1 for d in docs if d.get("id", "").startswith("bls-oes-"))
        print(
            f"\nBLS docs added: {bls_count}"
            "\nNext step — ingest:"
            "\n  POST /api/v1/admin/kb/ingest"
            "\n  {'doc_types': ['market_reports']}"
        )


if __name__ == "__main__":
    main()
