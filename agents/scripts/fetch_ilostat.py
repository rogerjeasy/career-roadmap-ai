"""fetch_ilostat.py — ILO ILOSTAT SDMX REST API client (shared backbone).

Imported by all regional market scripts.  Can also run standalone to fetch
wage data for any set of countries across all ILO-covered regions.

Sources
-------
ILO ILOSTAT SDMX REST API v2.1  (ilostat.ilo.org — free, no auth, CC BY 4.0)
  EAR_4MTH_SEX_ECO_NB_A
      Mean nominal monthly earnings by sex × economic activity (ISIC Rev.4)
      Covers ALL industries: agriculture, mining, manufacturing, construction,
      wholesale & retail, transport, hospitality, finance, real estate,
      professional services, public administration, education, healthcare, arts.

  EAR_4MTH_SEX_OCU_NB_A
      Mean nominal monthly earnings by sex × occupation (ISCO-08 major groups)
      Covers ALL occupations: managers, professionals (doctors, lawyers, engineers,
      teachers, accountants, nurses), technicians, clerks, service & sales workers,
      agricultural workers, craft & trades workers, machine operators, elementary.

  EMP_TEMP_SEX_OCU_NB_A
      Employment (thousands) by sex × occupation — workforce composition context.

Data Policy
-----------
CC BY 4.0 — free for commercial use with attribution.
Attribution: "Source: ILOSTAT, International Labour Organization, [year]"
URL: https://ilostat.ilo.org/data/

Usage
-----
  # Standalone — writes global_market_ilo.json:
  cd agents
  python -m scripts.fetch_ilostat --regions all --output-dir data/knowledge-base

  # Single region:
  python -m scripts.fetch_ilostat --regions africa --output-dir data/knowledge-base

  # As imported module:
  from agents.scripts.fetch_ilostat import fetch_ilo_data, build_ilo_documents
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# ── Constants ─────────────────────────────────────────────────────────────────

_UA = (
    "CareerRoadmapAI/1.0 (global-labour-market-kb; "
    "contact: rogerjeasybavibidila@gmail.com) python-urllib/3.12"
)
_ILO_BASE = "https://ilostat.ilo.org/resources/sdmx/v21/data"
_DELAY = 1.2          # seconds between API calls (be polite to ILO servers)
_TIMEOUT = 40         # seconds per request
_MAX_RETRIES = 3
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / ".ilo_cache"

# ILO indicator IDs
_IND_EARNINGS_BY_INDUSTRY   = "EAR_4MTH_SEX_ECO_NB_A"
_IND_EARNINGS_BY_OCCUPATION = "EAR_4MTH_SEX_OCU_NB_A"
_IND_EMPLOYMENT_BY_OCC      = "EMP_TEMP_SEX_OCU_NB_A"

# ISCO-08 major occupation groups — ALL job families, not just technology
_ISCO_GROUPS: dict[str, dict] = {
    "OCU_ISCO08_TOTAL": {
        "num": "ALL", "label": "All Occupations",
        "job_families": ["management", "engineering", "finance", "healthcare",
                         "education", "legal", "sales_marketing", "operations",
                         "construction_trades", "manufacturing", "agriculture",
                         "transport_logistics", "hospitality_tourism", "retail",
                         "it_technology", "arts_media", "public_sector",
                         "science_research", "social_services"],
    },
    "OCU_ISCO08_1": {
        "num": "1", "label": "Managers",
        "job_families": ["management", "operations", "public_sector"],
        "description": (
            "Chief executives, senior officials, general managers, hospitality managers, "
            "retail managers, agricultural managers, factory managers, school principals."
        ),
    },
    "OCU_ISCO08_2": {
        "num": "2", "label": "Professionals",
        "job_families": ["engineering", "healthcare", "education", "legal", "finance",
                         "it_technology", "science_research", "arts_media"],
        "description": (
            "Doctors, nurses (degree-level), lawyers, accountants, engineers (civil, "
            "mechanical, electrical, software), architects, teachers, university lecturers, "
            "scientists, economists, IT professionals, journalists, social workers (degree)."
        ),
    },
    "OCU_ISCO08_3": {
        "num": "3", "label": "Technicians and Associate Professionals",
        "job_families": ["engineering", "healthcare", "finance", "it_technology",
                         "arts_media", "construction_trades"],
        "description": (
            "Paramedics, lab technicians, dental assistants, engineering technicians, "
            "IT support technicians, police inspectors, financial officers, "
            "ship officers, aircraft pilots, photographers, sound technicians."
        ),
    },
    "OCU_ISCO08_4": {
        "num": "4", "label": "Clerical Support Workers",
        "job_families": ["operations", "finance", "public_sector"],
        "description": (
            "Office clerks, bookkeepers, receptionists, customer service representatives, "
            "data-entry operators, bank tellers, postal workers, legal secretaries."
        ),
    },
    "OCU_ISCO08_5": {
        "num": "5", "label": "Service and Sales Workers",
        "job_families": ["retail", "hospitality_tourism", "social_services", "public_sector"],
        "description": (
            "Retail salespeople, waiters, cooks, hairdressers, security guards, "
            "childcare workers, home-based care workers, shop assistants, tour guides."
        ),
    },
    "OCU_ISCO08_6": {
        "num": "6", "label": "Skilled Agricultural, Forestry and Fishery Workers",
        "job_families": ["agriculture"],
        "description": (
            "Subsistence and commercial farmers, market gardeners, livestock workers, "
            "forestry workers, aquaculture operators, fishing vessel operators."
        ),
    },
    "OCU_ISCO08_7": {
        "num": "7", "label": "Craft and Related Trades Workers",
        "job_families": ["construction_trades", "manufacturing"],
        "description": (
            "Construction workers, carpenters, plumbers, electricians, welders, mechanics, "
            "tailors, bakers, butchers, jewellers, pottery and glassware workers."
        ),
    },
    "OCU_ISCO08_8": {
        "num": "8", "label": "Plant and Machine Operators and Assemblers",
        "job_families": ["manufacturing", "transport_logistics"],
        "description": (
            "Factory machine operators, vehicle drivers (bus, truck, taxi), assemblers, "
            "mining machine operators, locomotive engineers, crane operators."
        ),
    },
    "OCU_ISCO08_9": {
        "num": "9", "label": "Elementary Occupations",
        "job_families": ["retail", "agriculture", "construction_trades", "hospitality_tourism"],
        "description": (
            "Cleaners, food preparation assistants, agricultural labourers, street vendors, "
            "delivery workers, rubbish collectors, building construction labourers."
        ),
    },
}

# ISIC Rev.4 economic activity sections — ALL industries covered
_ISIC_SECTIONS: dict[str, dict] = {
    "ECO_ISIC4_TOTAL": {
        "letter": "ALL", "label": "All Industries",
        "industries": ["all"],
        "job_families": ["management", "engineering", "finance", "healthcare", "education",
                         "legal", "operations", "construction_trades", "manufacturing",
                         "agriculture", "transport_logistics", "hospitality_tourism",
                         "retail", "it_technology", "public_sector"],
    },
    "ECO_ISIC4_A": {
        "letter": "A", "label": "Agriculture, Forestry and Fishing",
        "industries": ["agriculture", "forestry", "fishing"],
        "job_families": ["agriculture", "management", "operations"],
    },
    "ECO_ISIC4_B": {
        "letter": "B", "label": "Mining and Quarrying",
        "industries": ["mining", "oil_gas", "quarrying"],
        "job_families": ["engineering", "construction_trades", "manufacturing", "management"],
    },
    "ECO_ISIC4_C": {
        "letter": "C", "label": "Manufacturing",
        "industries": ["manufacturing", "food_processing", "textiles", "pharmaceuticals",
                        "automotive", "electronics", "chemicals"],
        "job_families": ["manufacturing", "engineering", "operations", "management"],
    },
    "ECO_ISIC4_D": {
        "letter": "D", "label": "Electricity, Gas, Steam and Air Conditioning",
        "industries": ["energy", "utilities"],
        "job_families": ["engineering", "operations", "management"],
    },
    "ECO_ISIC4_E": {
        "letter": "E", "label": "Water Supply, Sewerage and Waste Management",
        "industries": ["utilities", "environmental_services"],
        "job_families": ["engineering", "operations", "construction_trades"],
    },
    "ECO_ISIC4_F": {
        "letter": "F", "label": "Construction",
        "industries": ["construction", "real_estate_development", "infrastructure"],
        "job_families": ["construction_trades", "engineering", "management", "operations"],
    },
    "ECO_ISIC4_G": {
        "letter": "G", "label": "Wholesale and Retail Trade",
        "industries": ["retail", "wholesale", "e_commerce", "automotive_sales"],
        "job_families": ["retail", "sales_marketing", "management", "operations"],
    },
    "ECO_ISIC4_H": {
        "letter": "H", "label": "Transportation and Storage",
        "industries": ["transport", "logistics", "shipping", "aviation", "warehousing"],
        "job_families": ["transport_logistics", "operations", "engineering", "management"],
    },
    "ECO_ISIC4_I": {
        "letter": "I", "label": "Accommodation and Food Service",
        "industries": ["hospitality", "tourism", "restaurants", "hotels", "food_service"],
        "job_families": ["hospitality_tourism", "retail", "management", "operations"],
    },
    "ECO_ISIC4_J": {
        "letter": "J", "label": "Information and Communication (Technology)",
        "industries": ["technology", "telecommunications", "media", "software",
                       "cloud_computing", "cybersecurity"],
        "job_families": ["it_technology", "engineering", "arts_media", "management"],
    },
    "ECO_ISIC4_K": {
        "letter": "K", "label": "Financial and Insurance Activities",
        "industries": ["banking", "insurance", "investment", "fintech", "microfinance"],
        "job_families": ["finance", "management", "legal", "it_technology", "operations"],
    },
    "ECO_ISIC4_L": {
        "letter": "L", "label": "Real Estate Activities",
        "industries": ["real_estate", "property_management"],
        "job_families": ["management", "finance", "legal", "operations"],
    },
    "ECO_ISIC4_M": {
        "letter": "M", "label": "Professional, Scientific and Technical Activities",
        "industries": ["consulting", "legal_services", "accounting", "engineering_services",
                       "research", "advertising", "architecture"],
        "job_families": ["management", "legal", "finance", "engineering", "science_research",
                         "arts_media", "it_technology"],
    },
    "ECO_ISIC4_N": {
        "letter": "N", "label": "Administrative and Support Services",
        "industries": ["business_services", "staffing", "security", "travel_agencies",
                       "facility_management"],
        "job_families": ["operations", "management", "retail"],
    },
    "ECO_ISIC4_O": {
        "letter": "O", "label": "Public Administration and Defence",
        "industries": ["government", "defence", "public_safety", "civil_service"],
        "job_families": ["public_sector", "management", "legal", "operations"],
    },
    "ECO_ISIC4_P": {
        "letter": "P", "label": "Education",
        "industries": ["primary_education", "secondary_education", "higher_education",
                       "vocational_training", "private_tutoring"],
        "job_families": ["education", "management", "arts_media", "science_research"],
    },
    "ECO_ISIC4_Q": {
        "letter": "Q", "label": "Human Health and Social Work",
        "industries": ["healthcare", "hospitals", "clinics", "social_work",
                       "elderly_care", "mental_health", "pharmaceuticals"],
        "job_families": ["healthcare", "social_services", "management", "science_research"],
    },
    "ECO_ISIC4_R": {
        "letter": "R", "label": "Arts, Entertainment and Recreation",
        "industries": ["arts", "sports", "entertainment", "gaming", "culture",
                       "libraries", "museums"],
        "job_families": ["arts_media", "management", "operations"],
    },
    "ECO_ISIC4_S": {
        "letter": "S", "label": "Other Service Activities",
        "industries": ["personal_services", "religious_organisations",
                       "professional_associations", "repair_services"],
        "job_families": ["social_services", "retail", "operations"],
    },
}

# ── ISO-2 → ISO-3 country code mapping (ILO uses ISO3) ───────────────────────

_ISO2_TO_ISO3: dict[str, str] = {
    # Asia
    "SG": "SGP", "IN": "IND", "JP": "JPN", "CN": "CHN", "KR": "KOR",
    "PH": "PHL", "MY": "MYS", "TH": "THA", "ID": "IDN", "VN": "VNM",
    "BD": "BGD", "HK": "HKG", "PK": "PAK", "LK": "LKA", "MM": "MMR",
    "KH": "KHM", "NP": "NPL", "MN": "MNG", "TW": "TWN",
    # LATAM
    "BR": "BRA", "MX": "MEX", "AR": "ARG", "CO": "COL", "CL": "CHL",
    "PE": "PER", "VE": "VEN", "EC": "ECU", "BO": "BOL", "UY": "URY",
    "PA": "PAN", "GT": "GTM", "CR": "CRI", "HN": "HND", "SV": "SLV",
    "DO": "DOM", "JM": "JAM", "TT": "TTO", "CU": "CUB", "PR": "PRI",
    "PY": "PRY",
    # Africa
    "NG": "NGA", "ZA": "ZAF", "KE": "KEN", "ET": "ETH", "GH": "GHA",
    "TZ": "TZA", "UG": "UGA", "AO": "AGO", "ZM": "ZMB", "RW": "RWA",
    "SN": "SEN", "CI": "CIV", "CM": "CMR", "MZ": "MOZ", "ZW": "ZWE",
    "BF": "BFA", "ML": "MLI", "MW": "MWI", "MG": "MDG", "TD": "TCD",
    "SD": "SDN", "SS": "SSD", "ER": "ERI", "SO": "SOM", "MR": "MRT",
    "GN": "GIN", "SL": "SLE", "LR": "LBR", "BJ": "BEN", "TG": "TGO",
    "NE": "NER", "GA": "GAB", "CG": "COG", "CD": "COD", "BI": "BDI",
    "TN": "TUN",  # TN is Tunisia (Africa + MENA)
    # MENA
    "AE": "ARE", "SA": "SAU", "EG": "EGY", "MA": "MAR", "IL": "ISR",
    "TR": "TUR", "JO": "JOR", "QA": "QAT", "KW": "KWT", "BH": "BHR",
    "OM": "OMN", "IQ": "IRQ", "SY": "SYR", "YE": "YEM", "LB": "LBN",
    "IR": "IRN", "DZ": "DZA", "LY": "LBY",
    # Oceania
    "AU": "AUS", "NZ": "NZL", "FJ": "FJI", "PG": "PNG", "WS": "WSM",
    "TO": "TON", "VU": "VUT", "SB": "SLB", "FM": "FSM", "PW": "PLW",
}
_ISO3_TO_ISO2: dict[str, str] = {v: k for k, v in _ISO2_TO_ISO3.items()}

# ── HTTP client with cache + retry ────────────────────────────────────────────

def _cache_path(url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()[:16]
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def _http_get(url: str, *, use_cache: bool = True, timeout: int = _TIMEOUT) -> bytes | None:
    """GET with disk cache, retry, and polite rate limiting."""
    cp = _cache_path(url)
    if use_cache and cp.exists():
        return cp.read_bytes()

    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            if use_cache:
                cp.write_bytes(raw)
            return raw
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 400):
                return None  # no data for this query — not an error
            print(f"  WARN HTTP {exc.code} attempt {attempt+1}/{_MAX_RETRIES}: {url[:80]}")
            time.sleep(2 ** attempt)
        except Exception as exc:
            print(f"  WARN attempt {attempt+1}/{_MAX_RETRIES}: {exc}: {url[:80]}")
            time.sleep(2 ** attempt)
    return None


# ── SDMX-JSON parser ──────────────────────────────────────────────────────────

def _parse_sdmx_json(raw: bytes) -> dict[str, dict[str, float]]:
    """Parse ILO SDMX-JSON response → {classif1_id: {year: value}}.

    Picks the most recent non-null value per (classif1_id, country) series.
    Returns empty dict on parse failure.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

    structure = data.get("structure", {})
    datasets = data.get("dataSets", [])
    if not datasets:
        return {}

    series_dims = structure.get("dimensions", {}).get("series", [])
    obs_dims = structure.get("dimensions", {}).get("observation", [])

    # Build value lists per dimension
    dim_values: list[list[str]] = []
    for dim in series_dims:
        dim_values.append([v["id"] for v in dim.get("values", [])])

    # Time periods
    time_values: list[str] = []
    for dim in obs_dims:
        if dim.get("id") == "TIME_PERIOD":
            time_values = [v["id"] for v in dim.get("values", [])]
            break

    # Find position of CLASSIF1 in series dimensions
    classif_pos = next(
        (i for i, d in enumerate(series_dims) if d.get("id") == "CLASSIF1"), -1
    )
    if classif_pos == -1:
        return {}

    result: dict[str, dict[str, float]] = {}

    for series_key, series_data in datasets[0].get("series", {}).items():
        indices = series_key.split(":")
        if len(indices) <= classif_pos:
            continue
        try:
            classif_id = dim_values[classif_pos][int(indices[classif_pos])]
        except (IndexError, ValueError):
            continue

        for time_idx_str, obs in series_data.get("observations", {}).items():
            value = obs[0] if obs else None
            if value is None:
                continue
            try:
                year = time_values[int(time_idx_str)]
                result.setdefault(classif_id, {})[year] = float(value)
            except (IndexError, ValueError):
                continue

    return result


def _latest_value(year_map: dict[str, float]) -> tuple[str, float] | tuple[None, None]:
    """Return (latest_year_str, value) or (None, None) if map is empty."""
    if not year_map:
        return None, None
    year = max(year_map)
    return year, year_map[year]


# ── ILO data fetcher ──────────────────────────────────────────────────────────

def fetch_ilo_data(
    indicator: str,
    countries_iso2: list[str],
    *,
    start_year: int = 2018,
    use_cache: bool = True,
) -> dict[str, dict[str, dict[str, float]]]:
    """Fetch ILO indicator for a list of countries.

    Returns {country_iso2: {classif1_id: {year: value}}}.
    Countries with no data are omitted from the result.
    """
    iso3_codes = [_ISO2_TO_ISO3[c] for c in countries_iso2 if c in _ISO2_TO_ISO3]
    if not iso3_codes:
        return {}

    # Batch into groups of 15 to keep URL length manageable
    batch_size = 15
    batches = [iso3_codes[i:i + batch_size] for i in range(0, len(iso3_codes), batch_size)]

    combined: dict[str, dict[str, dict[str, float]]] = {}

    for batch in batches:
        country_key = "+".join(batch)
        url = (
            f"{_ILO_BASE}/{indicator}"
            f"/A.{country_key}.SEX_T..MN_A"
            f"?format=jsondata&startPeriod={start_year}"
        )
        # Employment indicator uses different measure
        if indicator == _IND_EMPLOYMENT_BY_OCC:
            url = (
                f"{_ILO_BASE}/{indicator}"
                f"/A.{country_key}.SEX_T.."
                f"?format=jsondata&startPeriod={start_year}"
            )

        print(f"  ILO {indicator}: {', '.join(batch)} ...")
        raw = _http_get(url, use_cache=use_cache)
        time.sleep(_DELAY)

        if not raw:
            continue

        parsed = _parse_sdmx_json(raw)
        if not parsed:
            continue

        # The parser returns {classif_id: {year: value}} — this is already per-batch
        # but we need to know which country each series belongs to.
        # Re-parse with country awareness.
        combined.update(_parse_sdmx_json_with_countries(raw))

    return combined


def _parse_sdmx_json_with_countries(
    raw: bytes,
) -> dict[str, dict[str, dict[str, float]]]:
    """Parse SDMX-JSON → {country_iso2: {classif1_id: {year: value}}}."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

    structure = data.get("structure", {})
    datasets = data.get("dataSets", [])
    if not datasets:
        return {}

    series_dims = structure.get("dimensions", {}).get("series", [])
    obs_dims = structure.get("dimensions", {}).get("observation", [])

    dim_values: list[list[str]] = [
        [v["id"] for v in d.get("values", [])] for d in series_dims
    ]
    time_values: list[str] = next(
        ([v["id"] for v in d.get("values", [])]
         for d in obs_dims if d.get("id") == "TIME_PERIOD"),
        [],
    )

    area_pos = next(
        (i for i, d in enumerate(series_dims) if d.get("id") == "REF_AREA"), -1
    )
    classif_pos = next(
        (i for i, d in enumerate(series_dims) if d.get("id") == "CLASSIF1"), -1
    )
    if area_pos == -1 or classif_pos == -1:
        return {}

    result: dict[str, dict[str, dict[str, float]]] = {}

    for series_key, series_data in datasets[0].get("series", {}).items():
        indices = series_key.split(":")
        try:
            iso3 = dim_values[area_pos][int(indices[area_pos])]
            classif_id = dim_values[classif_pos][int(indices[classif_pos])]
        except (IndexError, ValueError):
            continue

        iso2 = _ISO3_TO_ISO2.get(iso3)
        if not iso2:
            continue

        for time_idx_str, obs in series_data.get("observations", {}).items():
            value = obs[0] if obs else None
            if value is None:
                continue
            try:
                year = time_values[int(time_idx_str)]
                result.setdefault(iso2, {}).setdefault(classif_id, {})[year] = float(value)
            except (IndexError, ValueError):
                continue

    return result


# ── Document builders ─────────────────────────────────────────────────────────

def build_ilo_documents(
    country_iso2: str,
    country_meta: dict,
    occ_data: dict[str, dict[str, float]],
    ind_data: dict[str, dict[str, float]],
) -> list[dict]:
    """Build a list of KB document dicts from ILO wage data for one country.

    Returns up to 1 overview + 9 occupation docs + 18 industry docs per country.
    All documents cover ALL job families and industries — not just technology.

    Parameters
    ----------
    country_iso2   : ISO 2-letter country code.
    country_meta   : dict with keys: name, continent, region, sub_region,
                     market_tier, currency, context (prose paragraph).
    occ_data       : {classif1_id: {year: value}} — earnings by occupation.
    ind_data       : {classif1_id: {year: value}} — earnings by industry.
    """
    docs: list[dict] = []
    name = country_meta["name"]
    continent = country_meta["continent"]
    region = country_meta.get("region", "")
    sub_region = country_meta.get("sub_region", "")
    market_tier = country_meta["market_tier"]
    currency = country_meta.get("currency", "local currency")
    context_paragraph = country_meta.get("context", "")

    # ── 1. Country overview document ──────────────────────────────────────────
    total_occ = occ_data.get("OCU_ISCO08_TOTAL", {})
    total_ind = ind_data.get("ECO_ISIC4_TOTAL", {})

    if total_occ or total_ind:
        occ_year, occ_val = _latest_value(total_occ)
        ind_year, ind_val = _latest_value(total_ind)
        ref_val = occ_val or ind_val
        ref_year = occ_year or ind_year

        if ref_val and ref_year:
            # Build ranked industry comparison
            ind_ranking = _rank_sectors(ind_data, exclude={"ECO_ISIC4_TOTAL"})
            occ_ranking = _rank_groups(occ_data, exclude={"OCU_ISCO08_TOTAL"})

            content_lines = [
                f"{name} Labour Market — All Occupations and Industries ({ref_year})",
                "=" * 60,
                "",
                context_paragraph or f"{name} is a {market_tier} labour market in {region}.",
                "",
                "ILO ILOSTAT Wage Data Summary",
                "─" * 30,
                f"Mean nominal monthly earnings (all occupations): "
                f"{ref_val:,.0f} {currency} ({ref_year})",
                "",
            ]

            if occ_ranking:
                content_lines += [
                    "Earnings by Occupation Group (mean monthly, local currency):",
                ]
                for classif_id, (year, val) in occ_ranking[:6]:
                    grp = _ISCO_GROUPS.get(classif_id, {})
                    lbl = grp.get("label", classif_id)
                    content_lines.append(f"  {lbl}: {val:,.0f} {currency} ({year})")

            if ind_ranking:
                content_lines += [
                    "",
                    "Earnings by Industry Sector (mean monthly, local currency):",
                ]
                for classif_id, (year, val) in ind_ranking[:8]:
                    sec = _ISIC_SECTIONS.get(classif_id, {})
                    lbl = sec.get("label", classif_id)
                    content_lines.append(f"  {lbl}: {val:,.0f} {currency} ({year})")

            content_lines += [
                "",
                "Note: Wages quoted in nominal local currency. Data covers formal-sector "
                "employees. Agriculture, construction, and the informal sector may be "
                "under-represented in national earnings surveys.",
                "Source: ILOSTAT, International Labour Organization.",
            ]

            all_industries = list({
                ind
                for sec_data in _ISIC_SECTIONS.values()
                for ind in sec_data.get("industries", [])
                if ind != "all"
            })
            all_job_families = list({
                jf
                for grp_data in _ISCO_GROUPS.values()
                for jf in grp_data.get("job_families", [])
            })

            docs.append({
                "id": f"ilo-{country_iso2.lower()}-overview-{ref_year}",
                "title": f"{name} Labour Market Wages Overview {ref_year} — All Occupations and Industries",
                "content": "\n".join(content_lines),
                "continent": continent,
                "country": country_iso2,
                "region": region,
                "sub_region": sub_region,
                "market_tier": market_tier,
                "industries": all_industries[:20],
                "job_families": all_job_families[:15],
                "published_at": f"{ref_year}-01-01",
                "source_url": "https://ilostat.ilo.org/data/",
                "tags": [country_iso2.lower(), name.lower().replace(" ", "-"),
                         "wages", "labour-market", "ilo", ref_year, "all-industries"],
            })

    # ── 2. Per-occupation-group documents ─────────────────────────────────────
    total_val_occ = _latest_value(total_occ)[1]

    for classif_id, year_map in occ_data.items():
        if classif_id == "OCU_ISCO08_TOTAL":
            continue
        grp = _ISCO_GROUPS.get(classif_id)
        if not grp:
            continue
        year, val = _latest_value(year_map)
        if not year or not val:
            continue

        pct_of_avg = ""
        if total_val_occ and total_val_occ > 0:
            ratio = val / total_val_occ
            pct_of_avg = (
                f"This is {ratio:.0%} of the national average wage "
                f"({total_val_occ:,.0f} {currency}/month)."
            )

        content = (
            f"{name} — {grp['label']} (ISCO-08 Group {grp['num']}) "
            f"Mean Monthly Earnings {year}\n"
            f"{'=' * 60}\n\n"
            f"Mean nominal monthly earnings: {val:,.0f} {currency} ({year}). "
            f"{pct_of_avg}\n\n"
            f"Roles in this occupation group:\n{grp.get('description', '')}\n\n"
            f"This ISCO-08 major group covers workers in {name} across public and private "
            f"sector employers in all industries. Wages reflect formal-sector employees "
            f"only; informal employment may have significantly different earnings.\n\n"
            f"Source: ILOSTAT, International Labour Organization, {year}."
        )

        docs.append({
            "id": f"ilo-{country_iso2.lower()}-occ-{grp['num']}-{year}",
            "title": (
                f"{name} — {grp['label']} (ISCO-08 Group {grp['num']}) "
                f"Mean Monthly Earnings {year}"
            ),
            "content": content,
            "continent": continent,
            "country": country_iso2,
            "region": region,
            "sub_region": sub_region,
            "market_tier": market_tier,
            "industries": ["all"],
            "job_families": grp.get("job_families", []),
            "published_at": f"{year}-01-01",
            "source_url": "https://ilostat.ilo.org/data/",
            "tags": [country_iso2.lower(), "isco", f"isco-{grp['num']}", "wages",
                     "occupation", grp["label"].lower().replace(" ", "-"), year],
        })

    # ── 3. Per-industry-sector documents ──────────────────────────────────────
    total_val_ind = _latest_value(total_ind)[1]

    for classif_id, year_map in ind_data.items():
        if classif_id == "ECO_ISIC4_TOTAL":
            continue
        sec = _ISIC_SECTIONS.get(classif_id)
        if not sec:
            continue
        year, val = _latest_value(year_map)
        if not year or not val:
            continue

        pct_of_avg = ""
        if total_val_ind and total_val_ind > 0:
            ratio = val / total_val_ind
            pct_of_avg = (
                f"This is {ratio:.0%} of the national average wage "
                f"({total_val_ind:,.0f} {currency}/month)."
            )

        content = (
            f"{name} — {sec['label']} (ISIC Rev.4 Section {sec['letter']}) "
            f"Mean Monthly Earnings {year}\n"
            f"{'=' * 60}\n\n"
            f"Mean nominal monthly earnings in this sector: {val:,.0f} {currency} ({year}). "
            f"{pct_of_avg}\n\n"
            f"Industries covered: {', '.join(sec['industries'])}.\n\n"
            f"Key job families in this sector: "
            f"{', '.join(sec.get('job_families', []))}. "
            f"These span roles from entry-level to senior management across "
            f"government, private sector, and mixed ownership employers in {name}.\n\n"
            f"Source: ILOSTAT, International Labour Organization, {year}."
        )

        docs.append({
            "id": f"ilo-{country_iso2.lower()}-ind-{sec['letter'].lower()}-{year}",
            "title": (
                f"{name} — {sec['label']} (ISIC {sec['letter']}) "
                f"Mean Monthly Earnings {year}"
            ),
            "content": content,
            "continent": continent,
            "country": country_iso2,
            "region": region,
            "sub_region": sub_region,
            "market_tier": market_tier,
            "industries": sec.get("industries", []),
            "job_families": sec.get("job_families", []),
            "published_at": f"{year}-01-01",
            "source_url": "https://ilostat.ilo.org/data/",
            "tags": [country_iso2.lower(), "isic", f"isic-{sec['letter'].lower()}",
                     "wages", "industry", sec["label"].lower()[:40], year],
        })

    return docs


def _rank_sectors(
    ind_data: dict[str, dict[str, float]],
    *,
    exclude: set[str] | None = None,
) -> list[tuple[str, tuple[str | None, float | None]]]:
    """Return sectors sorted descending by latest value, excluding keys in `exclude`."""
    exclude = exclude or set()
    ranked = []
    for classif_id, year_map in ind_data.items():
        if classif_id in exclude:
            continue
        year, val = _latest_value(year_map)
        if val is not None:
            ranked.append((classif_id, (year, val)))
    ranked.sort(key=lambda x: x[1][1] or 0, reverse=True)
    return ranked


def _rank_groups(
    occ_data: dict[str, dict[str, float]],
    *,
    exclude: set[str] | None = None,
) -> list[tuple[str, tuple[str | None, float | None]]]:
    """Return occupation groups sorted descending by latest value."""
    exclude = exclude or set()
    ranked = []
    for classif_id, year_map in occ_data.items():
        if classif_id in exclude:
            continue
        year, val = _latest_value(year_map)
        if val is not None:
            ranked.append((classif_id, (year, val)))
    ranked.sort(key=lambda x: x[1][1] or 0, reverse=True)
    return ranked


# ── Country metadata registry ─────────────────────────────────────────────────
# Each entry: name, continent, region, sub_region, market_tier, currency, context
# context: 2-4 sentence prose paragraph for the overview document.

COUNTRY_META: dict[str, dict] = {
    # ── ASIA ──────────────────────────────────────────────────────────────────
    "SG": {
        "name": "Singapore", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Greater Singapore", "market_tier": "mature",
        "currency": "SGD",
        "context": (
            "Singapore is one of Asia's highest-wage economies with a highly educated "
            "multilingual workforce. Major sectors include financial services, logistics, "
            "manufacturing (semiconductors, pharmaceuticals), professional services, and "
            "a growing technology cluster. The government's SkillsFuture programme "
            "funds continuous reskilling across all industries. Median household income "
            "places Singapore among the top five globally. Strong demand exists for "
            "finance, engineering, healthcare, legal, and technology professionals."
        ),
    },
    "IN": {
        "name": "India", "continent": "Asia", "region": "South Asia",
        "sub_region": "Indian Subcontinent", "market_tier": "emerging",
        "currency": "INR",
        "context": (
            "India has the world's largest working-age population and the third-largest "
            "economy by PPP. Key sectors include IT services and software (Bengaluru, "
            "Hyderabad, Pune), banking and financial services (Mumbai), manufacturing "
            "(automotive, textiles, pharmaceuticals), agriculture (employs ~45% of "
            "workforce), and a rapidly expanding healthcare and education sector. "
            "Salary ranges vary enormously between metro cities (Delhi, Mumbai, Bengaluru) "
            "and Tier-2/Tier-3 cities. Government jobs (IAS, PSU) remain highly sought "
            "after for stability."
        ),
    },
    "JP": {
        "name": "Japan", "continent": "Asia", "region": "East Asia",
        "sub_region": "Northeast Asia", "market_tier": "mature",
        "currency": "JPY",
        "context": (
            "Japan maintains one of the world's highest living standards with strong wages "
            "in manufacturing, finance, and professional services. The labour market is "
            "characterised by lifetime employment traditions (slowly changing), seniority-"
            "based pay, and significant gender wage gaps. Key sectors: automotive and "
            "electronics manufacturing, financial services, healthcare (aging population "
            "driving demand), retail, construction, and a growing tech/startup ecosystem "
            "in Tokyo. Bilingual (English-Japanese) professionals command significant "
            "premiums across sectors."
        ),
    },
    "CN": {
        "name": "China", "continent": "Asia", "region": "East Asia",
        "sub_region": "Northeast Asia", "market_tier": "emerging",
        "currency": "CNY",
        "context": (
            "China's labour market spans vast regional wage differentials — coastal "
            "cities (Beijing, Shanghai, Shenzhen, Guangzhou) have wages 2-4x higher than "
            "inland provinces. Key sectors: manufacturing (world's factory), technology "
            "(Alibaba, Tencent, Huawei ecosystem), finance, construction, retail, and "
            "healthcare. The middle class drives growth in education, healthcare, and "
            "consumer services. Formal sector wages have grown rapidly; skilled workers "
            "in technology, finance, and management command premium salaries in tier-1 cities."
        ),
    },
    "KR": {
        "name": "South Korea", "continent": "Asia", "region": "East Asia",
        "sub_region": "Northeast Asia", "market_tier": "mature",
        "currency": "KRW",
        "context": (
            "South Korea has a highly educated workforce concentrated in large chaebols "
            "(Samsung, Hyundai, LG, SK, Lotte) and a growing SME/startup ecosystem. "
            "Major sectors: semiconductor and electronics manufacturing, automotive, "
            "shipbuilding, steel, finance, e-commerce, gaming, and entertainment (K-pop/K-drama). "
            "The public sector and education are highly competitive entry paths. "
            "Wage growth is concentrated among large-firm employees; small firm wages "
            "and irregular employment remain a structural challenge."
        ),
    },
    "PH": {
        "name": "Philippines", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Maritime Southeast Asia", "market_tier": "emerging",
        "currency": "PHP",
        "context": (
            "The Philippines has a large English-proficient workforce powering a globally "
            "dominant BPO/outsourcing sector (call centres, shared services, IT support). "
            "Remittances from Overseas Filipino Workers (OFWs — ~10% of GDP) in healthcare, "
            "maritime, domestic work, and construction abroad are a major income source. "
            "Domestic sectors include retail, agriculture, manufacturing, and a growing "
            "fintech and e-commerce ecosystem. Healthcare, engineering, and education "
            "are key professional pathways."
        ),
    },
    "MY": {
        "name": "Malaysia", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Mainland Southeast Asia", "market_tier": "emerging",
        "currency": "MYR",
        "context": (
            "Malaysia is an upper-middle-income economy transitioning toward high-income "
            "status. Key sectors: manufacturing (electronics, chemicals, rubber), oil and "
            "gas (Petronas), financial services (Islamic banking hub), tourism, and a "
            "growing technology cluster in the Klang Valley (Cyberjaya). Kuala Lumpur "
            "offers wages significantly above rural Sabah/Sarawak. English is widely "
            "used in business and professional services."
        ),
    },
    "TH": {
        "name": "Thailand", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Mainland Southeast Asia", "market_tier": "emerging",
        "currency": "THB",
        "context": (
            "Thailand's economy is driven by tourism (pre-COVID ~20% of GDP), "
            "manufacturing (automotive assembly, hard disk drives, food processing), "
            "agriculture (rice, rubber, tapioca), and financial services in Bangkok. "
            "The Eastern Economic Corridor (EEC) is attracting advanced manufacturing "
            "and technology investment. Bangkok wages are substantially higher than "
            "rural provinces. Healthcare, hospitality, manufacturing, and professional "
            "services are the primary formal employment sectors."
        ),
    },
    "ID": {
        "name": "Indonesia", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Maritime Southeast Asia", "market_tier": "emerging",
        "currency": "IDR",
        "context": (
            "Indonesia is Southeast Asia's largest economy with significant regional "
            "wage variation across its 17,000+ islands. Jakarta's urban economy "
            "dominates in financial services, technology, and professional services. "
            "Key sectors: commodities (palm oil, coal, nickel), manufacturing, retail, "
            "construction, agriculture, and a rapidly growing digital economy. "
            "Minimum wages are set provincially; Jakarta is the highest. Healthcare, "
            "education, and civil service are major formal employers."
        ),
    },
    "VN": {
        "name": "Vietnam", "continent": "Asia", "region": "Southeast Asia",
        "sub_region": "Mainland Southeast Asia", "market_tier": "emerging",
        "currency": "VND",
        "context": (
            "Vietnam is among Asia's fastest-growing economies, driven by export-oriented "
            "manufacturing (electronics, textiles, footwear — Samsung, Intel, Nike). "
            "Ho Chi Minh City and Hanoi lead in financial services, technology, and "
            "professional services. Foreign direct investment has driven wage growth in "
            "manufacturing zones. The agricultural sector (rice, coffee, seafood) employs "
            "a large share of the population but with lower formal wages. "
            "IT outsourcing and fintech are fast-growing knowledge economy sectors."
        ),
    },
    "BD": {
        "name": "Bangladesh", "continent": "Asia", "region": "South Asia",
        "sub_region": "Indian Subcontinent", "market_tier": "emerging",
        "currency": "BDT",
        "context": (
            "Bangladesh's formal labour market is dominated by garment and textile "
            "manufacturing (world's second-largest exporter), which employs ~4 million "
            "workers — majority women. Remittances from migrant workers in the Middle East "
            "and Southeast Asia are a major income source (~7% of GDP). The pharmaceutical, "
            "healthcare, education, and NGO sectors are growing. Dhaka wages significantly "
            "exceed rural areas. IT and outsourcing are emerging sectors."
        ),
    },
    "HK": {
        "name": "Hong Kong", "continent": "Asia", "region": "East Asia",
        "sub_region": "Northeast Asia", "market_tier": "mature",
        "currency": "HKD",
        "context": (
            "Hong Kong is a major global financial centre with one of the world's "
            "highest concentrations of banks, asset managers, and wealth management firms. "
            "Key sectors: financial services, trade and logistics, professional services "
            "(legal, accounting, consulting), retail, hospitality, and a growing technology "
            "ecosystem. High cost of living means salaries are among Asia's highest. "
            "English and Cantonese proficiency are expected in most professional roles."
        ),
    },
    "PK": {
        "name": "Pakistan", "continent": "Asia", "region": "South Asia",
        "sub_region": "Indian Subcontinent", "market_tier": "emerging",
        "currency": "PKR",
        "context": (
            "Pakistan has a large and youthful workforce (median age ~22). Key formal "
            "sectors: textiles and garments, agriculture (wheat, cotton, rice), financial "
            "services, telecommunications, retail, and construction. IT freelancing and "
            "digital services have grown rapidly, with Pakistani developers among the top "
            "suppliers on global platforms. Karachi dominates in manufacturing and finance; "
            "Lahore in manufacturing and services; Islamabad in government and NGOs."
        ),
    },
    "LK": {
        "name": "Sri Lanka", "continent": "Asia", "region": "South Asia",
        "sub_region": "Indian Subcontinent", "market_tier": "emerging",
        "currency": "LKR",
        "context": (
            "Sri Lanka is a lower-middle-income economy with major formal sectors in "
            "garment manufacturing, tourism (recovering post-crisis), tea and rubber "
            "agriculture, financial services, and IT/BPO. Remittances from the large "
            "diaspora in the Gulf, Middle East, and Western countries are a key income "
            "source. Colombo has the highest wages; rural areas depend heavily on "
            "agriculture. Healthcare, education, and civil service are major employers."
        ),
    },
    # ── LATAM ─────────────────────────────────────────────────────────────────
    "BR": {
        "name": "Brazil", "continent": "Americas", "region": "South America",
        "sub_region": "Southern Cone / Brazil", "market_tier": "emerging",
        "currency": "BRL",
        "context": (
            "Brazil is Latin America's largest economy with significant wage inequality "
            "between regions (São Paulo/Rio de Janeiro vs. Nordeste) and between formal "
            "and informal workers. Key sectors: agriculture (soybeans, beef — major global "
            "exporter), manufacturing (aerospace — Embraer, automotive), financial services "
            "(major banks in São Paulo), retail, healthcare, education, oil and gas "
            "(Petrobras), and a booming fintech/technology sector (Nubank, iFood). "
            "CLT formal employment includes 13th salary and statutory benefits."
        ),
    },
    "MX": {
        "name": "Mexico", "continent": "Americas", "region": "Central America & Caribbean",
        "sub_region": "North America", "market_tier": "emerging",
        "currency": "MXN",
        "context": (
            "Mexico is deeply integrated with the US economy through USMCA (NAFTA "
            "successor), powering manufacturing exports (automotive, aerospace, electronics). "
            "The maquiladora sector in northern border states (Baja California, Chihuahua, "
            "Nuevo León) offers wages above the national average. Key sectors: "
            "manufacturing, agriculture (avocado, tomatoes), tourism (Riviera Maya, "
            "Cancún), financial services, retail, and oil and gas (PEMEX). "
            "Mexico City has the most diversified professional job market."
        ),
    },
    "AR": {
        "name": "Argentina", "continent": "Americas", "region": "South America",
        "sub_region": "Southern Cone", "market_tier": "emerging",
        "currency": "ARS",
        "context": (
            "Argentina has a highly educated workforce but has experienced significant "
            "macroeconomic volatility, affecting real wage values. Key sectors: agriculture "
            "(soybean, corn, beef exports), manufacturing, financial services, "
            "professional services, education, healthcare, and a strong IT/technology "
            "sector (Buenos Aires is a major tech hub with globally competitive salaries). "
            "Wages are frequently renegotiated due to inflation; USD-indexed contracts "
            "are common in technology and professional services."
        ),
    },
    "CO": {
        "name": "Colombia", "continent": "Americas", "region": "South America",
        "sub_region": "Andean Region", "market_tier": "emerging",
        "currency": "COP",
        "context": (
            "Colombia's labour market is centred on Bogotá (finance, technology, "
            "professional services), Medellín (manufacturing, innovation hub), and "
            "Cali (agribusiness, healthcare). Key sectors: agriculture (coffee, cut "
            "flowers, bananas), oil and gas, manufacturing, retail, financial services, "
            "and a growing technology and BPO sector. Tourism and healthcare are "
            "expanding. Bogotá's minimum wage is above the national level."
        ),
    },
    "CL": {
        "name": "Chile", "continent": "Americas", "region": "South America",
        "sub_region": "Southern Cone", "market_tier": "emerging",
        "currency": "CLP",
        "context": (
            "Chile is Latin America's most stable economy with the highest per-capita "
            "income in the region. Key sectors: mining (copper — world's largest exporter), "
            "agriculture and food (wine, salmon, fruit), financial services, retail "
            "(Falabella, CENCOSUD), technology, and professional services. Santiago "
            "dominates with high professional wages; mining regions pay significant "
            "premiums for technical and engineering roles."
        ),
    },
    "PE": {
        "name": "Peru", "continent": "Americas", "region": "South America",
        "sub_region": "Andean Region", "market_tier": "emerging",
        "currency": "PEN",
        "context": (
            "Peru's formal economy is driven by mining (gold, copper, silver — top-5 "
            "global producer), agriculture (asparagus, blueberries, quinoa exports), "
            "financial services, retail, and manufacturing. Lima concentrates most formal "
            "employment; mining regions offer premium wages for engineers and technicians. "
            "The informal sector is large (~70% of employment). Healthcare, education, "
            "and public administration are major formal employers."
        ),
    },
    "CO": {
        "name": "Colombia", "continent": "Americas", "region": "South America",
        "sub_region": "Andean Region", "market_tier": "emerging",
        "currency": "COP",
        "context": (
            "Colombia's economy is centred on Bogotá (finance, technology), Medellín "
            "(manufacturing, innovation), and Cali (agribusiness, healthcare). "
            "Key sectors: coffee and agricultural exports, oil and gas, manufacturing, "
            "retail, financial services, and a growing technology/BPO sector."
        ),
    },
    "EC": {
        "name": "Ecuador", "continent": "Americas", "region": "South America",
        "sub_region": "Andean Region", "market_tier": "emerging",
        "currency": "USD",
        "context": (
            "Ecuador uses the US dollar, giving wage stability. Key sectors: oil exports, "
            "agriculture (bananas, roses, shrimp), manufacturing, retail, healthcare, "
            "and education. Quito and Guayaquil have the highest formal wages. "
            "The public sector is a major employer."
        ),
    },
    "BO": {
        "name": "Bolivia", "continent": "Americas", "region": "South America",
        "sub_region": "Andean Region", "market_tier": "emerging",
        "currency": "BOB",
        "context": (
            "Bolivia is among South America's lowest-income countries but has seen "
            "strong growth from natural gas exports, lithium mining, and agriculture. "
            "Key sectors: natural resources (gas, minerals), agriculture, retail, "
            "construction, and public administration. La Paz and Santa Cruz are the "
            "main formal employment centres."
        ),
    },
    "UY": {
        "name": "Uruguay", "continent": "Americas", "region": "South America",
        "sub_region": "Southern Cone", "market_tier": "emerging",
        "currency": "UYU",
        "context": (
            "Uruguay has Latin America's strongest social safety net, lowest inequality, "
            "and high human development. Key sectors: agriculture and food exports "
            "(beef, dairy, soy), financial services (regional offshore banking hub), "
            "tourism, IT/software exports (significant per capita), and public services. "
            "Montevideo wages are significantly above rural areas."
        ),
    },
    "PA": {
        "name": "Panama", "continent": "Americas", "region": "Central America & Caribbean",
        "sub_region": "Central America", "market_tier": "emerging",
        "currency": "USD",
        "context": (
            "Panama's economy is centred on the Panama Canal, financial services "
            "(Colón Free Zone, regional banking hub), logistics, retail, tourism, "
            "and construction. Panama City has wages well above the regional average. "
            "The USD currency and low inflation make it attractive for regional HQs."
        ),
    },
    "CR": {
        "name": "Costa Rica", "continent": "Americas", "region": "Central America & Caribbean",
        "sub_region": "Central America", "market_tier": "emerging",
        "currency": "CRC",
        "context": (
            "Costa Rica has the region's most educated workforce and a strong medical "
            "device manufacturing sector (Boston Scientific, Medtronic). Key sectors: "
            "high-tech manufacturing, tourism (ecotourism), agriculture (pineapples, "
            "bananas, coffee), financial services, and a growing technology/shared "
            "services sector in San José."
        ),
    },
    "GT": {
        "name": "Guatemala", "continent": "Americas", "region": "Central America & Caribbean",
        "sub_region": "Central America", "market_tier": "frontier",
        "currency": "GTQ",
        "context": (
            "Guatemala is Central America's largest economy driven by agriculture "
            "(coffee, bananas, sugarcane, palm oil), manufacturing (textiles/maquilas), "
            "remittances (~15% of GDP from the US), retail, and financial services. "
            "Guatemala City concentrates formal employment. The informal sector is large."
        ),
    },
    "HN": {
        "name": "Honduras", "continent": "Americas", "region": "Central America & Caribbean",
        "sub_region": "Central America", "market_tier": "frontier",
        "currency": "HNL",
        "context": (
            "Honduras relies heavily on remittances (~25% of GDP), maquila/textile "
            "manufacturing for export, agriculture (coffee, bananas, shrimp), and retail. "
            "San Pedro Sula is the industrial capital. The informal sector employs "
            "the majority of the workforce."
        ),
    },
    "DO": {
        "name": "Dominican Republic", "continent": "Americas",
        "region": "Central America & Caribbean", "sub_region": "Caribbean",
        "market_tier": "emerging", "currency": "DOP",
        "context": (
            "The Dominican Republic is the Caribbean's largest economy, led by tourism, "
            "free-trade zones (manufacturing), remittances, mining, and agriculture. "
            "Santo Domingo has wages significantly above rural areas. The tourism and "
            "hospitality sector is a major formal employer."
        ),
    },
    "JM": {
        "name": "Jamaica", "continent": "Americas",
        "region": "Central America & Caribbean", "sub_region": "Caribbean",
        "market_tier": "emerging", "currency": "JMD",
        "context": (
            "Jamaica's formal economy is driven by tourism (largest sector), bauxite/alumina, "
            "agriculture (sugar, coffee, yams), financial services, remittances, and "
            "a growing BPO/shared services sector in Kingston. English proficiency "
            "and the US/UK diaspora connections fuel outsourcing growth."
        ),
    },
    "TT": {
        "name": "Trinidad and Tobago", "continent": "Americas",
        "region": "Central America & Caribbean", "sub_region": "Caribbean",
        "market_tier": "emerging", "currency": "TTD",
        "context": (
            "Trinidad and Tobago is the Caribbean's wealthiest economy per capita, "
            "driven by oil and natural gas exports. Key sectors: energy, petrochemicals, "
            "financial services, retail, construction, and public administration. "
            "Port of Spain has the region's most developed financial services cluster."
        ),
    },
    "PY": {
        "name": "Paraguay", "continent": "Americas", "region": "South America",
        "sub_region": "Southern Cone", "market_tier": "emerging",
        "currency": "PYG",
        "context": (
            "Paraguay is a fast-growing agricultural exporter (soybeans, beef, corn) "
            "with cheap hydroelectric power (Itaipú Dam co-owned with Brazil). "
            "Key sectors: agriculture, energy re-export, retail, construction, "
            "and financial services. Asunción dominates in formal employment. "
            "Low tax rates attract regional businesses."
        ),
    },
    # ── AFRICA ────────────────────────────────────────────────────────────────
    "NG": {
        "name": "Nigeria", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "West Africa", "market_tier": "emerging",
        "currency": "NGN",
        "context": (
            "Nigeria is Africa's largest economy (by GDP) and most populous nation. "
            "Key formal sectors: oil and gas (NNPC, major IOCs), financial services "
            "(Lagos is Africa's finance capital), telecommunications, retail (FMCG), "
            "construction, manufacturing, agriculture (cassava, yam, sorghum — major "
            "employer), and a rapidly growing technology startup ecosystem (Flutterwave, "
            "Paystack, Andela based in Lagos). Lagos wages significantly exceed "
            "Abuja and other cities. Oil and gas, banking, and technology pay the "
            "highest formal salaries."
        ),
    },
    "ZA": {
        "name": "South Africa", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Southern Africa", "market_tier": "emerging",
        "currency": "ZAR",
        "context": (
            "South Africa has the continent's most industrialised economy with world-class "
            "financial and legal infrastructure. Key sectors: mining (gold, platinum, coal, "
            "manganese), financial services (Johannesburg Stock Exchange — Africa's largest), "
            "retail (Shoprite, Woolworths), manufacturing (automotive — Toyota, BMW), "
            "healthcare, education, and a significant public sector. High unemployment "
            "and inequality persist; the formal sector wage premium is substantial. "
            "Cape Town leads in technology and tourism; Johannesburg in finance and mining."
        ),
    },
    "KE": {
        "name": "Kenya", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "East Africa", "market_tier": "emerging",
        "currency": "KES",
        "context": (
            "Kenya is East Africa's economic hub with a strong financial services sector, "
            "a dominant M-Pesa fintech ecosystem, and Nairobi as a regional HQ for "
            "multinationals and NGOs. Key sectors: financial services (Equity Bank, "
            "KCB), telecommunications (Safaricom), agriculture (tea, coffee, horticulture — "
            "major exports), tourism, manufacturing, construction, and healthcare. "
            "The technology scene (iHub, Andela) is growing rapidly. Nairobi wages "
            "significantly exceed rural and Coast/Rift Valley regions."
        ),
    },
    "ET": {
        "name": "Ethiopia", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "East Africa", "market_tier": "frontier",
        "currency": "ETB",
        "context": (
            "Ethiopia is Africa's second most populous country and has been among the "
            "fastest-growing economies globally. Key sectors: agriculture (coffee, teff, "
            "cut flowers — major exports; ~75% of employment), garment manufacturing "
            "(export-oriented industrial parks), construction (major government projects), "
            "telecommunications, and financial services. Addis Ababa has the highest "
            "formal wages. The Ethiopian Airlines ecosystem is a leading employer."
        ),
    },
    "GH": {
        "name": "Ghana", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "West Africa", "market_tier": "emerging",
        "currency": "GHS",
        "context": (
            "Ghana is West Africa's most politically stable democracy and an important "
            "economic hub. Key sectors: gold and cocoa exports (major global producer), "
            "oil and gas (offshore Jubilee Field), financial services, telecommunications, "
            "retail, healthcare, and education. Accra's tech ecosystem (mPharma, Zeepay) "
            "is growing. Government and NGO/international organisation employment is "
            "significant."
        ),
    },
    "TZ": {
        "name": "Tanzania", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "East Africa", "market_tier": "frontier",
        "currency": "TZS",
        "context": (
            "Tanzania's economy is largely agricultural (sisal, coffee, tea, cashews, "
            "tobacco) alongside tourism (Serengeti, Kilimanjaro, Zanzibar), mining "
            "(gold, diamonds, tanzanite), construction, and financial services. "
            "Dar es Salaam concentrates formal private sector employment. "
            "Anticipated natural gas production from offshore fields could transform "
            "the formal wage landscape significantly."
        ),
    },
    "UG": {
        "name": "Uganda", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "East Africa", "market_tier": "frontier",
        "currency": "UGX",
        "context": (
            "Uganda has a young, rapidly growing population. Key sectors: agriculture "
            "(coffee, maize, plantain — ~70% of employment), financial services, "
            "telecommunications, retail, construction, and a growing technology scene "
            "in Kampala. The NGO and international development sector is a significant "
            "formal employer with competitive wages."
        ),
    },
    "AO": {
        "name": "Angola", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Central Africa", "market_tier": "frontier",
        "currency": "AOA",
        "context": (
            "Angola is Africa's second-largest oil producer; the petroleum sector "
            "dominates formal wages and government revenue. Outside oil, key sectors "
            "include diamond mining, agriculture (cassava, maize), construction, "
            "financial services, and retail. Luanda is among Africa's most expensive "
            "cities; oil industry wages are disproportionately high."
        ),
    },
    "RW": {
        "name": "Rwanda", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "East Africa", "market_tier": "frontier",
        "currency": "RWF",
        "context": (
            "Rwanda has undergone remarkable transformation since 1994 and is now among "
            "Africa's fastest-growing economies with ambitions to become a knowledge "
            "economy hub (Kigali Innovation City). Key sectors: agriculture (coffee, tea, "
            "pyrethrum), tourism (gorilla trekking), financial services, technology, "
            "and a strong public sector. Wages are low by global standards but growing."
        ),
    },
    "SN": {
        "name": "Senegal", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "West Africa", "market_tier": "frontier",
        "currency": "XOF",
        "context": (
            "Senegal is West Africa's most stable democracy and a growing economy. "
            "Key sectors: fishing (major export), groundnuts (peanuts), phosphate mining, "
            "tourism (Dakar, Saint-Louis), financial services, and telecommunications. "
            "Dakar is a regional hub for financial institutions and development organisations. "
            "Emerging oil and gas production could significantly change the wage landscape."
        ),
    },
    "CI": {
        "name": "Côte d'Ivoire", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "West Africa", "market_tier": "frontier",
        "currency": "XOF",
        "context": (
            "Côte d'Ivoire is the world's largest cocoa producer and West Africa's "
            "most dynamic economy. Key sectors: cocoa and agriculture (coffee, rubber, "
            "palm oil), manufacturing, financial services (Abidjan is a major UEMOA "
            "financial centre), construction, retail, and telecommunications."
        ),
    },
    "CM": {
        "name": "Cameroon", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Central Africa", "market_tier": "frontier",
        "currency": "XAF",
        "context": (
            "Cameroon is Central Africa's largest economy with a diversified base: "
            "oil exports, agriculture (cocoa, coffee, palm oil, timber), manufacturing, "
            "financial services, and public administration. Douala is the commercial "
            "capital; Yaoundé is the political capital and public sector hub."
        ),
    },
    "MZ": {
        "name": "Mozambique", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Southern Africa", "market_tier": "frontier",
        "currency": "MZN",
        "context": (
            "Mozambique is a lower-income country with significant natural gas reserves "
            "(LNG projects under development). Current key sectors: agriculture (cashews, "
            "cotton, tobacco), coal mining, aluminium smelting (Mozal), financial services, "
            "and construction. Maputo has much higher wages than rural provinces."
        ),
    },
    "ZW": {
        "name": "Zimbabwe", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Southern Africa", "market_tier": "frontier",
        "currency": "USD",
        "context": (
            "Zimbabwe uses a multi-currency system (USD dominant). Key sectors: mining "
            "(platinum, gold, lithium — growing), agriculture (tobacco — major export), "
            "manufacturing, financial services, and retail. Harare has the most developed "
            "formal labour market. Brain drain has reduced professional talent supply, "
            "supporting wages for remaining skilled workers."
        ),
    },
    "ZM": {
        "name": "Zambia", "continent": "Africa", "region": "Sub-Saharan Africa",
        "sub_region": "Southern Africa", "market_tier": "frontier",
        "currency": "ZMW",
        "context": (
            "Zambia is a major copper producer (Copperbelt region). Other key sectors: "
            "agriculture (maize, tobacco, cotton), construction, financial services, "
            "and retail. Lusaka and Copperbelt cities concentrate formal employment. "
            "Mining engineering and financial services command premium wages."
        ),
    },
    # ── MENA ──────────────────────────────────────────────────────────────────
    "AE": {
        "name": "United Arab Emirates", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "AED",
        "context": (
            "The UAE (Dubai + Abu Dhabi + 5 other emirates) is the GCC's most diversified "
            "economy and a global hub for finance, trade, tourism, and professional services. "
            "The tax-free salary structure and high purchasing power attract top international "
            "talent. Key sectors: financial services (DIFC), real estate, construction, "
            "tourism and hospitality, retail, aviation (Emirates, Etihad), healthcare, "
            "education, and a growing technology ecosystem (Hub71, ADGM). "
            "Nearly 90% of the private sector workforce is expatriate."
        ),
    },
    "SA": {
        "name": "Saudi Arabia", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "SAR",
        "context": (
            "Saudi Arabia is executing Vision 2030, diversifying from oil toward tourism, "
            "entertainment, fintech, manufacturing, logistics, and healthcare. Key sectors: "
            "oil and gas (Saudi Aramco — world's most profitable company), financial "
            "services (Al Rajhi Bank), construction (NEOM, Red Sea Project), retail, "
            "healthcare, and education. Saudisation (Nitaqat) mandates local hiring quotas. "
            "Riyadh and Jeddah dominate formal employment."
        ),
    },
    "EG": {
        "name": "Egypt", "continent": "Africa", "region": "Middle East & North Africa",
        "sub_region": "North Africa", "market_tier": "emerging",
        "currency": "EGP",
        "context": (
            "Egypt is the Arab world's most populous country and a major emerging economy. "
            "Key sectors: Suez Canal revenues, tourism (historical sites, Red Sea), "
            "natural gas and oil, financial services, manufacturing (textiles, food, "
            "chemicals), retail, agriculture (cotton, wheat), construction, and healthcare. "
            "Cairo and Alexandria have the highest formal wages. Remittances from Egyptians "
            "working in the Gulf are significant."
        ),
    },
    "MA": {
        "name": "Morocco", "continent": "Africa", "region": "Middle East & North Africa",
        "sub_region": "North Africa", "market_tier": "emerging",
        "currency": "MAD",
        "context": (
            "Morocco is a growing hub between Europe and Africa. Key sectors: phosphate "
            "mining and chemicals (OCP — world's largest phosphate exporter), automotive "
            "manufacturing (Renault, PSA/Stellantis), aerospace, tourism, agriculture "
            "(citrus, olives, vegetables), financial services, and outsourcing/BPO "
            "(French-language capabilities). Casablanca dominates finance; Rabat is "
            "the government centre; Tangier leads in manufacturing."
        ),
    },
    "IL": {
        "name": "Israel", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Levant", "market_tier": "mature",
        "currency": "ILS",
        "context": (
            "Israel ('Startup Nation') has one of the world's most innovative technology "
            "ecosystems, with the highest density of tech startups globally per capita. "
            "Major sectors: technology and cyber security (R&D centres of Intel, Google, "
            "Microsoft, Amazon, Meta), defence, financial services, agriculture (agritech), "
            "healthcare (life sciences), manufacturing, and tourism. Tel Aviv–Yafo "
            "wages are among the highest in the Middle East."
        ),
    },
    "TR": {
        "name": "Turkey", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Near East", "market_tier": "emerging",
        "currency": "TRY",
        "context": (
            "Turkey straddles Europe and Asia and has a large, diverse economy. Key sectors: "
            "manufacturing (automotive, textiles, steel, white goods), construction and real "
            "estate, financial services (Istanbul is Turkey's financial hub), tourism, "
            "agriculture (hazelnuts, tomatoes, wheat — major exporter), technology, and "
            "healthcare. Istanbul dominates in wages; Ankara in public sector employment. "
            "High inflation means nominal wages are frequently renegotiated."
        ),
    },
    "JO": {
        "name": "Jordan", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Levant", "market_tier": "emerging",
        "currency": "JOD",
        "context": (
            "Jordan has a service-oriented economy with key sectors in financial services, "
            "IT/technology (growing Amman tech scene), tourism (Petra, Wadi Rum, Dead Sea), "
            "pharmaceuticals, potash and phosphate mining, healthcare, education, and "
            "a large public sector. Jordan hosts a significant refugee population "
            "and substantial humanitarian/NGO sector employment."
        ),
    },
    "TN": {
        "name": "Tunisia", "continent": "Africa", "region": "Middle East & North Africa",
        "sub_region": "North Africa", "market_tier": "emerging",
        "currency": "TND",
        "context": (
            "Tunisia has a well-educated workforce and a diversified economy. Key sectors: "
            "manufacturing (textiles, automotive components — Leoni, Dräxlmaier for European "
            "OEMs), tourism, olive oil exports, financial services, phosphate mining, and "
            "a growing ICT/outsourcing sector (French-language capabilities). Tunis "
            "dominates in professional services and finance."
        ),
    },
    "QA": {
        "name": "Qatar", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "QAR",
        "context": (
            "Qatar has the world's highest GDP per capita driven by natural gas "
            "and oil wealth. Qatar Energy (QE) and its subsidiaries are the dominant "
            "employers. Other key sectors: financial services (QFC), construction, "
            "aviation (Qatar Airways), retail, hospitality, and education (Education "
            "City hosts branches of Georgetown, Cornell, CMU, etc.). "
            "Over 85% of the workforce is foreign nationals."
        ),
    },
    "KW": {
        "name": "Kuwait", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "KWD",
        "context": (
            "Kuwait's public sector employs the majority of Kuwaiti nationals with "
            "high salaries and extensive benefits. The private sector relies heavily "
            "on expatriate labour. Key sectors: oil (Kuwait Petroleum Corporation), "
            "financial services (NBK), construction, retail, healthcare, and education. "
            "The KWD is the world's highest-valued currency unit."
        ),
    },
    "BH": {
        "name": "Bahrain", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "BHD",
        "context": (
            "Bahrain is a financial services hub hosting numerous GCC regional HQs. "
            "Key sectors: financial services (CBB-regulated hub), oil refining (BAPCO), "
            "aluminium smelting (Alba), construction, retail, tourism (medical and "
            "shopping tourism from Saudi Arabia), and information technology. "
            "Lower cost of living than UAE and Qatar makes it competitive for professionals."
        ),
    },
    "OM": {
        "name": "Oman", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Gulf (GCC)", "market_tier": "mature",
        "currency": "OMR",
        "context": (
            "Oman is diversifying from oil toward tourism, logistics, manufacturing, "
            "and fisheries under Vision 2040. Key sectors: oil and gas, financial services, "
            "construction, retail, tourism (Muscat, Salalah), fisheries, and a growing "
            "special economic zones industry. Omanisation policies require increasing "
            "local hiring in the private sector."
        ),
    },
    "DZ": {
        "name": "Algeria", "continent": "Africa", "region": "Middle East & North Africa",
        "sub_region": "North Africa", "market_tier": "emerging",
        "currency": "DZD",
        "context": (
            "Algeria is Africa's largest country with significant hydrocarbon wealth. "
            "Key sectors: oil and gas (Sonatrach — Africa's largest energy company), "
            "agriculture (cereals, dates, olive oil), construction (major public "
            "investment), financial services, and public administration. "
            "The public sector dominates formal employment; the private sector is smaller "
            "relative to GDP."
        ),
    },
    "IQ": {
        "name": "Iraq", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Near East", "market_tier": "frontier",
        "currency": "IQD",
        "context": (
            "Iraq is one of the world's largest oil producers. Outside the oil sector, "
            "formal employment is concentrated in public administration, construction, "
            "retail, and financial services. Baghdad and Basra (oil hub) have the "
            "highest formal wages. Reconstruction and infrastructure development are "
            "ongoing major sectors."
        ),
    },
    "LB": {
        "name": "Lebanon", "continent": "Middle East",
        "region": "Middle East", "sub_region": "Levant", "market_tier": "frontier",
        "currency": "LBP",
        "context": (
            "Lebanon faces severe economic crisis; wages are significantly eroded by "
            "hyperinflation. The formal economy is concentrated in financial services "
            "(historically), trade, healthcare, education, and hospitality. "
            "USD-indexed contracts are now common for professional roles. The diaspora "
            "and NGO/UN sector are key sources of foreign-currency employment."
        ),
    },
    # ── OCEANIA ───────────────────────────────────────────────────────────────
    "AU": {
        "name": "Australia", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Australasia", "market_tier": "mature",
        "currency": "AUD",
        "context": (
            "Australia has one of the world's highest minimum wages and strong workers' "
            "rights protections under the Fair Work Act. Key sectors: mining (iron ore, "
            "coal, LNG — world-leading exporter), financial services (the 'Big Four' banks), "
            "healthcare (growing with aging population), construction, education, retail "
            "(Woolworths, Coles), agriculture (wheat, beef, dairy), and a growing technology "
            "sector (Sydney, Melbourne, Brisbane). Mining engineers and specialists in "
            "Perth (Western Australia) command some of the highest wages in the world."
        ),
    },
    "NZ": {
        "name": "New Zealand", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Australasia", "market_tier": "mature",
        "currency": "NZD",
        "context": (
            "New Zealand has strong wages relative to cost of living and excellent "
            "work-life balance. Key sectors: agriculture (dairy, sheep, wine, kiwifruit — "
            "dominant exports), tourism (pre/post-COVID), financial services, healthcare, "
            "construction, technology (growing Wellington and Auckland clusters), and "
            "education (international students). The public sector (healthcare, education, "
            "government) is a major employer. Remote work has driven relocation to "
            "regional centres."
        ),
    },
    "FJ": {
        "name": "Fiji", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Melanesia", "market_tier": "frontier",
        "currency": "FJD",
        "context": (
            "Fiji's formal economy is driven by tourism (largest sector), sugar cane "
            "production and processing, financial services, garment manufacturing, and "
            "fisheries. Suva is the administrative and commercial capital; Nadi is the "
            "tourism hub. Remittances from Fijians working in Australia, New Zealand, "
            "and the UK are significant."
        ),
    },
    "PG": {
        "name": "Papua New Guinea", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Melanesia", "market_tier": "frontier",
        "currency": "PGK",
        "context": (
            "Papua New Guinea is resource-rich with significant LNG (ExxonMobil PNG LNG), "
            "gold (Lihir, Porgera), copper, and timber. The formal labour market is "
            "small relative to population; most people are in subsistence agriculture. "
            "Port Moresby has the highest formal wages. The public sector and resource "
            "industry are the dominant formal employers."
        ),
    },
    "WS": {
        "name": "Samoa", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Polynesia", "market_tier": "frontier",
        "currency": "WST",
        "context": (
            "Samoa's small economy depends on remittances (largest income source), "
            "tourism, agriculture (coconut products, taro), and fisheries. Apia is "
            "the centre of formal employment in government, retail, and services."
        ),
    },
    "TO": {
        "name": "Tonga", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Polynesia", "market_tier": "frontier",
        "currency": "TOP",
        "context": (
            "Tonga is heavily dependent on remittances from diaspora in New Zealand, "
            "Australia, and the US (~40% of GDP). Agriculture (squash, root crops, "
            "vanilla), fisheries, tourism, and public administration are the main "
            "formal sectors."
        ),
    },
    "SB": {
        "name": "Solomon Islands", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Melanesia", "market_tier": "frontier",
        "currency": "SBD",
        "context": (
            "The Solomon Islands economy relies on timber exports, fishing, palm oil, "
            "cocoa, and subsistence agriculture. Honiara concentrates formal employment "
            "in government, financial services, and retail. The public sector is the "
            "largest formal employer."
        ),
    },
    "VU": {
        "name": "Vanuatu", "continent": "Oceania",
        "region": "Oceania", "sub_region": "Melanesia", "market_tier": "frontier",
        "currency": "VUV",
        "context": (
            "Vanuatu's economy is centred on tourism, offshore financial services "
            "(citizenship by investment programme), agriculture (kava, copra, cocoa), "
            "and fisheries. Port Vila is the formal employment centre. The informal "
            "and subsistence sectors employ the majority."
        ),
    },
}

# Region groupings for batch fetching and standalone script mode
REGION_COUNTRIES: dict[str, list[str]] = {
    "asia": ["SG", "IN", "JP", "CN", "KR", "PH", "MY", "TH", "ID", "VN",
             "BD", "HK", "PK", "LK"],
    "latam": ["BR", "MX", "AR", "CO", "CL", "PE", "EC", "BO", "UY", "PA",
              "CR", "GT", "HN", "DO", "JM", "TT", "PY"],
    "africa": ["NG", "ZA", "KE", "ET", "GH", "TZ", "UG", "AO", "RW", "SN",
               "CI", "CM", "MZ", "ZW", "ZM"],
    "mena": ["AE", "SA", "EG", "MA", "IL", "TR", "JO", "TN", "QA", "KW",
             "BH", "OM", "DZ", "IQ", "LB"],
    "oceania": ["AU", "NZ", "FJ", "PG", "WS", "TO", "SB", "VU"],
}


# ── Standalone runner ─────────────────────────────────────────────────────────

def run_ilo_for_region(
    region: str,
    output_path: Path,
    *,
    dry_run: bool = False,
    use_cache: bool = True,
    start_year: int = 2018,
) -> list[dict]:
    """Fetch ILO data for a named region and build document list.

    Does NOT write to disk — returns the list. Caller decides whether to write.
    """
    countries = REGION_COUNTRIES.get(region, [])
    if not countries:
        print(f"  Unknown region '{region}'")
        return []

    print(f"\n{'─' * 60}")
    print(f"ILO fetch: {region.upper()} ({len(countries)} countries)")
    print(f"{'─' * 60}")

    occ_all = fetch_ilo_data(
        _IND_EARNINGS_BY_OCCUPATION, countries,
        start_year=start_year, use_cache=use_cache,
    )
    time.sleep(_DELAY)
    ind_all = fetch_ilo_data(
        _IND_EARNINGS_BY_INDUSTRY, countries,
        start_year=start_year, use_cache=use_cache,
    )

    docs: list[dict] = []
    countries_with_data = set(occ_all) | set(ind_all)

    for iso2 in countries:
        meta = COUNTRY_META.get(iso2)
        if not meta:
            continue
        occ = occ_all.get(iso2, {})
        ind = ind_all.get(iso2, {})
        if not occ and not ind:
            print(f"  {iso2}: no ILO earnings data available — skipping")
            continue
        country_docs = build_ilo_documents(iso2, meta, occ, ind)
        docs.extend(country_docs)
        print(f"  {iso2} ({meta['name']}): {len(country_docs)} documents")

    print(f"\n  → {region.upper()} total: {len(docs)} ILO documents "
          f"({len(countries_with_data)}/{len(countries)} countries with data)")

    if not dry_run and docs:
        existing: list[dict] = []
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing_ids = {d["id"] for d in existing}
        new_docs = [d for d in docs if d["id"] not in existing_ids]
        updated = [d for d in existing if d["id"] not in {x["id"] for x in docs}]
        updated.extend(docs)
        output_path.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Written {len(updated)} docs to {output_path.name} "
              f"({len(new_docs)} new, {len(docs) - len(new_docs)} updated)")

    return docs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ILO ILOSTAT wage data for global career KB",
    )
    parser.add_argument(
        "--regions", default="all",
        help="Comma-separated list of regions: asia,latam,africa,mena,oceania  or  'all'",
    )
    parser.add_argument(
        "--output-dir", default="data/knowledge-base",
        help="Directory to write output JSON files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and parse data but do not write files",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Bypass disk cache and always re-fetch from ILO API",
    )
    parser.add_argument(
        "--start-year", type=int, default=2018,
        help="Earliest year to fetch (default: 2018)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    use_cache = not args.no_cache

    regions_to_run = (
        list(REGION_COUNTRIES.keys())
        if args.regions.strip().lower() == "all"
        else [r.strip() for r in args.regions.split(",")]
    )

    all_docs: list[dict] = []
    for region in regions_to_run:
        out_file = out_dir / f"global_market_ilo_{region}.json"
        docs = run_ilo_for_region(
            region,
            out_file,
            dry_run=args.dry_run,
            use_cache=use_cache,
            start_year=args.start_year,
        )
        all_docs.extend(docs)

    print(f"\n{'=' * 60}")
    print(f"ILO ILOSTAT total: {len(all_docs)} documents across "
          f"{len(regions_to_run)} region(s)")
    print(f"Attribution: ILOSTAT, International Labour Organization")
    print(f"License: CC BY 4.0 — https://ilostat.ilo.org/data/")


if __name__ == "__main__":
    main()
