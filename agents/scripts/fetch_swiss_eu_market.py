"""fetch_swiss_eu_market.py — Fetch real Swiss/EU labour-market data.

Sources
-------
1. Eurostat REST API  (ec.europa.eu, CC BY 4.0, no key)
   • htec_emp_nisced2  — High-tech sector employment share (annual, 2008–latest)
   • isoc_ske_ittn2    — % enterprises with ICT specialists (annual, 2010–latest)
   • earn_nt_net       — Gross annual earnings at average wage (annual, 2004–latest)

2. Swiss BFS PXWEB API  (www.pxweb.bfs.admin.ch, no auth)
   • px-x-0304010000_201 — Monthly gross wage by region × sector × level (2012–2024)

3. frankfurter.app  (no key, no registration)
   • Live CHF → EUR / USD exchange rates (enriches Swiss wage documents)

4. Adzuna Jobs API  (developer.adzuna.com, free key)
   • Live tech job counts + advertised salaries by EU country and role category
   • Set ADZUNA_APP_ID and ADZUNA_APP_KEY in apps/api/.env
   • Free tier: 100 req/day

Output
------
  swiss_eu_market_real.json — ready for SwissEUMarketLoader ingestion (~50 documents)

Usage
-----
  cd agents
  python -m scripts.fetch_swiss_eu_market --output-dir data/knowledge-base
  python -m scripts.fetch_swiss_eu_market --output-dir data/knowledge-base --dry-run
  python -m scripts.fetch_swiss_eu_market --output-dir data/knowledge-base --skip-adzuna
"""
from __future__ import annotations

import argparse
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

# Load .env for Adzuna API credentials
_ENV_FILE = Path(__file__).resolve().parents[2] / "apps" / "api" / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                if _k not in os.environ:
                    os.environ[_k] = _v.strip().strip('"').strip("'")

# ── Constants ─────────────────────────────────────────────────────────────────

_UA = (
    "CareerRoadmapAI/1.0 (career-coaching-platform; "
    "contact: rogerjeasybavibidila@gmail.com) python-urllib/3.12"
)

_EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
_BFS_BASE = "https://www.pxweb.bfs.admin.ch/api/v1/de"
_BFS_DB = "px-x-0304010000_201"
_BFS_TABLE = "px-x-0304010000_201.px"

_DELAY = 0.8  # seconds between requests

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"
_ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

# EU countries where Adzuna has confirmed coverage (ISO 2-letter, lowercase).
# Sweden ("se") removed — Adzuna API returns 404 for that country code.
_ADZUNA_EU_COUNTRIES: dict[str, str] = {
    "at": "Austria",
    "be": "Belgium",
    "de": "Germany",
    "es": "Spain",
    "fr": "France",
    "it": "Italy",
    "nl": "Netherlands",
    "pl": "Poland",
}

# Role search queries and human labels for Adzuna — tech roles
_ADZUNA_TECH_QUERIES: list[tuple[str, str]] = [
    ("software engineer",        "Software Engineering"),
    ("data scientist",           "Data Science & Analytics"),
    ("cloud devops engineer",    "Cloud & DevOps"),
    ("cybersecurity analyst",    "Cybersecurity"),
    ("machine learning engineer","AI & Machine Learning"),
]

# Non-tech / cross-functional roles — covers finance, product, design, ops
_ADZUNA_NON_TECH_QUERIES: list[tuple[str, str]] = [
    ("product manager",   "Product Management"),
    ("ux designer",       "UX & Product Design"),
    ("financial analyst", "Financial Analysis"),
    ("marketing manager", "Marketing & Growth"),
    ("project manager",   "Project Management"),
    ("business analyst",  "Business Analysis"),
    ("data analyst",      "Data & Business Analytics"),
]

# Combined list used in API calls (12 queries × 8 countries = 96 req/run, within 100/day free tier)
_ADZUNA_ALL_QUERIES: list[tuple[str, str]] = _ADZUNA_TECH_QUERIES + _ADZUNA_NON_TECH_QUERIES

# ISCO-08 major occupation group labels (Eurostat earn_ses_pub3a)
_ISCO_MAJOR_GROUPS: dict[str, str] = {
    "OC1":   "Managers",
    "OC2":   "Professionals",
    "OC3":   "Technicians and Associate Professionals",
    "OC4":   "Clerical Support Workers",
    "OC5":   "Service and Sales Workers",
    "OC7":   "Craft and Related Trades Workers",
    "OC8":   "Plant and Machine Operators",
    "OC9":   "Elementary Occupations",
    "TOTAL": "All occupation groups",
}

# Non-tech career role profiles for salary triangulation.
# bls_sector_ratio: (US BLS OES 2024) occupation median / sector median — applied as
#   relative EU adjustment since EU sector structure differs only by scale.
# entry_factor / senior_factor: fraction of mid-level estimate (calibrated from
#   European salary survey percentiles: Mercer, Korn Ferry EU 2024 published summaries).
_NONTECH_ROLE_PROFILES: dict[str, dict] = {
    "Product Manager": {
        "primary_nace": "J", "secondary_nace": "M",
        "isco_group": "OC1", "bls_sector_ratio": 1.18,
        "entry_factor": 0.68, "senior_factor": 1.45,
        "description": (
            "Defines product vision and roadmap. High demand in tech companies, "
            "e-commerce, fintech, and digital transformation consulting."
        ),
    },
    "Financial Analyst": {
        "primary_nace": "K", "secondary_nace": "M",
        "isco_group": "OC2", "bls_sector_ratio": 1.16,
        "entry_factor": 0.72, "senior_factor": 1.55,
        "description": (
            "Analyses financial performance, models investments, and supports decisions. "
            "Roles in banks, insurance companies, investment firms, and corporate finance."
        ),
    },
    "Business Analyst": {
        "primary_nace": "M", "secondary_nace": "J",
        "isco_group": "OC2", "bls_sector_ratio": 0.89,
        "entry_factor": 0.72, "senior_factor": 1.35,
        "description": (
            "Bridges business requirements and technical solutions. "
            "Core role in management consulting, banking, and enterprise IT projects."
        ),
    },
    "UX Designer": {
        "primary_nace": "J", "secondary_nace": "M",
        "isco_group": "OC2", "bls_sector_ratio": 0.84,
        "entry_factor": 0.72, "senior_factor": 1.30,
        "description": (
            "Designs digital user experiences. Primarily in technology companies, "
            "digital agencies, media, and e-commerce."
        ),
    },
    "Marketing Manager": {
        "primary_nace": "M", "secondary_nace": "G",
        "isco_group": "OC1", "bls_sector_ratio": 1.05,
        "entry_factor": 0.70, "senior_factor": 1.50,
        "description": (
            "Drives brand, demand generation, and digital marketing. "
            "Roles across all industries: FMCG, tech, finance, and e-commerce."
        ),
    },
    "Project Manager": {
        "primary_nace": "M", "secondary_nace": "J",
        "isco_group": "OC2", "bls_sector_ratio": 1.03,
        "entry_factor": 0.75, "senior_factor": 1.40,
        "description": (
            "Manages delivery of complex projects and programmes. "
            "Cross-sector demand: IT, construction, financial services, and consulting."
        ),
    },
    "Data Analyst": {
        "primary_nace": "J", "secondary_nace": "K",
        "isco_group": "OC2", "bls_sector_ratio": 0.68,
        "entry_factor": 0.72, "senior_factor": 1.30,
        "description": (
            "Extracts and visualises insights from business data. "
            "Growing demand in tech, finance, retail, and e-commerce."
        ),
    },
}

# Top EU/EEA markets to generate per-country non-tech role salary cards for
_TOP_EU_MARKETS_ROLE_CARDS: list[str] = [
    "DE", "FR", "NL", "IE", "SE", "ES", "BE", "PL", "IT", "AT",
]

# NACE Rev.2 sector labels (Eurostat earn_ses_pub1a) — key sectors for career coaching
_NACE_SECTOR_LABELS: dict[str, str] = {
    "J":    "Information & Communication (ICT)",
    "K":    "Finance & Insurance",
    "M":    "Professional, Scientific & Technical",
    "C":    "Manufacturing (incl. Pharma)",
    "Q":    "Human Health & Social Work",
    "O":    "Public Administration & Defence",
    "P":    "Education",
    "N":    "Administrative & Support Services",
    "H":    "Transportation & Storage",
    "G":    "Wholesale & Retail Trade",
}

# BFS region codes → human name + included cantons
_BFS_REGIONS: dict[str, tuple[str, str]] = {
    "-1": ("Switzerland", "CH total — all 26 cantons"),
    "1":  ("Région lémanique", "Geneva (GE), Vaud (VD), Valais (VS)"),
    "2":  ("Espace Mittelland", "Bern (BE), Fribourg (FR), Solothurn (SO), Neuchâtel (NE), Jura (JU)"),
    "3":  ("Nordwestschweiz", "Basel-Stadt (BS), Basel-Landschaft (BL), Aargau (AG)"),
    "4":  ("Zurich", "Zurich (ZH)"),
    "5":  ("Ostschweiz", "St. Gallen (SG), Grisons (GR), Thurgau (TG), Schaffhausen (SH), Appenzell"),
    "6":  ("Zentralschweiz", "Lucerne (LU), Zug (ZG), Schwyz (SZ), Obwalden (OW), Nidwalden (NW), Uri (UR)"),
    "7":  ("Ticino", "Ticino (TI)"),
}

# BFS sector codes → readable label
_BFS_SECTORS: dict[str, str] = {
    "-1": "All sectors",
    "62": "IT services (NACE J62)",
    "61": "Telecommunications (NACE J61)",
    "63": "Information services (NACE J63)",
    "64": "Financial services (NACE K64)",
    "65": "Insurance (NACE K65)",
    "72": "Research & Development (NACE M72)",
    "21": "Pharmaceuticals (NACE C21)",
    "71": "Engineering & consulting (NACE M71)",
    "70": "Management consulting (NACE M70)",
    "84": "Public administration (NACE O84)",
    "85": "Education (NACE P85)",
    "86": "Healthcare (NACE Q86)",
}

# BFS percentile codes
_BFS_PERCENTILES: dict[str, str] = {
    "1": "Median",
    "3": "P25",
    "4": "P75",
}

# Region-specific tech-ecosystem context
_REGION_CONTEXT: dict[str, str] = {
    "-1": (
        "Switzerland combines the highest average wages in Europe with a strong multi-lingual "
        "workforce and a world-class research infrastructure (ETH Zurich, EPFL). The Swiss franc "
        "is not in the euro zone; salaries are quoted gross in CHF. Mandatory deductions include "
        "AHV/IV/EO (~5.3%), ALV (~1.1%), pension fund (BVG, varies), and accident insurance. "
        "Net take-home is typically 75–85% of gross depending on canton and family situation."
    ),
    "1": (
        "The Région lémanique (Geneva, Lausanne/Vaud, Sion/Valais) hosts EPFL, Nestlé HQ, "
        "Logitech, IMD Business School, CERN, and numerous UN/WHO organisations. Geneva is the "
        "most expensive Swiss city for both housing and cost of living. The tech ecosystem spans "
        "medtech, biotech, fintech, and software. Cross-border workers from France represent a "
        "significant share of the workforce."
    ),
    "2": (
        "Espace Mittelland centres on Bern (federal capital) and Fribourg. Key employers include "
        "Swisscom HQ, Swiss Post, federal IT services, and Bernese research institutions. Wages "
        "are somewhat lower than Zurich or Geneva but cost of living is also lower."
    ),
    "3": (
        "Northwestern Switzerland (Basel-Stadt, Basel-Landschaft, Aargau) is the pharmaceutical "
        "and life-sciences capital of Europe: Novartis, Roche, Lonza, Syngenta, and BASF all "
        "maintain major operations here. ABB's global headquarters is in Baden (AG). Salaries "
        "in life sciences and engineering are among the highest in Switzerland."
    ),
    "4": (
        "Zurich is Switzerland's financial and technology hub. Google, Microsoft, IBM Research, "
        "LinkedIn, Salesforce, and many Swiss fintechs operate major engineering offices here. "
        "ETH Zurich produces top-tier engineering talent. The Zurich tech scene is particularly "
        "strong in machine learning, cloud infrastructure, and blockchain."
    ),
    "5": (
        "Eastern Switzerland (St. Gallen, Grisons, Thurgau, Schaffhausen) has a strong industrial "
        "and logistics base. St. Gallen hosts several fintech and insurtech start-ups and is close "
        "to both Zurich and the Austrian/German border labour markets."
    ),
    "6": (
        "Central Switzerland (Lucerne, Zug, Schwyz) includes Zug, Switzerland's crypto valley "
        "and low-tax canton. Numerous blockchain firms, commodity traders, and holding companies "
        "are headquartered in Zug. Overall wages here are among the highest for senior tech and "
        "finance roles."
    ),
    "7": (
        "Ticino is Italian-speaking and shares a cross-border labour market with Milan and the "
        "Lombardy tech cluster. Key sectors include logistics, banking, and pharmaceutical services. "
        "Wages are somewhat lower than German-speaking Switzerland but so is cost of living."
    ),
}

# EU country map (ISO 2-letter → name + brief context)
_EU_COUNTRIES: dict[str, tuple[str, str]] = {
    "AT": ("Austria",        "Vienna emerging tech hub, strong e-commerce and industrial software"),
    "BE": ("Belgium",        "Brussels EU institutions driving public IT; cybersecurity cluster in Leuven"),
    "BG": ("Bulgaria",       "Sofia low-cost tech hub, Telerik (Progress), growing nearshore IT"),
    "CY": ("Cyprus",         "Limassol emerging fintech; low corporation tax; nearshore services"),
    "CZ": ("Czech Republic", "Prague nearshore hub; Avast; strong automotive software (Skoda, Continental)"),
    "DE": ("Germany",        "Europe's largest tech market: Berlin, Munich, Hamburg; automotive & industrial IoT"),
    "DK": ("Denmark",        "Copenhagen cleantech; Novo Nordisk digital health; strong IT security cluster"),
    "EE": ("Estonia",        "e-governance pioneer (Skype, Wise birthplace); top EU digital-society ranking"),
    "EL": ("Greece",         "Athens tech scene growing; Workable, Blueground; strong shipping-tech"),
    "ES": ("Spain",          "Barcelona and Madrid booming startups; travel-tech and e-commerce"),
    "FI": ("Finland",        "Nokia heritage; strong gaming (Supercell, Rovio); deep HPC and data centres"),
    "FR": ("France",         "Paris Station F; La Défense finance tech; strong aerospace and luxury-tech"),
    "HR": ("Croatia",        "Zagreb tech scene; Infobip unicorn; Rimac electric vehicles"),
    "HU": ("Hungary",        "Budapest growing startup scene; Prezi; nearshore IT to Western Europe"),
    "IE": ("Ireland",        "EMEA HQ for US tech giants: Google, Meta, Apple, Microsoft, Intel"),
    "IT": ("Italy",          "Milan fintech; Turin automotive software; Rome public-sector IT"),
    "LT": ("Lithuania",      "Vilnius and Kaunas fintech growth; Revolut Lithuanian entity; EU banking licences"),
    "LU": ("Luxembourg",     "EIB and EU institution IT; satellite comms (SES); fund-tech and banking"),
    "LV": ("Latvia",         "Riga growing tech hub; airBaltic digital; strong IT outsourcing sector"),
    "MT": ("Malta",          "iGaming and fintech hub; growing blockchain regulatory framework"),
    "NL": ("Netherlands",    "Amsterdam scale-up capital; Booking.com, Adyen; ASML semiconductor ecosystem"),
    "PL": ("Poland",         "Largest CEE tech market; Kraków and Warsaw dev hubs; strong outsourcing"),
    "PT": ("Portugal",       "Lisbon Web Summit host; growing nearshore hub; strong remote-work ecosystem"),
    "RO": ("Romania",        "Bucharest and Cluj-Napoca fastest-growing IT outsourcing centres in EU"),
    "SE": ("Sweden",         "Stockholm unicorn capital: Spotify, Klarna; strong gaming and telecom heritage"),
    "SI": ("Slovenia",       "Ljubljana smart-city projects; industrial automation; strong engineering talent"),
    "SK": ("Slovakia",       "Bratislava between Vienna and Budapest; automotive software; nearshore IT"),
    "NO": ("Norway",         "Oslo energy-tech (oil & gas digitisation); strong maritime software cluster"),
    "IS": ("Iceland",        "100% renewable energy data centres; small but highly educated tech workforce"),
    "CH": ("Switzerland",    "Financial and innovation powerhouse; ETH Zurich/EPFL; highest EU-area wages"),
}

# Eurostat dataset → filters → readable label
_EUROSTAT_DATASETS: list[dict] = [
    {
        # Fetched as THS_PER for both HTC and TOTAL nace_r2 in one request;
        # high-tech % is computed post-hoc as (HTC / TOTAL) * 100.
        "code": "htec_emp_nisced2",
        "params": {
            "unit": "THS_PER",
            "isced11": "TOTAL",
            "sinceTimePeriod": "2021",
        },
        "label": "High-tech employment (computed % of total employment)",
        "geo_dim": "geo",
        "time_dim": "time",
        "filter_dims": {"unit": "THS_PER", "isced11": "TOTAL"},
        "compute_ratio": {"numerator": "HTC", "denominator": "TOTAL", "dim": "nace_r2"},
    },
    {
        "code": "isoc_ske_ittn2",
        "params": {
            "indic_is": "E_ITT2",
            "unit": "PC_ENT",
            "sinceTimePeriod": "2020",
        },
        "label": "Enterprises with ICT specialists (% of all enterprises)",
        "geo_dim": "geo",
        "time_dim": "time",
        "filter_dims": {"indic_is": "E_ITT2", "unit": "PC_ENT"},
    },
    {
        "code": "earn_nt_net",
        "params": {
            "currency": "EUR",
            "estruct": "GRS",
            "ecase": "P1_NCH_AW100",
            "sinceTimePeriod": "2021",
        },
        "label": "Gross annual earnings at 100% average wage (EUR)",
        "geo_dim": "geo",
        "time_dim": "time",
        "filter_dims": {"currency": "EUR", "estruct": "GRS", "ecase": "P1_NCH_AW100"},
    },
]


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = 30) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        print(f"  WARN GET {url[:80]} → HTTP {exc.code}")
    except Exception as exc:
        print(f"  WARN GET {url[:80]} → {exc}")
    return None


def _http_post(url: str, body: dict, timeout: int = 30) -> bytes | None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": _UA, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        print(f"  WARN POST {url[:80]} → HTTP {exc.code}")
    except Exception as exc:
        print(f"  WARN POST {url[:80]} → {exc}")
    return None


# ── JSON-stat parser ───────────────────────────────────────────────────────────

def _parse_jsonstat(raw: dict) -> tuple[list[str], dict[tuple[str, ...], float]]:
    """Parse JSON-stat 2.0 (Eurostat or BFS wrapped format).

    Returns (dim_names, {coord_tuple: value}).
    BFS wraps the dataset under {"dataset": {...}}; Eurostat is flat.
    """
    data = raw.get("dataset", raw)  # unwrap BFS envelope

    # BFS PXWEB nests "id" and "size" *inside* the "dimension" block.
    # Eurostat puts them at the top level of the dataset object.
    dim_block = data.get("dimension", {})
    dim_names: list[str] = (
        data.get("id")                                                        # Eurostat
        or dim_block.get("id")                                                # BFS
        or [k for k in dim_block if k not in ("id", "size", "role")]         # fallback
    )
    dim_sizes: list[int] = (
        data.get("size")                                                      # Eurostat
        or dim_block.get("size")                                              # BFS
        or [len(dim_block[d]["category"]["index"]) for d in dim_names]       # compute
    )

    # {position_index → code} for each dimension
    code_maps: list[dict[int, str]] = []
    for name in dim_names:
        cat = dim_block[name]["category"]["index"]
        code_maps.append({int(v): k for k, v in cat.items()})

    # Compute strides (last dim has stride 1, first dim has largest)
    strides: list[int] = [1] * len(dim_sizes)
    for i in range(len(dim_sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * dim_sizes[i + 1]

    raw_vals = data.get("value", {})
    if isinstance(raw_vals, list):
        value_map: dict[int, float] = {i: v for i, v in enumerate(raw_vals) if v is not None}
    else:
        value_map = {int(k): float(v) for k, v in raw_vals.items() if v is not None}

    result: dict[tuple[str, ...], float] = {}
    for flat_i, val in value_map.items():
        coords: list[str] = []
        remaining = flat_i
        for stride, code_map in zip(strides, code_maps):
            dim_pos = remaining // stride
            remaining %= stride
            coords.append(code_map.get(dim_pos, str(dim_pos)))
        result[tuple(coords)] = float(val)

    return dim_names, result


def _extract_geo_time(
    dim_names: list[str],
    parsed: dict[tuple[str, ...], float],
    filter_dims: dict[str, str],
) -> dict[str, dict[str, float]]:
    """Return {geo_code: {year: value}} applying filter_dims as equality constraints."""
    geo_idx = next((i for i, n in enumerate(dim_names) if n == "geo"), -1)
    time_idx = next((i for i, n in enumerate(dim_names) if n == "time"), -1)
    if geo_idx == -1 or time_idx == -1:
        return {}

    filter_idx = {
        i: v for i, (k, v) in zip(
            [dim_names.index(k) for k in filter_dims if k in dim_names],
            filter_dims.items(),
        )
        if k in dim_names
    }

    result: dict[str, dict[str, float]] = {}
    for coords, val in parsed.items():
        if not all(coords[i] == v for i, v in filter_idx.items()):
            continue
        geo = coords[geo_idx]
        year = coords[time_idx]
        result.setdefault(geo, {})[year] = val
    return result


# ── Eurostat fetchers ─────────────────────────────────────────────────────────

def fetch_eurostat_series(ds_cfg: dict) -> dict[str, dict[str, float]]:
    """Fetch a Eurostat dataset and return {country_code: {year: value}}.

    If ds_cfg has a ``compute_ratio`` key, the returned values are a computed
    percentage: (numerator_nace / denominator_nace) * 100 per country+year.
    """
    code = ds_cfg["code"]
    params = {"format": "JSON", "lang": "EN", **ds_cfg["params"]}
    url = f"{_EUROSTAT_BASE}/{code}?{urllib.parse.urlencode(params)}"
    print(f"  Fetching Eurostat {code} ...")
    raw_bytes = _http_get(url)
    time.sleep(_DELAY)
    if not raw_bytes:
        return {}
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
        dim_names, parsed = _parse_jsonstat(raw)

        ratio_cfg = ds_cfg.get("compute_ratio")
        if ratio_cfg:
            # Extract both numerator and denominator slices, then compute ratio.
            ratio_dim = ratio_cfg["dim"]
            num_filter = {**ds_cfg["filter_dims"], ratio_dim: ratio_cfg["numerator"]}
            den_filter = {**ds_cfg["filter_dims"], ratio_dim: ratio_cfg["denominator"]}
            num_series = _extract_geo_time(dim_names, parsed, num_filter)
            den_series = _extract_geo_time(dim_names, parsed, den_filter)
            series: dict[str, dict[str, float]] = {}
            for geo, years in num_series.items():
                for year, num_val in years.items():
                    den_val = den_series.get(geo, {}).get(year)
                    if den_val and den_val > 0:
                        series.setdefault(geo, {})[year] = round(num_val / den_val * 100, 2)
        else:
            series = _extract_geo_time(dim_names, parsed, ds_cfg["filter_dims"])

        country_count = sum(1 for k in series if k in _EU_COUNTRIES)
        print(f"    → {len(parsed):,} data points, {country_count} known EU/EEA countries")
        return series
    except Exception as exc:
        print(f"  WARN parse {code}: {exc}")
        return {}


# ── Eurostat SES fetchers (earn_ses_pub2n / earn_ses_pub2i) ──────────────────
# SES = Structure of Earnings Survey, conducted every 4 years.
# Both datasets report MEDIAN HOURLY earnings in EUR (enterprises with 10+ employees).
# Reference years: 2010, 2014, 2018, 2022.
# Multiply hourly rate × 1,700 h/yr for a full-time annual equivalent.
# HOURS_PER_YEAR is an approximation; actual annual wages depend on contracted hours.
_SES_HOURS_PER_YEAR = 1_700  # EU approximate full-time hours/year

# ISCED-11 education levels used in earn_ses_pub2i
_ISCED_LABELS: dict[str, str] = {
    "TOTAL": "All education levels",
    "ED0-2":  "Basic education (ISCED 0–2, no/lower secondary)",
    "ED3_4":  "Upper secondary / post-secondary non-tertiary (ISCED 3–4)",
    "ED5-8":  "Tertiary education — university degree or higher (ISCED 5–8)",
}


def _ses_fetch(dataset: str, dim_key: str, valid_codes: set[str]) -> dict[str, dict[str, float]]:
    """Generic SES fetcher: returns {country: {dim_key_code: median_hourly_eur}}.

    Filters to unit=EUR, sizeclas=GE10, keeps only the latest available year per cell.
    """
    params = {
        "format": "JSON", "lang": "EN",
        "unit": "EUR", "sizeclas": "GE10",
        "sinceTimePeriod": "2018",
    }
    url = f"{_EUROSTAT_BASE}/{dataset}?{urllib.parse.urlencode(params)}"
    print(f"  Fetching Eurostat {dataset} ...")
    raw_bytes = _http_get(url)
    time.sleep(_DELAY)
    if not raw_bytes:
        return {}
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
        dim_names, parsed = _parse_jsonstat(raw)

        geo_idx  = next((i for i, n in enumerate(dim_names) if n == "geo"),   -1)
        time_idx = next((i for i, n in enumerate(dim_names) if n == "time"),  -1)
        cat_idx  = next((i for i, n in enumerate(dim_names) if n == dim_key), -1)

        if geo_idx == -1 or cat_idx == -1 or time_idx == -1:
            print(f"  WARN {dataset}: expected dims not found in {dim_names}")
            return {}

        # Accumulate {country: {category_code: {year: hourly_eur}}}
        by_country: dict[str, dict[str, dict[str, float]]] = {}
        for coords, val in parsed.items():
            cat = coords[cat_idx]
            if valid_codes and cat not in valid_codes:
                continue
            geo  = coords[geo_idx]
            year = coords[time_idx]
            by_country.setdefault(geo, {}).setdefault(cat, {})[year] = val

        # Collapse to latest year per (country, category)
        result: dict[str, dict[str, float]] = {}
        for geo, cat_map in by_country.items():
            for cat, years in cat_map.items():
                if years:
                    result.setdefault(geo, {})[cat] = years[max(years)]

        country_count = sum(1 for k in result if k in _EU_COUNTRIES)
        print(f"    → {len(parsed):,} data points, {country_count} EU countries")
        return result
    except Exception as exc:
        print(f"  WARN {dataset} parse: {exc}")
        return {}


def fetch_eurostat_edu_wages() -> dict[str, dict[str, float]]:
    """Fetch earn_ses_pub2i — median hourly earnings by ISCED-11 education level (EUR).

    Returns {country_code: {isced_code: median_hourly_eur}}.
    Relevant ISCED codes: ED0-2, ED3_4, ED5-8, TOTAL.
    """
    return _ses_fetch("earn_ses_pub2i", "isced11", set(_ISCED_LABELS.keys()))


def fetch_eurostat_sector_wages() -> dict[str, dict[str, float]]:
    """Fetch earn_ses_pub2n — median hourly earnings by NACE Rev.2 sector (EUR).

    Returns {country_code: {nace_sector_code: median_hourly_eur}}.
    """
    return _ses_fetch("earn_ses_pub2n", "nace_r2", set(_NACE_SECTOR_LABELS.keys()))


# ── Swiss BFS PXWEB fetcher ───────────────────────────────────────────────────

def fetch_swiss_wages() -> dict[str, dict[str, dict[str, float]]]:
    """Fetch BFS monthly gross wages (CHF) by region × sector.

    Returns {region_code: {sector_code: {percentile_label: monthly_chf}}}.
    E.g., result["4"]["62"]["Median"] == 10500.0  (Zurich / IT / median)
    """
    # POST query: year=2024, all regions, key tech sectors, total level, total sex, median+P25+P75
    body = {
        "query": [
            {"code": "Jahr",
             "selection": {"filter": "item", "values": ["2024"]}},
            {"code": "Grossregion",
             "selection": {"filter": "all", "values": ["*"]}},
            {"code": "Wirtschaftsabteilung",
             "selection": {"filter": "item",
                           "values": ["-1", "62", "61", "64", "65", "72", "21", "71", "70", "84", "85", "86"]}},
            {"code": "Berufliche Stellung",
             "selection": {"filter": "item", "values": ["-1"]}},
            {"code": "Geschlecht",
             "selection": {"filter": "item", "values": ["-1"]}},
            {"code": "Zentralwert und andere Perzentile",
             "selection": {"filter": "item", "values": ["1", "3", "4"]}},
        ],
        "response": {"format": "JSON-stat"},
    }
    url = f"{_BFS_BASE}/{_BFS_DB}/{_BFS_TABLE}"
    print("  Fetching BFS monthly wages (2024) ...")
    raw_bytes = _http_post(url, body, timeout=30)
    time.sleep(_DELAY)
    if not raw_bytes:
        return {}

    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
        dim_names, parsed = _parse_jsonstat(raw)
    except Exception as exc:
        print(f"  WARN BFS parse: {exc}")
        return {}

    # Identify dimension positions
    region_idx  = next((i for i, n in enumerate(dim_names) if "grossregion" in n.lower()), -1)
    sector_idx  = next((i for i, n in enumerate(dim_names) if "wirtschaft" in n.lower()), -1)
    pct_idx     = next((i for i, n in enumerate(dim_names) if "zentralwert" in n.lower()), -1)
    if region_idx == -1 or sector_idx == -1 or pct_idx == -1:
        print(f"  WARN BFS dims not found in {dim_names}")
        return {}

    pct_label_map = {"1": "Median", "3": "P25", "4": "P75"}

    result: dict[str, dict[str, dict[str, float]]] = {}
    for coords, val in parsed.items():
        region  = coords[region_idx]
        sector  = coords[sector_idx]
        pct_key = coords[pct_idx]
        pct_lbl = pct_label_map.get(pct_key, pct_key)
        result.setdefault(region, {}).setdefault(sector, {})[pct_lbl] = val

    regions_found = len(result)
    print(f"    → {regions_found} regions × {len(next(iter(result.values()), {}))} sectors")
    return result


# ── Exchange rate fetcher ─────────────────────────────────────────────────────

def fetch_exchange_rates() -> dict[str, float]:
    """Fetch CHF → EUR and USD rates from frankfurter.app (no API key needed)."""
    url = f"{_FRANKFURTER_URL}?from=CHF&to=EUR,USD"
    print("  Fetching CHF exchange rates from frankfurter.app ...")
    raw = _http_get(url)
    time.sleep(_DELAY)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        rates = data.get("rates", {})
        eur = rates.get("EUR")
        usd = rates.get("USD")
        print(f"    1 CHF = EUR {eur}, USD {usd}")
        return {k: float(v) for k, v in rates.items() if v is not None}
    except Exception as exc:
        print(f"  WARN rates: {exc}")
        return {}


# ── Adzuna job fetcher ────────────────────────────────────────────────────────

def fetch_adzuna_country(
    country_code: str,
    app_id: str,
    app_key: str,
) -> dict[str, dict]:
    """Fetch live tech job counts + salary data from Adzuna for one EU country.

    Returns {role_label: {"count": int, "mean_salary": float | None}}.
    Salary is in local currency (EUR for most EU countries).
    """
    results: dict[str, dict] = {}
    for query, label in _ADZUNA_ALL_QUERIES:
        params = urllib.parse.urlencode({
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "results_per_page": 20,
            "content-type": "application/json",
        })
        url = f"{_ADZUNA_BASE}/{country_code}/search/1?{params}"
        raw = _http_get(url)
        time.sleep(_DELAY)
        if not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
            count = data.get("count", 0)
            # Compute mean from salary_max of jobs that disclose pay
            salary_values = [
                r["salary_max"]
                for r in data.get("results", [])
                if r.get("salary_max") and float(r["salary_max"]) > 5000
                and r.get("salary_is_predicted", "1") == "0"  # prefer disclosed salaries
            ]
            if not salary_values:
                # Fall back to all (including predicted) if no disclosed salaries
                salary_values = [
                    r["salary_max"]
                    for r in data.get("results", [])
                    if r.get("salary_max") and float(r["salary_max"]) > 5000
                ]
            mean_sal = round(sum(salary_values) / len(salary_values)) if salary_values else None
            results[label] = {"count": count, "mean_salary": mean_sal}
        except Exception as exc:
            print(f"    WARN Adzuna {country_code}/{query}: {exc}")
    return results


# ── Document builders ─────────────────────────────────────────────────────────

def _latest(series: dict[str, float]) -> tuple[str, float] | tuple[None, None]:
    """Return (latest_year, value) from a {year: value} dict, or (None, None)."""
    if not series:
        return None, None
    year = max(series)
    return year, series[year]


def build_eu_country_doc(
    country_code: str,
    hightech: dict[str, float],   # {year: pct}
    ict_ent: dict[str, float],    # {year: pct}
    earnings: dict[str, float],   # {year: eur_annual}
    doc_idx: int,
) -> dict | None:
    name, context = _EU_COUNTRIES.get(country_code, (country_code, ""))
    if not (hightech or ict_ent or earnings):
        return None

    ht_year, ht_val = _latest(hightech)
    ent_year, ent_val = _latest(ict_ent)
    earn_year, earn_val = _latest(earnings)

    lines: list[str] = []
    heading = f"{name} — ICT & Technology Labour Market"
    lines += [heading, "=" * len(heading), ""]

    if context:
        lines += [context, ""]

    lines += ["Key Statistics (Eurostat)", "─" * 26]
    if ht_val is not None:
        lines.append(f"High-tech employment:          {ht_val:.1f}% of total employment ({ht_year})")
    if ent_val is not None:
        lines.append(f"Enterprises with ICT staff:    {ent_val:.1f}% of all enterprises ({ent_year})")
    if earn_val is not None:
        lines.append(
            f"Gross annual earnings (avg):    EUR {int(earn_val):,} ({earn_year})  "
            f"[≈ EUR {int(earn_val / 12):,}/month]"
        )
    lines.append("")

    # Multi-year ICT trend
    if len(hightech) >= 2:
        years = sorted(hightech)
        oldest, newest = years[0], years[-1]
        delta = hightech[newest] - hightech[oldest]
        sign = "+" if delta >= 0 else ""
        lines += [
            "High-tech Employment Trend",
            "─" * 26,
            f"{oldest}: {hightech[oldest]:.1f}%  →  {newest}: {hightech[newest]:.1f}%  "
            f"({sign}{delta:.1f} pp)",
            "",
        ]

    region = "Switzerland" if country_code == "CH" else "EU"
    tags = [name.lower(), country_code.lower(), "ict", "high-tech", "employment", "eurostat"]
    if country_code in ("CH", "NO", "IS"):
        tags.append("efta")

    display_year = ht_year or ent_year or earn_year or "2024"
    return {
        "id": f"eu-ict-{country_code.lower()}-{doc_idx}",
        "title": f"{name} — ICT & Technology Labour Market {display_year}",
        "content": "\n".join(lines).strip(),
        "region": region,
        "sub_region": name,
        "published_at": f"{display_year}-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/htec_emp_nisced2",
        "tags": tags,
    }


def build_eu_ranking_doc(
    hightech: dict[str, dict[str, float]],
    earnings: dict[str, dict[str, float]],
) -> dict:
    """One pan-EU ranking overview document."""
    # Pick latest year with most data coverage
    all_years: dict[str, int] = {}
    for series in hightech.values():
        for y in series:
            all_years[y] = all_years.get(y, 0) + 1
    pivot_year = max(all_years, key=all_years.get) if all_years else "2024"

    ranked = [
        (code, series[pivot_year])
        for code, series in hightech.items()
        if code in _EU_COUNTRIES and pivot_year in series
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)

    lines: list[str] = []
    heading = f"European Union — High-Tech Employment Rankings {pivot_year}"
    lines += [heading, "=" * len(heading), ""]
    lines += [
        "High-tech sector employment as % of total employment (Eurostat htec_emp_nisced2).",
        "High-tech includes knowledge-intensive manufacturing AND high-tech services.",
        "",
        "Country Rankings",
        "─" * 16,
    ]
    for rank, (code, pct) in enumerate(ranked[:30], 1):
        name = _EU_COUNTRIES[code][0]
        lines.append(f"  {rank:>2}. {name:<22} {pct:.1f}%")

    lines += [""]

    # Earnings ranking
    earn_ranked = [
        (code, series.get(pivot_year) or series.get(max(series)))
        for code, series in earnings.items()
        if code in _EU_COUNTRIES
    ]
    earn_ranked = [(c, v) for c, v in earn_ranked if v is not None]
    earn_ranked.sort(key=lambda x: x[1], reverse=True)
    if earn_ranked:
        lines += [
            "Gross Annual Earnings at Average Wage (EUR, single person, 100% avg wage)",
            "─" * 72,
        ]
        for rank, (code, eur) in enumerate(earn_ranked[:20], 1):
            name = _EU_COUNTRIES[code][0]
            lines.append(f"  {rank:>2}. {name:<22} EUR {int(eur):>8,}")

    lines += [
        "",
        "Note: Swiss wages (CHF) are excluded from EUR rankings.",
        "Note: Earnings represent gross statutory wages before income tax and social contributions.",
        "Source: Eurostat htec_emp_nisced2, earn_nt_net.",
    ]

    latest_year = max(all_years) if all_years else "2024"
    return {
        "id": f"eu-rankings-overview-{latest_year}",
        "title": f"EU/EEA High-Tech Employment and Earnings Rankings {latest_year}",
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": "European Union",
        "published_at": f"{latest_year}-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/htec_emp_nisced2",
        "tags": ["eu", "rankings", "ict", "high-tech", "salaries", "employment", "eurostat"],
    }


def build_swiss_region_doc(
    region_code: str,
    wage_data: dict[str, dict[str, float]],  # {sector_code: {percentile: monthly_chf}}
    doc_idx: int,
    rates: dict[str, float] | None = None,   # CHF exchange rates from frankfurter.app
) -> dict:
    region_name, canton_list = _BFS_REGIONS[region_code]
    context = _REGION_CONTEXT.get(region_code, "")

    heading = f"Switzerland — {region_name}: Monthly Gross Wage Benchmarks 2024"
    lines: list[str] = [heading, "=" * len(heading), ""]

    if canton_list and canton_list != "CH total — all 26 cantons":
        lines += [f"Cantons: {canton_list}", ""]
    if context:
        lines += [context, ""]

    lines += [
        "Monthly Gross Wages (CHF, median) — BFS Wage Structure Survey 2024",
        "─" * 68,
        f"{'Sector':<40} {'Median':>8}  {'P25':>8}  {'P75':>8}",
        "─" * 68,
    ]

    # Display key sectors first, then remaining
    priority_order = ["-1", "62", "61", "64", "65", "72", "21", "71", "70", "84", "85", "86"]
    displayed_sectors = [s for s in priority_order if s in wage_data]
    for sector_code in displayed_sectors:
        pcts = wage_data[sector_code]
        median = pcts.get("Median")
        p25    = pcts.get("P25")
        p75    = pcts.get("P75")
        label  = _BFS_SECTORS.get(sector_code, sector_code)

        median_str = f"CHF {int(median):>6,}" if median else "  n/a    "
        p25_str    = f"CHF {int(p25):>6,}"    if p25    else "  n/a    "
        p75_str    = f"CHF {int(p75):>6,}"    if p75    else "  n/a    "
        lines.append(f"  {label:<38} {median_str}  {p25_str}  {p75_str}")

    lines += [
        "─" * 68,
        "Values are monthly gross wages in CHF (before AHV/IV/EO deductions).",
        "P25 = 25th percentile, P75 = 75th percentile.",
        "Source: Swiss Federal Statistical Office (BFS), px-x-0304010000_201.",
        "",
    ]

    # Annual equivalent for median
    total_sector = wage_data.get("-1", {})
    total_median = total_sector.get("Median")
    if total_median:
        annual = int(total_median * 12)
        lines += [
            "Annual Equivalent (median × 12)",
            "─" * 34,
            f"Overall median gross:   CHF {annual:>8,}/year",
        ]
        it_sector = wage_data.get("62", {})
        it_median = it_sector.get("Median")
        if it_median:
            it_annual = int(it_median * 12)
            lines.append(f"IT services median:     CHF {it_annual:>8,}/year")

        # EUR/USD equivalents using live frankfurter.app rates
        if rates:
            eur_rate = rates.get("EUR")
            usd_rate = rates.get("USD")
            lines += ["", "Approximate Equivalents (live rates, frankfurter.app)"]
            if eur_rate:
                lines.append(f"  Overall median:  EUR {int(annual * eur_rate):>8,}/year")
                if it_median:
                    lines.append(f"  IT services:     EUR {int(it_annual * eur_rate):>8,}/year")
            if usd_rate:
                lines.append(f"  Overall median:  USD {int(annual * usd_rate):>8,}/year")
                if it_median:
                    lines.append(f"  IT services:     USD {int(it_annual * usd_rate):>8,}/year")
            lines.append(f"  Exchange rate:   1 CHF = EUR {eur_rate:.4f} / USD {usd_rate:.4f}")

        lines += [
            "",
            "Net take-home is approximately 75–85% of gross, depending on canton and",
            "personal circumstances (AHV/IV ~5.3%, ALV ~1.1%, BVG pension varies).",
        ]

    tags = [
        region_name.lower().replace(" ", "-"), "switzerland", "swiss",
        "wages", "salary", "bfs", "lse", region_code,
    ]
    if region_code == "4":
        tags.append("zurich")
    elif region_code == "1":
        tags.extend(["geneva", "lausanne"])
    elif region_code == "3":
        tags.extend(["basel", "pharma"])
    elif region_code == "6":
        tags.append("zug")

    return {
        "id": f"swiss-wages-region-{region_code}-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Switzerland",
        "sub_region": region_name,
        "published_at": "2024-01-01",
        "source_url": "https://www.bfs.admin.ch/bfs/en/home/statistics/work-income/wages-income-employment-labour-costs.html",
        "tags": tags,
    }


def build_swiss_region_stub_doc(region_code: str, doc_idx: int) -> dict:
    """Fallback Swiss region doc when BFS API returns no data."""
    region_name, canton_list = _BFS_REGIONS[region_code]
    context = _REGION_CONTEXT.get(region_code, "")
    heading = f"Switzerland — {region_name}: Labour Market Overview"
    lines: list[str] = [heading, "=" * len(heading), ""]
    if canton_list:
        lines += [f"Cantons: {canton_list}", ""]
    if context:
        lines += [context, ""]
    lines += [
        "Swiss Labour Market Context",
        "─" * 26,
        "Switzerland is not an EU member but has bilateral free-movement agreements with the EU.",
        "",
        "EU/EFTA nationals: B permit (5-year renewable) or L permit (short-stay) on employment.",
        "Non-EU/EFTA: Employer-sponsored permit, quota-based, priority to EU candidates required.",
        "",
        "General salary benchmarks (gross, CHF, IT sector, Zurich reference):",
        "  Junior (0–2 yr):   CHF 85,000–110,000 /year",
        "  Mid-level (2–5 yr): CHF 110,000–145,000 /year",
        "  Senior (5+ yr):    CHF 145,000–200,000+ /year",
        "",
        "Net take-home ≈ 75–85% of gross. Major deductions: AHV/IV/EO (~5.3%), ALV (~1.1%),",
        "accident insurance (SUVA), and BVG occupational pension (employer-matched, varies).",
    ]
    return {
        "id": f"swiss-region-stub-{region_code}-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Switzerland",
        "sub_region": region_name,
        "published_at": "2024-01-01",
        "source_url": "https://www.bfs.admin.ch/bfs/en/home/statistics/work-income.html",
        "tags": [region_name.lower().replace(" ", "-"), "switzerland", "wages", "labour-market"],
    }


def build_adzuna_country_doc(
    country_code: str,
    country_name: str,
    job_data: dict[str, dict],
    doc_idx: int,
) -> dict | None:
    """Build a live job market doc (tech + non-tech) from Adzuna data for one EU country."""
    if not job_data:
        return None

    tech_labels   = {label for _, label in _ADZUNA_TECH_QUERIES}
    nontech_labels = {label for _, label in _ADZUNA_NON_TECH_QUERIES}

    tech_data    = {k: v for k, v in job_data.items() if k in tech_labels}
    nontech_data = {k: v for k, v in job_data.items() if k in nontech_labels}

    total_jobs = sum(v.get("count", 0) for v in job_data.values())
    heading = f"{country_name} — Live Job Market (Tech & Non-Tech) 2025"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        f"Total advertised positions tracked: {total_jobs:,}",
        "Source: Adzuna job board aggregate (live data, 2025)",
        "",
    ]

    def _role_table(section_title: str, data: dict[str, dict]) -> None:
        if not data:
            return
        lines.append(section_title)
        lines.append("─" * 72)
        lines.append(f"  {'Role Category':<33} {'Open Jobs':>10}   Advertised Salary (mean)")
        lines.append("  " + "─" * 60)
        for role, stats in data.items():
            count   = stats.get("count", 0)
            mean_sal = stats.get("mean_salary")
            sal_str  = f"≈ {int(mean_sal):>8,} EUR/yr" if mean_sal else "not disclosed"
            lines.append(f"  {role:<33} {count:>10,}   {sal_str}")
        lines.append("")

    _role_table("Technology & Engineering Roles", tech_data)
    _role_table("Business, Finance & Product Roles", nontech_data)

    lines += [
        "Notes:",
        "• Counts are live advertised positions at time of data collection.",
        "• Salary = mean advertised figure from listings that disclose pay (EUR).",
        "• Non-disclosure is common, especially for senior and managerial roles.",
    ]

    _, context = _EU_COUNTRIES.get(country_code.upper(), ("", ""))
    if context:
        lines += ["", "Regional Ecosystem Context", "─" * 26, context]

    return {
        "id": f"adzuna-jobs-{country_code}-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": country_name,
        "published_at": "2025-01-01",
        "source_url": f"https://www.adzuna.com/{country_code}/search",
        "tags": [country_name.lower(), "jobs", "tech", "non-tech", "live-data",
                 "adzuna", "2025", country_code.lower(),
                 "product-management", "finance", "marketing"],
    }


def build_eu_education_salary_doc(
    edu_wages: dict[str, dict[str, float]],  # {country: {isced_code: median_hourly_eur}}
) -> dict | None:
    """Build a pan-EU salary-by-education-level document.

    Shows median hourly and estimated annual earnings for university-educated vs secondary
    workers. Acts as a proxy for professional/managerial vs technical/clerical occupation tiers.
    """
    eu_data = {k: v for k, v in edu_wages.items() if k in _EU_COUNTRIES}
    if not eu_data:
        return None

    heading = "European Union — Earnings by Education Level & Career Stage (SES 2022)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        "Median hourly earnings (EUR) by ISCED-11 education level, enterprises with 10+ employees.",
        "Source: Eurostat Structure of Earnings Survey, earn_ses_pub2i (2022 reference year).",
        "Annual estimate = median hourly rate × 1,700 h/yr (EU full-time approximation).",
        "Education level is a strong proxy for career tier: university → professional/managerial roles.",
        "",
    ]

    # Pan-EU averages by education level
    edu_eu_vals: dict[str, list[float]] = {}
    for country_data in eu_data.values():
        for isced, hourly in country_data.items():
            edu_eu_vals.setdefault(isced, []).append(hourly)

    eu_hourly_avg = {k: sum(v) / len(v) for k, v in edu_eu_vals.items() if v}

    level_order = ["ED5-8", "ED3_4", "ED0-2", "TOTAL"]
    lines += [
        "Pan-EU Average Earnings by Education Level (all countries with SES data)",
        "─" * 76,
        f"  {'Education Level':<40} {'Hourly (EUR)':>12}  {'Annual Est. (EUR)':>18}  {'# Countries':>12}",
        "  " + "─" * 88,
    ]
    for isced in level_order:
        if isced not in eu_hourly_avg:
            continue
        label  = _ISCED_LABELS.get(isced, isced)
        hourly = eu_hourly_avg[isced]
        annual = int(hourly * _SES_HOURS_PER_YEAR)
        n_ctry = len(edu_eu_vals.get(isced, []))
        lines.append(
            f"  {label:<40} {hourly:>10.2f} EUR/hr  EUR {annual:>10,}/yr  {n_ctry:>12} countries"
        )
    lines += [""]

    # Tertiary (ED5-8) country ranking — best proxy for professional/managerial wages
    tertiary_data = [(cc, d["ED5-8"]) for cc, d in eu_data.items() if "ED5-8" in d]
    tertiary_data.sort(key=lambda x: x[1], reverse=True)
    if tertiary_data:
        lines += [
            "Tertiary-Educated Workers (ISCED 5–8) Hourly Earnings — Country Ranking",
            "─" * 68,
            "  University graduates: engineers, scientists, analysts, managers, consultants.",
            "",
            f"  {'Country':<26} {'EUR/hr':>8}  {'Annual Est. (EUR)':>18}",
            "  " + "─" * 56,
        ]
        for rank, (cc, hourly) in enumerate(tertiary_data[:20], 1):
            name = _EU_COUNTRIES[cc][0]
            annual = int(hourly * _SES_HOURS_PER_YEAR)
            lines.append(f"  {rank:>2}. {name:<24} {hourly:>6.2f} EUR/hr  EUR {annual:>10,}/yr")
        lines += [""]

    # Education wage premium (tertiary vs total) per country
    premium_data = [
        (cc, d.get("ED5-8", 0) / d.get("TOTAL", 1) if d.get("TOTAL") else 0)
        for cc, d in eu_data.items()
        if "ED5-8" in d and "TOTAL" in d
    ]
    premium_data.sort(key=lambda x: x[1], reverse=True)
    if premium_data:
        lines += [
            "Tertiary Education Premium (hourly earnings ratio: tertiary / all employees)",
            "─" * 68,
            "  Higher ratio = stronger return on university education in that labour market.",
            "",
        ]
        for rank, (cc, ratio) in enumerate(premium_data[:15], 1):
            name = _EU_COUNTRIES[cc][0]
            lines.append(f"  {rank:>2}. {name:<24} {ratio:.2f}×  (tertiary earns {ratio:.0%} of the median)")
        lines += [""]

    lines += [
        "Notes:",
        "• 'Tertiary' (ISCED 5–8) covers bachelor's, master's, PhD and equivalent professional qualifications.",
        "• Median hourly earnings include both full-time and part-time workers; annual estimate assumes full-time.",
        "• Annual estimate (hourly × 1,700 h/yr) is an approximation; actual contracted hours vary by country.",
        "• SES covers enterprises with 10+ employees in industry, construction and services (excl. agriculture).",
        "• Data excludes apprentices. Reference year: 2022 (SES conducted every 4 years).",
        "Source: Eurostat earn_ses_pub2i — Structure of Earnings Survey.",
    ]

    return {
        "id": "eu-education-salary-isced",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": "European Union",
        "published_at": "2025-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/earn_ses_pub2i",
        "tags": ["eu", "salary", "education", "isced", "earnings", "university",
                 "professionals", "managers", "career-stage", "non-tech", "eurostat", "ses"],
    }


def build_eu_sector_salary_doc(
    sector_wages: dict[str, dict[str, float]],  # {country: {nace_sector: median_hourly_eur}}
) -> dict | None:
    """Build a pan-EU NACE sector salary comparison document (covers finance, pharma, consulting).

    Input values are median hourly EUR from earn_ses_pub2n.
    Annual estimate = hourly × 1,700 h/yr.
    """
    eu_data = {k: v for k, v in sector_wages.items() if k in _EU_COUNTRIES}
    if not eu_data:
        return None

    heading = "European Union — Earnings by Industry Sector (NACE Rev.2, SES 2022)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        "Median hourly earnings (EUR) by NACE Rev.2 sector, enterprises with 10+ employees.",
        "Source: Eurostat Structure of Earnings Survey, earn_ses_pub2n (2022 reference year).",
        "Annual estimate = median hourly rate × 1,700 h/yr (EU full-time approximation).",
        "Sectors: ICT (J), Finance (K), Consulting/R&D (M), Pharma-Mfg (C), Health (Q), Education (P).",
        "",
    ]

    # Pan-EU averages per sector
    sector_eu_vals: dict[str, list[float]] = {}
    for country_data in eu_data.values():
        for nace, hourly in country_data.items():
            sector_eu_vals.setdefault(nace, []).append(hourly)

    eu_hourly_avg = {k: sum(v) / len(v) for k, v in sector_eu_vals.items() if v}
    sorted_sectors = sorted(eu_hourly_avg.items(), key=lambda x: x[1], reverse=True)

    lines += [
        "Pan-EU Average Earnings by Sector (all countries with SES data, 2022)",
        "─" * 80,
        f"  {'Sector':<45} {'Hourly (EUR)':>12}  {'Annual Est. (EUR)':>18}  {'# Countries':>12}",
        "  " + "─" * 90,
    ]
    for nace, hourly in sorted_sectors:
        label  = _NACE_SECTOR_LABELS.get(nace, nace)
        annual = int(hourly * _SES_HOURS_PER_YEAR)
        n_ctry = len(sector_eu_vals.get(nace, []))
        lines.append(
            f"  {label:<45} {hourly:>10.2f} EUR/hr  EUR {annual:>10,}/yr  {n_ctry:>12} countries"
        )
    lines += [""]

    # Country rankings for key career-relevant sectors
    key_sectors = [
        ("K", "Finance & Insurance"),
        ("J", "Information & Communication (ICT)"),
        ("M", "Professional, Scientific & Technical"),
        ("C", "Manufacturing (incl. Pharma)"),
        ("Q", "Human Health & Social Work"),
    ]
    for nace_code, nace_label in key_sectors:
        sector_data = [(cc, d[nace_code]) for cc, d in eu_data.items() if nace_code in d]
        sector_data.sort(key=lambda x: x[1], reverse=True)
        if sector_data:
            lines += [
                f"NACE {nace_code} — {nace_label}: Country Rankings",
                "─" * 70,
                f"  {'Country':<26} {'EUR/hr':>8}  {'Annual Est. (EUR)':>18}",
                "  " + "─" * 56,
            ]
            for rank, (cc, hourly) in enumerate(sector_data[:15], 1):
                name   = _EU_COUNTRIES[cc][0]
                annual = int(hourly * _SES_HOURS_PER_YEAR)
                lines.append(f"  {rank:>2}. {name:<24} {hourly:>6.2f} EUR/hr  EUR {annual:>10,}/yr")
            lines += [""]

    lines += [
        "Notes:",
        "• Median hourly earnings include full-time and part-time workers. Annual figures are estimates.",
        "• Annual estimate (hourly × 1,700 h/yr) is an approximation for a full-time worker.",
        "• NACE J = Information & Communication: software, telecom, IT services, data centres.",
        "• NACE K = Finance & Insurance: banking, investment management, insurance, pension funds.",
        "• NACE M = Professional, Scientific & Technical: consulting, engineering, R&D, law, accounting.",
        "• NACE C21 (pharmaceutical mfg) earns significantly more than the NACE C manufacturing average.",
        "• Sector median blends all occupations; ICT/finance specialists earn well above these medians.",
        "• Reference year 2022; SES is conducted every 4 years.",
        "Source: Eurostat earn_ses_pub2n — Structure of Earnings Survey.",
    ]

    return {
        "id": "eu-sector-salary-nace",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": "European Union",
        "published_at": "2025-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/earn_ses_pub2n",
        "tags": ["eu", "salary", "sector", "nace", "industry", "earnings",
                 "finance", "ict", "consulting", "pharma", "healthcare", "non-tech", "eurostat", "ses"],
    }


# ── ISCO occupation wage fetcher ─────────────────────────────────────────────

def fetch_eurostat_isco_wages() -> dict[str, dict[str, float]]:
    """Try Eurostat SES datasets for ISCO-08 occupation group median hourly earnings.

    Tries earn_ses_pub3a then earn_ses_pub3b with the ``isco08`` dimension.
    Returns {country_code: {isco_code: median_hourly_eur}} or {} if inaccessible.
    """
    for ds_code in ("earn_ses_pub3a", "earn_ses_pub3b"):
        result = _ses_fetch(ds_code, "isco08", set(_ISCO_MAJOR_GROUPS.keys()))
        if result:
            n = sum(1 for k in result if k in _EU_COUNTRIES)
            print(f"    ISCO wages: {ds_code} → {n} EU countries")
            return result
    print("  INFO: ISCO occupation wage datasets not accessible — triangulation only")
    return {}


# ── Role salary triangulation ─────────────────────────────────────────────────

def _estimate_role_annual_salary(
    role: str,
    country_sector: dict[str, float],  # {nace_code: median_hourly_eur}
    country_edu: dict[str, float],      # {isced_code: median_hourly_eur}
    country_isco: dict[str, float],     # {isco_code: median_hourly_eur}
) -> tuple[int | None, int | None, int | None, float]:
    """Triangulate gross annual salary estimate for a non-tech role in one country.

    Algorithm:
      1. Blend primary (70%) + secondary (30%) NACE sector medians as base.
      2. Apply BLS-derived occupation-to-sector ratio (relative adjustment).
      3. Scale by ISCED tertiary education premium (60% weight, role requires degree).
      4. Blend in ISCO occupation group data at 40% weight when available.

    Returns (mid_annual_eur, entry_annual_eur, senior_annual_eur, confidence).
    Confidence: 0.40 = sector only; +0.15 = ISCED available; +0.20 = ISCO available.
    """
    profile = _NONTECH_ROLE_PROFILES.get(role)
    if not profile:
        return None, None, None, 0.0

    primary_h = country_sector.get(profile["primary_nace"])
    secondary_h = country_sector.get(profile.get("secondary_nace", ""))

    if not primary_h and not secondary_h:
        return None, None, None, 0.0

    base_h: float = (
        primary_h * 0.7 + secondary_h * 0.3
        if (primary_h and secondary_h)
        else primary_h or secondary_h  # type: ignore[assignment]
    )

    role_h = base_h * profile["bls_sector_ratio"]
    confidence = 0.40

    # Tertiary education premium adjustment (university degree required for all roles)
    total_edu = country_edu.get("TOTAL")
    tertiary_edu = country_edu.get("ED5-8")
    if total_edu and tertiary_edu and total_edu > 0:
        edu_premium = tertiary_edu / total_edu
        role_h *= 1.0 + (edu_premium - 1.0) * 0.60
        confidence += 0.15

    # ISCO occupation group blend (40% weight when available)
    isco_grp_h = country_isco.get(profile["isco_group"])
    isco_total_h = country_isco.get("TOTAL")
    if isco_grp_h and isco_total_h and isco_total_h > 0:
        isco_adjusted_h = base_h * (isco_grp_h / isco_total_h) * profile["bls_sector_ratio"]
        role_h = role_h * 0.60 + isco_adjusted_h * 0.40
        confidence += 0.20

    mid_eur    = int(role_h * _SES_HOURS_PER_YEAR)
    entry_eur  = int(mid_eur * profile["entry_factor"])
    senior_eur = int(mid_eur * profile["senior_factor"])

    return mid_eur, entry_eur, senior_eur, min(confidence, 0.80)


# ── Non-tech role document builders ──────────────────────────────────────────

def build_eu_isco_occupation_doc(
    isco_wages: dict[str, dict[str, float]],  # {country: {isco_code: median_hourly_eur}}
) -> dict | None:
    """Pan-EU ISCO-08 occupation group salary document from earn_ses_pub3a."""
    eu_data = {k: v for k, v in isco_wages.items() if k in _EU_COUNTRIES}
    if not eu_data:
        return None

    heading = "European Union — Earnings by Occupation Group (ISCO-08, SES 2022)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        "Median hourly earnings (EUR) by ISCO-08 major occupation group.",
        "Source: Eurostat Structure of Earnings Survey, earn_ses_pub3a (2022 reference year).",
        "Annual estimate = median hourly × 1,700 h/yr (EU full-time approximation).",
        "Covers enterprises with 10+ employees in industry, construction and services.",
        "",
    ]

    # Pan-EU averages
    isco_eu: dict[str, list[float]] = {}
    for cd in eu_data.values():
        for oc, h in cd.items():
            isco_eu.setdefault(oc, []).append(h)

    eu_avg = {k: sum(v) / len(v) for k, v in isco_eu.items() if v and k != "TOTAL"}
    sorted_oc = sorted(eu_avg.items(), key=lambda x: x[1], reverse=True)

    lines += [
        "Pan-EU Average Hourly Earnings by ISCO Occupation Group",
        "─" * 84,
        f"  {'Occupation Group':<45} {'EUR/hr':>8}  {'Annual Est. (EUR)':>18}  {'Countries':>10}",
        "  " + "─" * 88,
    ]
    for oc, h in sorted_oc:
        label  = _ISCO_MAJOR_GROUPS.get(oc, oc)
        annual = int(h * _SES_HOURS_PER_YEAR)
        n      = len(isco_eu.get(oc, []))
        lines.append(f"  {label:<45} {h:>6.2f} EUR/hr  EUR {annual:>10,}/yr  {n:>10}")
    lines += [""]

    # Country rankings for Managers and Professionals (most career-relevant groups)
    for oc_code, oc_label in [("OC1", "Managers"), ("OC2", "Professionals")]:
        country_data = [(cc, d[oc_code]) for cc, d in eu_data.items() if oc_code in d]
        country_data.sort(key=lambda x: x[1], reverse=True)
        if country_data:
            lines += [
                f"ISCO {oc_code} — {oc_label}: Country Rankings",
                "─" * 68,
                f"  {'Country':<26} {'EUR/hr':>8}  {'Annual Est. (EUR)':>18}",
                "  " + "─" * 56,
            ]
            for rank, (cc, h) in enumerate(country_data[:15], 1):
                name   = _EU_COUNTRIES[cc][0]
                annual = int(h * _SES_HOURS_PER_YEAR)
                lines.append(f"  {rank:>2}. {name:<24} {h:>6.2f} EUR/hr  EUR {annual:>10,}/yr")
            lines += [""]

    lines += [
        "Notes:",
        "• ISCO OC1 (Managers): CEOs, general managers, functional directors, department heads.",
        "• ISCO OC2 (Professionals): engineers, scientists, analysts, accountants, lawyers, consultants.",
        "• ISCO OC3 (Technicians): lab technicians, IT support, junior analysts, supervisors.",
        "• Cross-sector medians blend all industries; ICT/finance specialists earn above these figures.",
        "• Reference year 2022. SES conducted every 4 years.",
        "Source: Eurostat earn_ses_pub3a — Structure of Earnings Survey.",
    ]

    return {
        "id": "eu-isco-occupation-wages",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": "European Union",
        "published_at": "2025-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/earn_ses_pub3a",
        "tags": [
            "eu", "salary", "occupation", "isco", "managers", "professionals",
            "career", "earnings", "eurostat", "ses",
        ],
    }


def build_eu_nontech_role_overview_doc(
    sector_wages: dict[str, dict[str, float]],
    edu_wages: dict[str, dict[str, float]],
    isco_wages: dict[str, dict[str, float]],
) -> dict:
    """Pan-EU estimated salary ranges for seven key non-tech professional roles.

    Triangulated from Eurostat NACE sector medians, ISCED education premiums,
    ISCO occupation group data, and US BLS OES 2024 sector ratios.
    """
    role_estimates: dict[str, dict] = {}
    countries_used: set[str] = set()

    for role in _NONTECH_ROLE_PROFILES:
        mids: list[int] = []
        entries: list[int] = []
        seniors: list[int] = []
        for cc in _EU_COUNTRIES:
            mid, entry, senior, conf = _estimate_role_annual_salary(
                role,
                sector_wages.get(cc, {}),
                edu_wages.get(cc, {}),
                isco_wages.get(cc, {}),
            )
            if mid:
                mids.append(mid)
                entries.append(entry)  # type: ignore[arg-type]
                seniors.append(senior)  # type: ignore[arg-type]
                countries_used.add(cc)
        if mids:
            role_estimates[role] = {
                "mid_avg":    int(sum(mids)    / len(mids)),
                "entry_avg":  int(sum(entries) / len(entries)),
                "senior_avg": int(sum(seniors) / len(seniors)),
                "n_countries": len(mids),
            }

    heading = "European Union — Non-Tech Role Salary Estimates (2022–2025)"
    lines: list[str] = [heading, "=" * len(heading), ""]
    lines += [
        "Estimated gross annual salaries (EUR) for key non-tech professional roles across the EU.",
        "Methodology: triangulated from Eurostat SES sector wages (NACE Rev.2), education",
        "premiums (ISCED-11), ISCO-08 occupation group data, and US BLS OES 2024 sector ratios.",
        "Mid-level = 3–8 years experience in enterprises with 10+ employees.",
        f"Coverage: {len(countries_used)} EU/EEA countries with Eurostat SES data.",
        "",
    ]

    lines += [
        "EU Average Salary Estimates (averages across all covered countries)",
        "─" * 92,
        f"  {'Role':<26} {'Entry (EUR/yr)':>16}  {'Mid-Level (EUR/yr)':>20}  {'Senior (EUR/yr)':>16}",
        "  " + "─" * 84,
    ]
    for role, est in sorted(role_estimates.items(), key=lambda x: x[1]["mid_avg"], reverse=True):
        entry  = est["entry_avg"]
        mid    = est["mid_avg"]
        senior = est["senior_avg"]
        lines.append(
            f"  {role:<26} EUR {entry:>8,}/yr       EUR {mid:>8,}/yr       EUR {senior:>8,}/yr"
        )
    lines += ["", "Note: Wide variance between countries — see per-country role cards for specifics.", ""]

    lines += ["Role Descriptions and Primary Industry Sectors", "─" * 60, ""]
    for role, profile in _NONTECH_ROLE_PROFILES.items():
        nace_label = _NACE_SECTOR_LABELS.get(profile["primary_nace"], profile["primary_nace"])
        lines.append(f"• {role}")
        lines.append(f"  {profile['description']}")
        lines.append(f"  Primary sector: NACE {profile['primary_nace']} ({nace_label})")
        lines += [""]

    lines += [
        "Estimation Methodology",
        "─" * 52,
        "1. NACE base: 70% primary + 30% secondary sector median hourly rate (Eurostat earn_ses_pub2n).",
        "2. Role adjustment: × BLS sector ratio (US BLS OES 2024 occupation median / sector median).",
        "3. Education premium: × (1 + (ISCED5-8/TOTAL − 1) × 0.60) — all roles require university degree.",
        "4. ISCO blend: when occupation group data (earn_ses_pub3a) available, blended at 40% weight.",
        "5. Annualised: hourly estimate × 1,700 h/yr (EU full-time approximation).",
        "",
        "Confidence levels (per-country cards):",
        "  High = NACE + ISCED + ISCO data     (±15% typical range)",
        "  Medium-High = NACE + ISCED           (±20% typical range)",
        "  Medium = NACE only                  (±30% typical range)",
        "",
        "These are statistical estimates, not market survey data. For live advertised salaries",
        "use Adzuna, LinkedIn Salary Insights, or Glassdoor for the specific country.",
        "",
        "Sources: Eurostat earn_ses_pub2n, earn_ses_pub2i, earn_ses_pub3a; US BLS OES 2024.",
    ]

    return {
        "id": "eu-nontech-role-estimates",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": "European Union",
        "published_at": "2025-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/earn_ses_pub2n",
        "tags": [
            "eu", "salary", "non-tech", "estimates",
            "product-manager", "financial-analyst", "business-analyst",
            "ux-designer", "marketing-manager", "project-manager", "data-analyst",
            "career", "professionals", "eurostat", "ses",
        ],
    }


def build_eu_country_role_card(
    country_code: str,
    sector_wages: dict[str, dict[str, float]],
    edu_wages: dict[str, dict[str, float]],
    isco_wages: dict[str, dict[str, float]],
    doc_idx: int,
) -> dict | None:
    """Per-country non-tech role salary card for a top EU market."""
    country_sector = sector_wages.get(country_code, {})
    country_edu    = edu_wages.get(country_code, {})
    country_isco   = isco_wages.get(country_code, {})

    # Need at least sector or education data to produce an estimate
    if not country_sector and not country_edu:
        return None

    name, context = _EU_COUNTRIES.get(country_code, (country_code, ""))
    heading = f"{name} — Non-Tech Role Salary Estimates 2022–2025"
    lines: list[str] = [heading, "=" * len(heading), ""]
    if context:
        lines += [context, ""]

    lines += [
        "Estimated gross annual salaries (EUR) for key non-tech professional roles.",
        "Triangulated from Eurostat SES sector wages, education premiums, and occupation data.",
        "Mid-level = 3–8 years experience. All figures gross before tax.",
        "",
        "Role Salary Estimates",
        "─" * 84,
        f"  {'Role':<26} {'Entry':>14}  {'Mid-Level':>14}  {'Senior':>14}  {'Confidence':>12}",
        "  " + "─" * 80,
    ]

    _conf_label = [(0.75, "High"), (0.60, "Medium-High"), (0.50, "Medium"), (0.0, "Low")]

    has_any = False
    for role in _NONTECH_ROLE_PROFILES:
        mid, entry, senior, conf = _estimate_role_annual_salary(
            role, country_sector, country_edu, country_isco
        )
        if mid is None:
            continue
        has_any = True
        label = next(lbl for threshold, lbl in _conf_label if conf >= threshold)
        lines.append(
            f"  {role:<26} EUR {entry:>6,}/yr  EUR {mid:>6,}/yr  EUR {senior:>6,}/yr  {label:>12}"
        )

    if not has_any:
        return None

    lines += ["", "─" * 84, ""]

    # Underlying sector data context
    shown_sector = False
    for nace in ("J", "K", "M", "G"):
        h = country_sector.get(nace)
        if not h:
            continue
        if not shown_sector:
            lines += ["Underlying Sector Median Hourly Wages (Eurostat SES 2022)", "─" * 60]
            shown_sector = True
        label = _NACE_SECTOR_LABELS.get(nace, nace)
        annual = int(h * _SES_HOURS_PER_YEAR)
        lines.append(f"  NACE {nace} — {label:<40} {h:>5.2f} EUR/hr  ≈ EUR {annual:,}/yr")

    # Education premium summary
    total_edu = country_edu.get("TOTAL")
    tertiary_edu = country_edu.get("ED5-8")
    if total_edu and tertiary_edu and total_edu > 0:
        premium = tertiary_edu / total_edu
        lines += [
            "",
            "Education Premium (Eurostat earn_ses_pub2i, 2022)",
            "─" * 50,
            f"  University graduates earn {premium:.2f}× the all-worker median hourly rate.",
            f"  ISCED 5–8 median: {tertiary_edu:.2f} EUR/hr  |  All workers: {total_edu:.2f} EUR/hr",
        ]

    # ISCO occupation group context (if available)
    if country_isco:
        oc1_h = country_isco.get("OC1")
        oc2_h = country_isco.get("OC2")
        if oc1_h or oc2_h:
            lines += [
                "",
                "Occupation Group Wages (Eurostat earn_ses_pub3a, 2022)",
                "─" * 52,
            ]
            if oc1_h:
                lines.append(
                    f"  Managers (ISCO OC1):       {oc1_h:.2f} EUR/hr  ≈ EUR {int(oc1_h * _SES_HOURS_PER_YEAR):,}/yr"
                )
            if oc2_h:
                lines.append(
                    f"  Professionals (ISCO OC2):  {oc2_h:.2f} EUR/hr  ≈ EUR {int(oc2_h * _SES_HOURS_PER_YEAR):,}/yr"
                )

    lines += [
        "",
        "Notes:",
        "• Entry = 0–2 yrs experience; Mid-Level = 3–8 yrs; Senior = 8+ yrs or managerial.",
        "• Confidence: High = NACE + ISCED + ISCO (±15%); Medium = fewer data sources (±25–30%).",
        "• Gross annual EUR. Tax burden varies: ~25–45% effective rate depending on country & income.",
        "• For current live salaries check Adzuna, LinkedIn Salary Insights, or Glassdoor.",
        "Sources: Eurostat earn_ses_pub2n, earn_ses_pub2i, earn_ses_pub3a; US BLS OES 2024.",
    ]

    return {
        "id": f"eu-country-roles-{country_code.lower()}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "EU",
        "sub_region": name,
        "published_at": "2025-01-01",
        "source_url": "https://ec.europa.eu/eurostat/databrowser/view/earn_ses_pub2n",
        "tags": [
            name.lower(), country_code.lower(), "non-tech", "salary", "estimates",
            "product-manager", "financial-analyst", "business-analyst",
            "ux-designer", "marketing-manager", "project-manager", "data-analyst",
            "career", "professionals", "eurostat",
        ],
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def fetch_swiss_eu_market(
    output_dir: str,
    dry_run: bool = False,
    skip_adzuna: bool = False,
) -> list[dict]:
    """Fetch all EU and Swiss market data and assemble documents."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "swiss_eu_market_real.json"

    # ── 1. Eurostat general (high-tech employment + earnings) ────────────────
    print("\n[1/5] Fetching Eurostat general datasets ...")
    hightech_by_country: dict[str, dict[str, float]] = {}
    ict_ent_by_country:  dict[str, dict[str, float]] = {}
    earnings_by_country: dict[str, dict[str, float]] = {}

    for ds in _EUROSTAT_DATASETS:
        series = fetch_eurostat_series(ds)
        if ds["code"] == "htec_emp_nisced2":
            hightech_by_country = series
        elif ds["code"] == "isoc_ske_ittn2":
            ict_ent_by_country = series
        elif ds["code"] == "earn_nt_net":
            earnings_by_country = series

    ht_countries = sum(1 for c in hightech_by_country if c in _EU_COUNTRIES)
    print(f"  Eurostat: {ht_countries} countries with high-tech employment data")

    # ── 2. Eurostat SES — wages by education level + NACE sector + ISCO ────────
    print("\n[2/5] Fetching Eurostat SES non-tech salary data ...")
    edu_wages:    dict[str, dict[str, float]] = fetch_eurostat_edu_wages()
    sector_wages: dict[str, dict[str, float]] = fetch_eurostat_sector_wages()
    isco_wages:   dict[str, dict[str, float]] = fetch_eurostat_isco_wages()

    ses_countries = sum(1 for c in edu_wages if c in _EU_COUNTRIES)
    print(f"  SES: {ses_countries} EU countries with education-level wage data")
    if isco_wages:
        isco_countries = sum(1 for c in isco_wages if c in _EU_COUNTRIES)
        print(f"  ISCO: {isco_countries} EU countries with occupation group wage data")

    # ── 3. Swiss BFS ─────────────────────────────────────────────────────────
    print("\n[3/5] Fetching Swiss BFS wage data ...")
    swiss_wages = fetch_swiss_wages()

    # ── 4. Exchange rates (frankfurter.app, no key needed) ───────────────────
    print("\n[4/5] Fetching exchange rates ...")
    rates = fetch_exchange_rates()

    # ── 5. Adzuna EU job market data ──────────────────────────────────────────
    adzuna_app_id = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key = os.getenv("ADZUNA_APP_KEY", "")
    adzuna_data: dict[str, dict[str, dict]] = {}

    if skip_adzuna:
        print("\n[5/5] Adzuna skipped (--skip-adzuna flag).")
    elif not adzuna_app_id or not adzuna_app_key:
        print(
            "\n[5/5] Adzuna skipped — ADZUNA_APP_ID / ADZUNA_APP_KEY not set.\n"
            "      Register free at https://developer.adzuna.com/ and add to apps/api/.env"
        )
    else:
        print(f"\n[5/5] Fetching Adzuna job data for {len(_ADZUNA_EU_COUNTRIES)} EU countries ...")
        for cc, cname in _ADZUNA_EU_COUNTRIES.items():
            print(f"  {cname} ...")
            adzuna_data[cc] = fetch_adzuna_country(cc, adzuna_app_id, adzuna_app_key)
            jobs_found = sum(v.get("count", 0) for v in adzuna_data[cc].values())
            print(f"    → {jobs_found:,} total jobs found")

    # ── Assemble documents ────────────────────────────────────────────────────
    print("\nAssembling documents ...")
    docs: list[dict] = []

    # EU/EEA country documents (Eurostat high-tech employment + general earnings)
    for idx, country_code in enumerate(sorted(_EU_COUNTRIES)):
        doc = build_eu_country_doc(
            country_code=country_code,
            hightech=hightech_by_country.get(country_code, {}),
            ict_ent=ict_ent_by_country.get(country_code, {}),
            earnings=earnings_by_country.get(country_code, {}),
            doc_idx=idx + 1,
        )
        if doc:
            docs.append(doc)
            print(f"  EU doc: {doc['title'][:70]}")

    # EU ranking overview
    if hightech_by_country:
        docs.append(build_eu_ranking_doc(hightech_by_country, earnings_by_country))
        print("  EU ranking overview added")

    # EU education-level salary doc (tertiary vs secondary vs basic — career stage proxy)
    edu_doc = build_eu_education_salary_doc(edu_wages)
    if edu_doc:
        docs.append(edu_doc)
        print(f"  Education salary doc added ({len(edu_wages)} countries)")

    # EU sector salary doc (NACE — finance, pharma, consulting, healthcare)
    sector_doc = build_eu_sector_salary_doc(sector_wages)
    if sector_doc:
        docs.append(sector_doc)
        print(f"  NACE sector salary doc added ({len(sector_wages)} countries)")

    # ISCO occupation group salary doc (earn_ses_pub3a — when accessible)
    if isco_wages:
        isco_doc = build_eu_isco_occupation_doc(isco_wages)
        if isco_doc:
            docs.append(isco_doc)
            print(f"  ISCO occupation salary doc added ({len(isco_wages)} countries)")

    # Pan-EU non-tech role salary estimates (triangulated from NACE + ISCED + ISCO)
    nontech_doc = build_eu_nontech_role_overview_doc(sector_wages, edu_wages, isco_wages)
    docs.append(nontech_doc)
    print("  Non-tech role estimates overview doc added")

    # Per-country non-tech role salary cards for top EU markets
    for cc in _TOP_EU_MARKETS_ROLE_CARDS:
        card = build_eu_country_role_card(cc, sector_wages, edu_wages, isco_wages, len(docs))
        if card:
            docs.append(card)
            print(f"  Country role card: {card['title'][:65]}")

    # Swiss region documents
    for region_code in sorted(_BFS_REGIONS):
        if swiss_wages and region_code in swiss_wages:
            doc = build_swiss_region_doc(
                region_code,
                swiss_wages[region_code],
                doc_idx=len(docs),
                rates=rates or None,
            )
        else:
            doc = build_swiss_region_stub_doc(region_code, doc_idx=len(docs))
        docs.append(doc)
        print(f"  Swiss doc: {doc['title'][:70]}")

    # Adzuna live job market documents (tech + non-tech)
    # When --skip-adzuna is active, carry over existing Adzuna docs from the previous run
    # so the output file keeps that coverage without burning daily API quota.
    if skip_adzuna and not dry_run and output_file.exists():
        try:
            existing = json.loads(output_file.read_text(encoding="utf-8"))
            carried = [d for d in existing if d.get("id", "").startswith("adzuna-")]
            for d in carried:
                docs.append(d)
            if carried:
                print(f"  Adzuna: carried over {len(carried)} docs from existing file (--skip-adzuna)")
        except Exception as exc:
            print(f"  WARN: could not carry over Adzuna docs: {exc}")
    else:
        for cc, cname in _ADZUNA_EU_COUNTRIES.items():
            if cc in adzuna_data:
                doc = build_adzuna_country_doc(cc, cname, adzuna_data[cc], doc_idx=len(docs))
                if doc:
                    docs.append(doc)
                    print(f"  Adzuna doc: {doc['title'][:70]}")

    print(f"\nTotal documents: {len(docs)}")

    if dry_run:
        print("  [dry-run] Output NOT written.")
        return docs

    output_file.write_text(json.dumps(docs, indent=2, ensure_ascii=False), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"  Written: {output_file}  ({size_kb} KB)")
    return docs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description=(
            "Fetch real Swiss/EU labour-market data from Eurostat + BFS PXWEB + "
            "frankfurter.app + Adzuna."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default=_default_out,
        help=f"Directory to write swiss_eu_market_real.json (default: {_default_out})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch data and print stats but do NOT write the output file.",
    )
    parser.add_argument(
        "--skip-adzuna", action="store_true",
        help="Skip Adzuna job market data (useful when Adzuna quota is exhausted).",
    )
    args = parser.parse_args()

    docs = fetch_swiss_eu_market(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        skip_adzuna=args.skip_adzuna,
    )

    if not args.dry_run:
        print(
            "\nNext step — update admin_kb_controller.py _DEFAULT_SOURCE_PATHS:\n"
            "  KBDocType.swiss_eu_market: str(_KB_DIR / 'swiss_eu_market_real.json')\n"
            "\nThen ingest:\n"
            "  POST /api/v1/admin/kb/ingest\n"
            "  {'doc_types': ['swiss_eu_market']}"
        )


if __name__ == "__main__":
    main()
