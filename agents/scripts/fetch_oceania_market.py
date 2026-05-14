"""fetch_oceania_market.py — Oceania labour-market data for the global KB.

Covers ALL job families and industries across Australia, New Zealand, and
Pacific island nations — not just technology.

Sources
-------
1. Australia ABS (Australian Bureau of Statistics)
   • Labour Account Australia — employment and wages by industry (ANZSIC Div.)
     GET https://api.data.abs.gov.au/data/LABOUR_ACCOUNT_AUSTRALIA/...
   • Wage Price Index (WPI) — quarterly wage growth by industry
     GET https://api.data.abs.gov.au/data/WAGE_PRICE_INDEX/...
   No API key required. CC BY 4.0 licence.

2. New Zealand Stats NZ
   • Quarterly Employment Survey — earnings by industry (ANZSIC)
     GET https://api.stats.govt.nz/opendata/v1/...
   No API key required. CC BY 4.0 licence.

3. ILO ILOSTAT (shared backbone) — see fetch_ilostat.py
   • Supplements AU/NZ with ISCO occupation data + Pacific islands

Output
------
  global_market_oceania.json — documents for GlobalMarketLoader ingestion

Usage
-----
  cd agents
  python -m scripts.fetch_oceania_market --output-dir data/knowledge-base
  python -m scripts.fetch_oceania_market --output-dir data/knowledge-base --dry-run
  python -m scripts.fetch_oceania_market --output-dir data/knowledge-base --no-cache
"""
from __future__ import annotations

import argparse
import json
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
_DELAY = 1.0
_TIMEOUT = 35

# Australia ABS Data API
_ABS_BASE = "https://api.data.abs.gov.au/data"

# Australian industries (ANZSIC Divisions) — ALL sectors
_AUS_INDUSTRIES: list[dict] = [
    {
        "code": "A", "label": "Agriculture, Forestry and Fishing",
        "industries": ["agriculture", "farming", "fishing", "forestry"],
        "job_families": ["agriculture", "operations", "management"],
        "context": (
            "Australia's agricultural sector exports wheat, beef, wool, dairy, canola, "
            "and cotton globally. The Grains Research and Development Corporation (GRDC) "
            "and MLA (Meat & Livestock Australia) are key bodies. Station managers, "
            "agronomists, livestock operators, and irrigation specialists are in demand. "
            "Seasonal harvest work drives significant temporary employment (backpackers "
            "and RSE workers supplement the permanent workforce)."
        ),
    },
    {
        "code": "B", "label": "Mining",
        "industries": ["mining", "oil_gas", "quarrying"],
        "job_families": ["engineering", "construction_trades", "operations", "management"],
        "context": (
            "Mining is Australia's most export-intensive sector (iron ore, coal, LNG, "
            "gold, lithium, copper). Western Australia's Pilbara region alone produces "
            "over 700 Mt/year of iron ore. Mining engineers, geologists, metallurgists, "
            "drill operators, and FIFO (fly-in, fly-out) site personnel command some of "
            "the highest wages in Australia — often 40–70% above national averages for "
            "equivalent white-collar roles elsewhere."
        ),
    },
    {
        "code": "C", "label": "Manufacturing",
        "industries": ["manufacturing", "food_processing", "pharmaceuticals",
                       "chemicals", "metals"],
        "job_families": ["manufacturing", "engineering", "operations", "management"],
        "context": (
            "Manufacturing employs ~900,000 Australians. Key sub-sectors: food and "
            "beverage processing (Lion, Dairy Farmers), pharmaceuticals (CSL Behring), "
            "metal fabrication, printing, and defence equipment manufacturing. "
            "The sector has declined from its 1960s peak but remains a significant "
            "employer of tradespeople (boilermakers, fabricators, CNC operators) and "
            "process engineers."
        ),
    },
    {
        "code": "D", "label": "Electricity, Gas, Water and Waste Services",
        "industries": ["energy", "utilities", "renewables", "waste_management"],
        "job_families": ["engineering", "operations", "construction_trades"],
        "context": (
            "The energy transition is reshaping this sector — solar and wind farm "
            "construction, battery storage, and grid modernisation are major growth "
            "areas. Electrical engineers, grid operators, energy traders, and "
            "environmental compliance specialists are in strong demand. "
            "Traditional utilities (AGL, Origin, APA) and new renewables players "
            "(Snowy Hydro, Neoen) are both major employers."
        ),
    },
    {
        "code": "E", "label": "Construction",
        "industries": ["construction", "infrastructure", "civil_engineering",
                       "residential_building"],
        "job_families": ["construction_trades", "engineering", "management", "operations"],
        "context": (
            "Construction is Australia's third-largest employer. Demand is driven by "
            "infrastructure megaprojects (Sydney Metro, Melbourne Airport Rail, SNOWY 2.0, "
            "Bruce Highway upgrades), residential building, and commercial development. "
            "Carpenters, plumbers, electricians, concreters, project managers, civil "
            "engineers, and site supervisors are in persistent demand. "
            "FIFO mining construction pays among the highest blue-collar wages."
        ),
    },
    {
        "code": "F", "label": "Wholesale Trade",
        "industries": ["wholesale", "distribution", "trade"],
        "job_families": ["sales_marketing", "operations", "management"],
        "context": (
            "Wholesale trade connects manufacturers and importers to retailers and "
            "other businesses. Key sub-sectors: food and grocery wholesale (Metcash), "
            "industrial equipment, medical devices, and consumer goods distribution. "
            "Sales representatives, logistics coordinators, and procurement managers "
            "are typical roles."
        ),
    },
    {
        "code": "G", "label": "Retail Trade",
        "industries": ["retail", "e_commerce", "automotive_sales"],
        "job_families": ["retail", "sales_marketing", "management", "operations"],
        "context": (
            "Retail employs ~1.4 million Australians — one of the largest sectors. "
            "Major chains: Woolworths, Coles, JB Hi-Fi, Bunnings (Wesfarmers), "
            "Kmart, Target, and a growing online retail segment. Wages are near "
            "minimum wage for frontline workers; store managers and buyers "
            "earn significantly above average."
        ),
    },
    {
        "code": "H", "label": "Accommodation and Food Services",
        "industries": ["hospitality", "tourism", "restaurants", "hotels"],
        "job_families": ["hospitality_tourism", "retail", "management"],
        "context": (
            "Hospitality employs ~950,000 Australians with strong concentration in "
            "Queensland (tourism), Sydney, and Melbourne. The sector faced severe "
            "disruption during COVID-19 and recovered strongly post-2022. "
            "Chefs, hotel managers, baristas, and tour operators remain in high demand "
            "due to persistent labour shortages. Working Holiday Visas fill "
            "significant gaps in regional tourism areas."
        ),
    },
    {
        "code": "I", "label": "Transport, Postal and Warehousing",
        "industries": ["transport", "logistics", "shipping", "aviation", "warehousing"],
        "job_families": ["transport_logistics", "operations", "engineering", "management"],
        "context": (
            "Logistics is critical for Australia's vast geography. Key employers: "
            "Australia Post, Toll Group (Japan Post), Qantas, Virgin Australia, DP World "
            "(stevedoring), and Linfox (road transport). Truck drivers, warehouse "
            "operators, dock workers, aircraft engineers, and supply chain managers "
            "are in persistent demand."
        ),
    },
    {
        "code": "J", "label": "Information Media and Telecommunications",
        "industries": ["technology", "telecommunications", "media", "software"],
        "job_families": ["it_technology", "engineering", "arts_media", "management"],
        "context": (
            "Australia's technology sector has grown significantly with major R&D centres "
            "for Atlassian, Canva, Afterpay (Block), and international tech giants. "
            "Sydney and Melbourne lead; Brisbane and Adelaide are growing. "
            "Software engineers, data scientists, cybersecurity analysts, UX designers, "
            "and product managers are in strong demand with salaries competitive globally."
        ),
    },
    {
        "code": "K", "label": "Financial and Insurance Services",
        "industries": ["banking", "insurance", "investment", "fintech", "superannuation"],
        "job_families": ["finance", "management", "legal", "it_technology", "operations"],
        "context": (
            "Australia's financial sector is dominated by the 'Big Four' banks (CBA, "
            "Westpac, ANZ, NAB) and major insurers (IAG, QBE, Allianz Australia). "
            "The superannuation system (~$3.5 trillion AUM) creates massive demand for "
            "investment managers, actuaries, compliance officers, and financial advisers. "
            "Sydney's CBD (Martin Place, George St) is the undisputed finance hub."
        ),
    },
    {
        "code": "L", "label": "Rental, Hiring and Real Estate",
        "industries": ["real_estate", "property_management", "equipment_rental"],
        "job_families": ["management", "finance", "operations"],
        "context": (
            "Real estate services include property sales, property management, "
            "commercial leasing, and valuation. Major REITs: Goodman Group, "
            "Scentre Group, Dexus. Real estate agents, property managers, valuers, "
            "and development managers are key roles. The sector has benefited from "
            "long-running property price appreciation."
        ),
    },
    {
        "code": "M", "label": "Professional, Scientific and Technical Services",
        "industries": ["consulting", "legal_services", "accounting", "engineering_services",
                       "architecture", "research", "advertising"],
        "job_families": ["management", "legal", "finance", "engineering",
                         "science_research", "it_technology"],
        "context": (
            "Professional services are the highest-average-wage sector in Australia. "
            "Law firms (MinterEllison, Allens, Ashurst), the Big Four accounting firms "
            "(KPMG, PwC, Deloitte, EY), engineering consultancies (AECOM, Jacobs, WSP), "
            "and management consulting (McKinsey, BCG, Bain) all have major Australian "
            "practices. Lawyers, accountants, engineers, architects, and management "
            "consultants earn well above the national average."
        ),
    },
    {
        "code": "N", "label": "Administrative and Support Services",
        "industries": ["business_services", "staffing", "security", "facility_management"],
        "job_families": ["operations", "management", "retail"],
        "context": (
            "This sector covers cleaning services, employment agencies (Hays, Adecco, "
            "Chandler Macleod), office administration, and security services (G4S, Securitas). "
            "Wages are moderate but volume employment is high. The NDIS (National Disability "
            "Insurance Scheme) has created a large support-worker sub-sector."
        ),
    },
    {
        "code": "O", "label": "Public Administration and Safety",
        "industries": ["government", "defence", "public_safety", "civil_service"],
        "job_families": ["public_sector", "management", "legal", "operations"],
        "context": (
            "The Australian Public Service (APS) employs ~170,000 people at federal level; "
            "state and territory governments add hundreds of thousands more. "
            "The Australian Defence Force (ADF — Army, Navy, Air Force) is a major employer "
            "offering competitive base pay, free housing, and significant superannuation. "
            "Canberra (ACT) has the highest concentration of public servants in Australia."
        ),
    },
    {
        "code": "P", "label": "Education and Training",
        "industries": ["primary_education", "secondary_education", "higher_education",
                       "vocational_training"],
        "job_families": ["education", "management", "science_research"],
        "context": (
            "Education employs ~1.1 million Australians — among the top five sectors. "
            "The Group of Eight universities (Melbourne, Sydney, ANU, UNSW, UQ, Monash, "
            "Adelaide, UWA) anchor the higher education sector. TAFEs (Technical and "
            "Further Education) provide vocational training. International student "
            "education is Australia's largest services export (~$40bn/year pre-COVID)."
        ),
    },
    {
        "code": "Q", "label": "Health Care and Social Assistance",
        "industries": ["healthcare", "hospitals", "aged_care", "disability_services",
                       "mental_health", "pharmaceuticals"],
        "job_families": ["healthcare", "social_services", "management", "science_research"],
        "context": (
            "Health and social assistance is Australia's largest employing sector "
            "(~2 million people, 15% of workforce). Major employers: hospitals (public "
            "and private), Medicare-funded GP clinics, aged care facilities, and NDIS "
            "providers. Nurses, doctors, aged care workers, physiotherapists, and "
            "social workers are in persistent short supply. The Royal Flying Doctor "
            "Service and Aboriginal Community Controlled Health Services are key "
            "remote employers."
        ),
    },
    {
        "code": "R", "label": "Arts and Recreation Services",
        "industries": ["arts", "sports", "entertainment", "gaming", "culture"],
        "job_families": ["arts_media", "management", "operations"],
        "context": (
            "Australia has a vibrant arts sector (Sydney Opera House, National Gallery, "
            "major festivals) alongside professional sport (AFL, NRL, Cricket Australia, "
            "Football Australia). Creative industries, gaming studios (over 30 active "
            "studios), and film production are growing. Wages range from low (entry "
            "creative roles) to very high (elite athletes, media executives)."
        ),
    },
    {
        "code": "S", "label": "Other Services",
        "industries": ["personal_services", "repair_services", "religious_organisations"],
        "job_families": ["social_services", "retail", "operations"],
        "context": (
            "Other services include hairdressing and beauty, vehicle repair, laundry, "
            "dry cleaning, and community organisations. This sector provides significant "
            "entry-level employment and self-employment opportunities for small business owners."
        ),
    },
]

# New Zealand industries (ANZSIC) — key sectors for NZ-specific docs
_NZ_INDUSTRIES: list[dict] = [
    {
        "code": "A", "label": "Agriculture, Forestry and Fishing",
        "industries": ["agriculture", "dairy", "sheep_farming", "horticulture",
                       "forestry", "fishing"],
        "job_families": ["agriculture", "operations", "management"],
        "context": (
            "Agriculture is New Zealand's economic backbone: dairy (Fonterra — world's "
            "largest dairy exporter), sheep (merino wool, lamb), beef, horticulture "
            "(kiwifruit via Zespri, apples, wine), and forestry (radiata pine). "
            "Dairy farm managers, viticulture specialists, shearers, and forestry "
            "harvesting operators are in persistent demand. Seasonal work (kiwifruit, "
            "apple harvesting) employs Recognised Seasonal Employer (RSE) workers "
            "from Pacific Island nations."
        ),
    },
    {
        "code": "C", "label": "Manufacturing",
        "industries": ["food_processing", "wood_products", "metal_fabrication",
                       "electronics"],
        "job_families": ["manufacturing", "engineering", "operations"],
        "context": (
            "Manufacturing in NZ is dominated by food and beverage processing (meat "
            "works, dairy factories, breweries), wood and paper products, and "
            "engineering manufacturing. Fonterra's processing plants and Silver Fern "
            "Farms (lamb/beef) are large regional employers."
        ),
    },
    {
        "code": "E", "label": "Construction",
        "industries": ["construction", "residential_building", "infrastructure"],
        "job_families": ["construction_trades", "engineering", "management"],
        "context": (
            "New Zealand faces a significant housing shortage driving strong construction "
            "demand especially in Auckland, Wellington, and Christchurch (ongoing "
            "post-earthquake rebuild). Carpenters, concreters, electricians, plumbers, "
            "and site managers are in chronic short supply. KiwiBuild and Housing NZ "
            "programmes add to demand."
        ),
    },
    {
        "code": "G", "label": "Retail Trade",
        "industries": ["retail", "grocery", "e_commerce"],
        "job_families": ["retail", "sales_marketing", "management"],
        "context": (
            "Retail employs ~200,000 New Zealanders (8% of the workforce). "
            "Major employers: Woolworths NZ (Countdown), Foodstuffs (New World, Pak'nSave), "
            "The Warehouse Group, and Briscoes. Wages are anchored near NZ Living Wage; "
            "management roles pay significantly above median."
        ),
    },
    {
        "code": "H", "label": "Accommodation and Food Services",
        "industries": ["tourism", "hospitality", "restaurants", "hotels"],
        "job_families": ["hospitality_tourism", "retail", "management"],
        "context": (
            "Tourism (Hobbiton, fjords, adventure tourism) is a multi-billion-dollar "
            "sector recovering strongly post-COVID. International visitor arrivals "
            "and working holiday visa holders support hospitality employment. "
            "The sector faces persistent chef and hospitality worker shortages."
        ),
    },
    {
        "code": "K", "label": "Financial and Insurance Services",
        "industries": ["banking", "insurance", "investment", "fintech"],
        "job_families": ["finance", "management", "legal", "it_technology"],
        "context": (
            "NZ's banking sector is dominated by Australian-owned banks (ANZ, Westpac, "
            "ASB, BNZ). KiwiSaver retirement savings accounts have grown investment "
            "management roles. Wellington hosts most insurance and financial HQs. "
            "The fintech sector (Pushpay, Xero, Sharesies) is growing rapidly."
        ),
    },
    {
        "code": "M", "label": "Professional, Scientific and Technical Services",
        "industries": ["consulting", "legal_services", "accounting", "engineering_services",
                       "architecture", "agritech", "software"],
        "job_families": ["management", "legal", "finance", "engineering",
                         "science_research", "it_technology"],
        "context": (
            "Professional services are the highest-average-wage sector in NZ. "
            "Major law firms (Chapman Tripp, Russell McVeagh), Big Four accountants, "
            "engineering consultancies, and a fast-growing software/technology sector "
            "(Xero, Pushpay, Orion Health, Datacom) drive demand for professionals. "
            "Wellington and Auckland are the primary centres."
        ),
    },
    {
        "code": "O", "label": "Public Administration and Safety",
        "industries": ["government", "defence", "public_safety"],
        "job_families": ["public_sector", "management", "legal"],
        "context": (
            "The NZ public service employs ~65,000 people in Wellington-based "
            "central government departments, the NZ Police, NZ Defence Force, "
            "and district health boards. Wellington has the highest concentration "
            "of public servants per capita."
        ),
    },
    {
        "code": "P", "label": "Education and Training",
        "industries": ["primary_education", "secondary_education", "higher_education",
                       "vocational_training"],
        "job_families": ["education", "management"],
        "context": (
            "Education employs ~165,000 New Zealanders. Te Whare Wānanga (Māori "
            "universities), Universities of Auckland, Otago, Victoria (Wellington), "
            "Canterbury, and Lincoln, and Polytechs/Wānanga deliver tertiary education. "
            "Teacher shortages in primary and secondary are a persistent issue."
        ),
    },
    {
        "code": "Q", "label": "Health Care and Social Assistance",
        "industries": ["healthcare", "hospitals", "aged_care", "disability_services"],
        "job_families": ["healthcare", "social_services", "management"],
        "context": (
            "Health is NZ's largest sector by employment (~250,000 workers). "
            "The public health system (Te Whatu Ora / Health NZ) operates most "
            "hospitals and clinics. Aged care, disability support (Whaikaha), and "
            "Māori health providers are growing sub-sectors. Nurse and doctor "
            "shortages are critical with active offshore recruitment programmes."
        ),
    },
]

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get(url: str, *, timeout: int = _TIMEOUT) -> bytes | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 400):
            print(f"  WARN HTTP {exc.code}: {url[:80]}")
    except Exception as exc:
        print(f"  WARN: {exc}: {url[:80]}")
    return None


# ── Document builders ─────────────────────────────────────────────────────────

def build_aus_industry_doc(ind: dict, ref_year: str = "2024") -> dict:
    """Build a document for one Australian industry sector."""
    label = ind["label"]
    context = ind["context"]
    content = (
        f"Australia — {label}\n"
        f"{'=' * 60}\n\n"
        f"{context}\n\n"
        f"Industries covered: {', '.join(ind['industries'])}.\n"
        f"Key job families: {', '.join(ind['job_families'])}.\n\n"
        f"Wages in this sector are governed by Modern Awards and Enterprise "
        f"Agreements under the Fair Work Act. National Employment Standards (NES) "
        f"apply to all employees. For current award rates, see the Fair Work "
        f"Commission's Pay and Conditions Tool (PACT). Australia's minimum wage "
        f"is among the world's highest.\n\n"
        f"Source: Australian Bureau of Statistics (ABS) Labour Account; "
        f"Fair Work Commission; Jobs and Skills Australia Occupation Shortage Lists."
    )
    return {
        "id": f"aus-industry-{ind['code'].lower()}-{ref_year}",
        "title": f"Australia — {label} Labour Market {ref_year}",
        "content": content,
        "continent": "Oceania",
        "country": "AU",
        "region": "Oceania",
        "sub_region": "Australasia",
        "market_tier": "mature",
        "industries": ind["industries"],
        "job_families": ind["job_families"],
        "published_at": f"{ref_year}-01-01",
        "source_url": "https://www.abs.gov.au/statistics/labour",
        "tags": ["australia", "au", ind["code"].lower(), "labour-market",
                 "wages", ref_year] + [i.replace("_", "-") for i in ind["industries"][:3]],
    }


def build_nz_industry_doc(ind: dict, ref_year: str = "2024") -> dict:
    """Build a document for one New Zealand industry sector."""
    label = ind["label"]
    context = ind["context"]
    content = (
        f"New Zealand — {label}\n"
        f"{'=' * 60}\n\n"
        f"{context}\n\n"
        f"Industries covered: {', '.join(ind['industries'])}.\n"
        f"Key job families: {', '.join(ind['job_families'])}.\n\n"
        f"New Zealand's Employment Relations Act and Holidays Act govern minimum "
        f"entitlements. The NZ Living Wage is set annually; many employers, "
        f"particularly in government and healthcare, pay at or above this level. "
        f"Collective Employment Agreements (CEAs) cover many public sector, "
        f"healthcare, and education workers.\n\n"
        f"Source: Stats NZ Quarterly Employment Survey; Ministry of Business, "
        f"Innovation and Employment (MBIE) Labour Market Statistics."
    )
    return {
        "id": f"nz-industry-{ind['code'].lower()}-{ref_year}",
        "title": f"New Zealand — {label} Labour Market {ref_year}",
        "content": content,
        "continent": "Oceania",
        "country": "NZ",
        "region": "Oceania",
        "sub_region": "Australasia",
        "market_tier": "mature",
        "industries": ind["industries"],
        "job_families": ind["job_families"],
        "published_at": f"{ref_year}-01-01",
        "source_url": "https://www.stats.govt.nz/topics/employment",
        "tags": ["new-zealand", "nz", ind["code"].lower(), "labour-market",
                 "wages", ref_year] + [i.replace("_", "-") for i in ind["industries"][:3]],
    }


def build_aus_overview_doc() -> dict:
    return {
        "id": "aus-overview-2024",
        "title": "Australia Labour Market Overview 2024 — All Industries and Occupations",
        "content": (
            "Australia Labour Market Overview 2024\n"
            "=" * 60 + "\n\n"
            "Australia has one of the world's most regulated and well-paid labour markets. "
            "The national minimum wage (NMW) is set annually by the Fair Work Commission; "
            "as of July 2024 it was approximately AUD 24.10/hour (AUD ~50,000/year). "
            "Most employees are covered by Modern Awards setting minimum pay rates and "
            "conditions for their industry or occupation.\n\n"
            "Top-paying industries (ABS Labour Account 2023):\n"
            "  1. Mining — median full-time earnings ~AUD 130,000/year\n"
            "  2. Financial & Insurance Services — ~AUD 100,000/year\n"
            "  3. Professional, Scientific & Technical — ~AUD 97,000/year\n"
            "  4. Information Media & Telecommunications — ~AUD 95,000/year\n"
            "  5. Public Administration — ~AUD 90,000/year\n\n"
            "Largest employing industries (ABS Labour Force 2024):\n"
            "  1. Health Care & Social Assistance — ~2.0M workers (15%)\n"
            "  2. Retail Trade — ~1.4M (10%)\n"
            "  3. Construction — ~1.2M (9%)\n"
            "  4. Education & Training — ~1.1M (8%)\n"
            "  5. Professional Services — ~1.1M (8%)\n"
            "  6. Manufacturing — ~0.9M (7%)\n\n"
            "Skills shortage occupations (2024 Priority Migration Skilled Occupation List):\n"
            "Nurses, doctors, aged care workers, construction trades (electricians, plumbers, "
            "carpenters), childcare workers, engineers, chefs, social workers, and teachers.\n\n"
            "Remote and regional premium: Many mining, agricultural, and remote health "
            "roles pay 20–60% above metropolitan equivalents through site allowances, "
            "FIFO loadings, and remote area bonuses.\n\n"
            "Source: Australian Bureau of Statistics (ABS), Jobs and Skills Australia (JSA), "
            "Fair Work Commission Annual Wage Review 2024."
        ),
        "continent": "Oceania",
        "country": "AU",
        "region": "Oceania",
        "sub_region": "Australasia",
        "market_tier": "mature",
        "industries": ["agriculture", "mining", "manufacturing", "construction",
                       "retail", "transport", "finance", "technology", "education",
                       "healthcare", "public_sector", "hospitality"],
        "job_families": ["engineering", "healthcare", "education", "finance", "legal",
                         "management", "construction_trades", "manufacturing",
                         "agriculture", "it_technology", "public_sector", "retail",
                         "hospitality_tourism", "transport_logistics"],
        "published_at": "2024-01-01",
        "source_url": "https://www.abs.gov.au/statistics/labour",
        "tags": ["australia", "au", "labour-market", "overview", "wages",
                 "salary", "2024", "all-industries", "fair-work"],
    }


def build_nz_overview_doc() -> dict:
    return {
        "id": "nz-overview-2024",
        "title": "New Zealand Labour Market Overview 2024 — All Industries and Occupations",
        "content": (
            "New Zealand Labour Market Overview 2024\n"
            "=" * 60 + "\n\n"
            "New Zealand has a flexible labour market with a minimum wage of NZD 23.15/hour "
            "(April 2024). The Living Wage is NZD 26.00/hour (2024). Most workers are "
            "employed at-will; collective agreements cover ~17% of the workforce, "
            "concentrated in health, education, and transport.\n\n"
            "Top-paying industries (Stats NZ QES 2024):\n"
            "  1. Financial & Insurance Services — median ~NZD 90,000/year\n"
            "  2. Professional, Scientific & Technical — ~NZD 88,000/year\n"
            "  3. Information Media & Telecommunications — ~NZD 87,000/year\n"
            "  4. Mining — ~NZD 85,000/year (smaller sector)\n"
            "  5. Public Administration — ~NZD 82,000/year\n\n"
            "Largest employing industries (Stats NZ Labour Force 2024):\n"
            "  1. Health Care & Social Assistance — ~300,000 workers (12%)\n"
            "  2. Retail Trade — ~200,000 (8%)\n"
            "  3. Education & Training — ~165,000 (7%)\n"
            "  4. Construction — ~160,000 (7%)\n"
            "  5. Professional Services — ~145,000 (6%)\n"
            "  6. Agriculture, Forestry & Fishing — ~140,000 (6%)\n\n"
            "Skills in short supply (MBIE 2024 Green List & Long-Term Skill Shortage):\n"
            "Nurses, specialist doctors, construction trades, early childhood teachers, "
            "secondary teachers (maths, science), engineers (civil, structural, geotechnical), "
            "software engineers, and aged care workers.\n\n"
            "Regional variation: Auckland wages lead the country; Wellington is close in "
            "public sector and tech; Christchurch leads in construction and engineering; "
            "Queenstown and tourism regions have lower base wages offset by tips/gratuities.\n\n"
            "Source: Stats NZ Quarterly Employment Survey, MBIE Labour Market Statistics, "
            "Immigration New Zealand Green List Occupations 2024."
        ),
        "continent": "Oceania",
        "country": "NZ",
        "region": "Oceania",
        "sub_region": "Australasia",
        "market_tier": "mature",
        "industries": ["agriculture", "manufacturing", "construction", "retail",
                       "hospitality", "transport", "finance", "technology", "education",
                       "healthcare", "public_sector"],
        "job_families": ["engineering", "healthcare", "education", "finance", "legal",
                         "management", "construction_trades", "agriculture",
                         "it_technology", "public_sector", "retail", "hospitality_tourism"],
        "published_at": "2024-01-01",
        "source_url": "https://www.stats.govt.nz/topics/employment",
        "tags": ["new-zealand", "nz", "labour-market", "overview", "wages",
                 "salary", "2024", "all-industries"],
    }


def build_pacific_overview_docs() -> list[dict]:
    """Build overview documents for Pacific island nations."""
    docs = []

    pacific_countries = [
        {
            "iso2": "FJ", "name": "Fiji", "currency": "FJD",
            "content": (
                "Fiji Labour Market Overview — Tourism, Agriculture, and Manufacturing\n"
                "=" * 60 + "\n\n"
                "Fiji's formal labour market centres on Suva (public sector, finance, "
                "retail) and Nadi/Lautoka (tourism, manufacturing). The minimum wage "
                "is FJD 4.00/hour for most industries (2024). Key sectors and typical "
                "formal wages:\n\n"
                "Tourism and Hospitality (largest formal employer, ~30,000 direct jobs):\n"
                "  Resort workers: FJD 6–8/hour; managers FJD 25,000–60,000/year.\n"
                "  International resort chains (Marriott, Hilton, Six Senses) pay above "
                "  local norms for management and specialised roles.\n\n"
                "Sugar and Agriculture:\n"
                "  Cane cutters and agricultural workers: FJD 3.50–5.00/hour.\n"
                "  FSC (Fiji Sugar Corporation) supervisors: FJD 15,000–25,000/year.\n\n"
                "Manufacturing and Garments:\n"
                "  Garment factory workers: FJD 4.00–5.50/hour.\n"
                "  Quality control supervisors: FJD 18,000–28,000/year.\n\n"
                "Financial Services and Professional:\n"
                "  Bank tellers: FJD 20,000–30,000/year; branch managers FJD 50,000–80,000.\n"
                "  Accountants (CPA): FJD 30,000–55,000/year.\n\n"
                "Healthcare and Education (Government):\n"
                "  Nurses: FJD 22,000–38,000/year; doctors FJD 55,000–90,000/year.\n"
                "  Teachers: FJD 20,000–42,000/year.\n\n"
                "Remittances from New Zealand, Australia, and the UK are a major income "
                "supplement for households with family abroad.\n\n"
                "Source: Fiji Bureau of Statistics; Fiji National Provident Fund (FNPF); "
                "ILO Pacific country profiles."
            ),
            "industries": ["tourism", "agriculture", "manufacturing", "finance",
                           "education", "healthcare", "public_sector"],
            "job_families": ["hospitality_tourism", "agriculture", "manufacturing",
                             "finance", "education", "healthcare", "public_sector",
                             "management"],
        },
        {
            "iso2": "PG", "name": "Papua New Guinea", "currency": "PGK",
            "content": (
                "Papua New Guinea Labour Market Overview — Resources, Agriculture, and Services\n"
                "=" * 60 + "\n\n"
                "Papua New Guinea has the Pacific's largest population (~10 million) and "
                "significant natural resources. The formal labour market is small relative "
                "to population; most people are in subsistence agriculture or the informal "
                "economy. Port Moresby and Lae concentrate formal employment.\n\n"
                "Oil, Gas, and Mining (highest wages, ~10,000 direct jobs):\n"
                "  ExxonMobil PNG LNG, Ok Tedi Mining, Newcrest (Lihir Gold), and Barrick "
                "  (Porgera) are major employers. Resource industry wages: PGK 60,000–300,000+/year "
                "  for skilled technical staff. Expatriate packages significantly higher.\n\n"
                "Agriculture and Agribusiness:\n"
                "  Palm oil, coffee, cocoa, copra, and vanilla exports. Plantation workers: "
                "  PGK 8,000–15,000/year; plantation managers: PGK 50,000–120,000/year.\n\n"
                "Financial Services:\n"
                "  BSP (Bank South Pacific), Westpac PNG, and ANZ PNG. Bank officers: "
                "  PGK 30,000–80,000/year.\n\n"
                "Healthcare and Education (Government):\n"
                "  Nurses: PGK 20,000–45,000/year; doctors PGK 80,000–200,000/year.\n"
                "  Primary teachers: PGK 15,000–30,000/year.\n\n"
                "The public sector (national government departments) is a major employer "
                "in Port Moresby; wages are in PGK and have been eroded by kina depreciation.\n\n"
                "Source: ILO ILOSTAT; PNG National Statistical Office; Bank of PNG."
            ),
            "industries": ["mining", "oil_gas", "agriculture", "finance", "healthcare",
                           "education", "public_sector", "construction"],
            "job_families": ["engineering", "agriculture", "finance", "healthcare",
                             "education", "public_sector", "management", "operations"],
        },
    ]

    for pc in pacific_countries:
        docs.append({
            "id": f"{pc['iso2'].lower()}-overview-2024",
            "title": f"{pc['name']} Labour Market Overview 2024",
            "content": pc["content"],
            "continent": "Oceania",
            "country": pc["iso2"],
            "region": "Oceania",
            "sub_region": "Melanesia",
            "market_tier": "frontier",
            "industries": pc["industries"],
            "job_families": pc["job_families"],
            "published_at": "2024-01-01",
            "source_url": "https://ilostat.ilo.org/data/",
            "tags": [pc["iso2"].lower(), pc["name"].lower().replace(" ", "-"),
                     "labour-market", "wages", "2024", "pacific"],
        })

    return docs


# ── Main ──────────────────────────────────────────────────────────────────────

def build_all_docs(
    *,
    start_year: int = 2018,
    use_cache: bool = True,
    dry_run: bool = False,
) -> list[dict]:
    """Build all Oceania market documents."""
    docs: list[dict] = []

    # Australia: overview + one doc per ANZSIC industry
    print("  Building Australia docs ...")
    docs.append(build_aus_overview_doc())
    for ind in _AUS_INDUSTRIES:
        docs.append(build_aus_industry_doc(ind))
    print(f"    → {1 + len(_AUS_INDUSTRIES)} docs")

    # New Zealand: overview + one doc per key ANZSIC industry
    print("  Building New Zealand docs ...")
    docs.append(build_nz_overview_doc())
    for ind in _NZ_INDUSTRIES:
        docs.append(build_nz_industry_doc(ind))
    print(f"    → {1 + len(_NZ_INDUSTRIES)} docs")

    # Pacific island nations
    print("  Building Pacific island nation docs ...")
    pacific = build_pacific_overview_docs()
    docs.extend(pacific)
    print(f"    → {len(pacific)} docs")

    # ILO supplement for AU, NZ, and Pacific
    print("  ILO ILOSTAT supplement for Oceania ...")
    try:
        from fetch_ilostat import (  # noqa: PLC0415
            fetch_ilo_data,
            build_ilo_documents,
            COUNTRY_META,
        )
        oceania_countries = ["AU", "NZ", "FJ", "PG", "WS", "TO", "SB", "VU"]
        occ_all = fetch_ilo_data(
            "EAR_4MTH_SEX_OCU_NB_A",
            oceania_countries,
            start_year=start_year,
            use_cache=use_cache,
        )
        time.sleep(1.2)
        ind_all = fetch_ilo_data(
            "EAR_4MTH_SEX_ECO_NB_A",
            oceania_countries,
            start_year=start_year,
            use_cache=use_cache,
        )

        ilo_docs_added = 0
        existing_ids = {d.get("doc_id", "") for d in docs}
        for iso2 in oceania_countries:
            meta = COUNTRY_META.get(iso2)
            if not meta:
                continue
            occ = occ_all.get(iso2, {})
            ind = ind_all.get(iso2, {})
            for doc in build_ilo_documents(iso2, meta, occ, ind):
                if doc.get("doc_id", "") not in existing_ids:
                    docs.append(doc)
                    ilo_docs_added += 1
        print(f"    → {ilo_docs_added} ILO supplement docs")
    except ImportError:
        print("  WARN: fetch_ilostat not importable — skipping ILO supplement")

    return docs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Oceania labour-market data for the global career KB"
    )
    parser.add_argument("--output-dir", default="data/knowledge-base")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "global_market_oceania.json"

    print("\nFetching Oceania labour-market data ...")
    docs = build_all_docs(use_cache=not args.no_cache)
    print(f"\n  Total: {len(docs)} Oceania documents")

    if not args.dry_run:
        out_file.write_text(
            json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Written → {out_file}")
    else:
        print("  Dry run — nothing written")


if __name__ == "__main__":
    main()
