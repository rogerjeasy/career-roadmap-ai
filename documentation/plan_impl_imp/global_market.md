---
  Global Knowledge Base Expansion Plan

  Current State Summary

  ┌─────────────────┬─────────┬──────────────────────────────────────────┐
  │    Namespace    │ Records │                 Coverage                 │
  ├─────────────────┼─────────┼──────────────────────────────────────────┤
  │ taxonomy        │ 40,044  │ ESCO/O*NET — global skills taxonomy (OK) │
  ├─────────────────┼─────────┼──────────────────────────────────────────┤
  │ role-templates  │ 3,200   │ US-centric roles                         │
  ├─────────────────┼─────────┼──────────────────────────────────────────┤
  │ career-kb       │ 2,858   │ US/EU career guidance                    │
  ├─────────────────┼─────────┼──────────────────────────────────────────┤
  │ market-reports  │ 739     │ US BLS + Stack Overflow (global sample)  │
  ├─────────────────┼─────────┼──────────────────────────────────────────┤
  │ swiss-eu-market │ 356     │ 30 EU countries + 8 Swiss regions        │
  └─────────────────┴─────────┴──────────────────────────────────────────┘

  Gap: No structured coverage for Southeast Asia, East Asia, South Asia, MENA, Sub-Saharan Africa, LATAM, or Oceania.

  ---
  Phase 1 — Namespace & Model Architecture (no data yet)

  Rename the bottleneck namespace. swiss-eu-market is too narrow for what it will become. Introduce a second namespace:

  global-market   ← new Pinecone namespace for all non-US/EU markets

  Add to models.py:

  class DocumentType(str, Enum):
      ...
      GLOBAL_MARKET = "global_market"   # Asia, LATAM, Africa, MENA, Oceania

  class KnowledgeNamespace(str, Enum):
      ...
      GLOBAL_MARKET = "global-market"

  Add region as a required top-level metadata field on every document (already used but not enforced). Add continent and
   market_tier fields:

  {
    "region": "Southeast Asia",
    "country": "SG",
    "continent": "Asia",
    "market_tier": "emerging"   // "mature" | "emerging" | "frontier"
  }

  This enables namespace + metadata filter queries so a Singapore user doesn't get noise from Nigerian salary data
  unless they ask for global context.

  ---
  Phase 2 — Data Sources by Region

  Asia (priority 1 — largest tech talent pool)

  ┌────────────────┬────────────────────────────────────────────────────────────────┬───────────────┬───────────┐
  │ Country/Region │                       Public Data Source                       │    Format     │ Freshness │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ Singapore      │ MOM (Ministry of Manpower) Occupation Wages — stats.mom.gov.sg │ JSON API      │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ Singapore      │ Tech Skills Accelerator (TeSA) demand reports                  │ PDF → extract │ Quarterly │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ India          │ Nasscom Annual Tech Report                                     │ PDF           │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ India          │ Ministry of Labour & Employment labourbureau.gov.in            │ CSV           │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ Japan          │ MHLW (Ministry of Health, Labour & Welfare) salary survey      │ CSV           │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ South Korea    │ KEIS (Korea Employment Information Service) know.work.go.kr    │ API           │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ China          │ NBS Annual Survey of Wages stats.gov.cn                        │ HTML table    │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ HK             │ Census & Statistics Dept HHIS                                  │ CSV           │ Bi-annual │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ Southeast Asia │ JobStreet Hays Salary Guide (public PDF)                       │ PDF → extract │ Annual    │
  ├────────────────┼────────────────────────────────────────────────────────────────┼───────────────┼───────────┤
  │ Philippines    │ PSA Occupational Wages Survey                                  │ CSV           │ Annual    │
  └────────────────┴────────────────────────────────────────────────────────────────┴───────────────┴───────────┘

  Recommended starting point: Singapore MOM (JSON REST API, English, clean) + India Nasscom + Japan MHLW.

  LATAM (priority 2)

  Country: Brazil
  Source: RAIS/CAGED (Ministério do Trabalho)
  Notes: CSV, Portuguese — needs translation
  ────────────────────────────────────────
  Country: Mexico
  Source: IMSS wage records
  Notes: CSV, Spanish
  ────────────────────────────────────────
  Country: Argentina
  Source: INDEC Encuesta Permanente de Hogares
  Notes: CSV
  ────────────────────────────────────────
  Country: Colombia/Chile
  Source: Stack Overflow survey already covers some; supplement with local Glassdoor scrape
  Notes:
  ────────────────────────────────────────
  Country: Regional
  Source: Hays LATAM Salary Guide (PDF)
  Notes: Annual, English summary available

  Africa (priority 3)

  ┌────────────────────┬───────────────────────────────────────┬──────────────────────────────────────────┐
  │       Region       │                Source                 │                  Notes                   │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ Nigeria            │ NBS Labour Force Survey               │ CSV, English                             │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ Nigeria            │ Jobberman Nigeria Salary Report (PDF) │ Annual                                   │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ South Africa       │ StatsSA Quarterly Labour Force Survey │ CSV, English                             │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ Kenya              │ Kenya National Bureau of Statistics   │ CSV, English                             │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ Egypt/North Africa │ ILO country profiles (English)        │ JSON API                                 │
  ├────────────────────┼───────────────────────────────────────┼──────────────────────────────────────────┤
  │ Pan-Africa         │ ILO ILOSTAT ilostat.ilo.org           │ REST API, all African countries, English │
  └────────────────────┴───────────────────────────────────────┴──────────────────────────────────────────┘

  ILO ILOSTAT is the highest-leverage single source: covers 190 countries, REST API, English, wages by occupation (ISCO)
   and industry (ISIC). This should be the backbone for Africa and LATAM coverage.

  MENA (Middle East & North Africa)

  ┌─────────────────────────────────┬───────────────────────────┐
  │             Source              │           Notes           │
  ├─────────────────────────────────┼───────────────────────────┤
  │ ILO ILOSTAT                     │ UAE, Saudi, Egypt covered │
  ├─────────────────────────────────┼───────────────────────────┤
  │ Gulf Talent Salary Survey (PDF) │ Annual, English           │
  ├─────────────────────────────────┼───────────────────────────┤
  │ Bayt.com Salary Survey          │ Annual PDF, covers GCC    │
  └─────────────────────────────────┴───────────────────────────┘

  Oceania

  ┌─────────────────────────────────────────────────────────┬──────────────────────────────────────┐
  │                         Source                          │                Notes                 │
  ├─────────────────────────────────────────────────────────┼──────────────────────────────────────┤
  │ Australia ABS Labour Force abs.gov.au/statistics/labour │ JSON API, English, excellent quality │
  ├─────────────────────────────────────────────────────────┼──────────────────────────────────────┤
  │ New Zealand Stats NZ stats.govt.nz                      │ JSON API, English                    │
  └─────────────────────────────────────────────────────────┴──────────────────────────────────────┘

  ---
  Phase 3 — Script Architecture

  The pattern already established for fetch_swiss_eu_market.py and fetch_bls_oes.py scales cleanly. Add one script per
  region:

  agents/scripts/
    fetch_asia_market.py        ← Singapore MOM + India MOSPI + Japan MHLW + ILO fallback
    fetch_latam_market.py       ← Brazil RAIS + Mexico IMSS + Hays PDF + ILO fallback
    fetch_africa_market.py      ← Nigeria NBS + South Africa StatsSA + ILO backbone
    fetch_mena_market.py        ← ILO + Gulf Talent PDF
    fetch_oceania_market.py     ← Australia ABS + NZ Stats
    fetch_ilostat.py            ← shared ILO ILOSTAT client (used by africa + latam + mena)

  Key design principle: Every script follows the same output contract:

  # Output: agents/data/knowledge-base/<region>_market.json
  [
    {
      "id": "sg-tech-mom-2024",
      "title": "Singapore MOM Occupational Wages 2024 — Software & IT",
      "content": "...",           # prose summary, not raw CSV
      "region": "Singapore",
      "country": "SG",
      "continent": "Asia",
      "market_tier": "mature",
      "published_at": "2024-01-01",
      "source_url": "https://...",
      "tags": ["singapore", "tech", "software", "salary", "asia"]
    }
  ]

  ---
  Phase 4 — Loader, Task & Pinecone Integration

  New loader (agents/src/agents/rag/ingestion/loaders/global_market_loader.py) — identical structure to
  SwissEUMarketLoader but emits DocumentType.GLOBAL_MARKET and reads from global_market_*.json glob.

  New Celery tasks in ingestion_tasks.py:

  @celery_app.task(name="rag.ingest_asia_market")
  @celery_app.task(name="rag.ingest_latam_market")
  @celery_app.task(name="rag.ingest_africa_market")
  @celery_app.task(name="rag.ingest_mena_market")
  @celery_app.task(name="rag.ingest_oceania_market")

  Beat schedule additions:

  "rag-ingest-global-markets": {
      "task": "rag.ingest_global_market",
      "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sunday 04:00 UTC
  }

  ContextAssembler update — add global-market to the namespace fan-out when user location or query intent implies
  non-US/EU geography:

  if intent.region not in ("US", "EU", "CH"):
      namespaces.append(KnowledgeNamespace.GLOBAL_MARKET)

  Admin API — extend POST /api/v1/admin/kb/ingest to accept the new doc_types.

  ---
  Phase 5 — ILO ILOSTAT as the Backbone (highest ROI action)

  The ILO REST API gives structured wage data for 190 countries, by ISCO occupation and ISIC industry. A single
  fetch_ilostat.py script can bootstrap all underserved regions at once:

  GET https://ilostat.ilo.org/resources/sdmx/v21/data/EAR_4MTH_SEX_OCU_NB_A
      ?ref_area=NG,ZA,KE,BR,MX,AE,SA,IN,SG,AU
      &classif1=OCU_ISCO08_TOTAL
      &startPeriod=2022
      &format=jsondata

  This single call returns median monthly earnings by country + ISCO occupation group. The script converts each
  country×occupation cell into a Document — approximately 200–400 documents per API call.

  Estimated records added: ~3,000–5,000 documents across all new regions from ILO alone, bringing global-market
  namespace to comparable density with swiss-eu-market.

  ---
  Phase 6 — Role Templates Global Expansion

  Current role-templates namespace (3,200 records) is US-centric (ONET-based). Add region-specific variants:

  - Asia: Software Engineer (India IC levels), Quant Analyst (Singapore/HK), CISO (Japan regulatory context)
  - LATAM: Startup generalist roles (Brazil fintech ecosystem), bilingual PM profiles
  - Africa: Tech lead in resource-constrained infra, mobile-first engineer profiles

  These are handcrafted JSON documents (same schema as role_templates_real.json) — no external API needed. ~200–400 new
  role templates would meaningfully improve recommendation quality for non-Western users.

  ---
  Implementation Sequence (optimized for ROI)

  ┌──────┬───────────────────────────────────────────────────────────────┬──────────────┬────────┐
  │ Step │                             What                              │ Est. Records │ Effort │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 1    │ Add GLOBAL_MARKET DocumentType + namespace + loader           │ 0            │ 2h     │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 2    │ fetch_ilostat.py — ILO backbone for all continents            │ ~3,000       │ 1 day  │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 3    │ fetch_oceania_market.py — ABS + Stats NZ (clean English APIs) │ ~200         │ 4h     │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 4    │ fetch_asia_market.py — Singapore MOM + India MOSPI summary    │ ~400         │ 1 day  │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 5    │ fetch_africa_market.py — ILO-backed + NBS Nigeria + StatsSA   │ ~300         │ 1 day  │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 6    │ fetch_latam_market.py — ILO-backed + Brazil/Mexico summaries  │ ~300         │ 1 day  │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 7    │ Global role templates (handcrafted JSON)                      │ ~300         │ 2 days │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 8    │ ContextAssembler region-aware namespace routing               │ 0            │ 4h     │
  ├──────┼───────────────────────────────────────────────────────────────┼──────────────┼────────┤
  │ 9    │ Beat + Admin API wiring                                       │ 0            │ 2h     │
  └──────┴───────────────────────────────────────────────────────────────┴──────────────┴────────┘

  Total estimated new records: ~4,500–5,000, bringing index to ~52,000 records with genuine global coverage. ILO ILOSTAT
   (step 2) gives the most coverage for least effort — do that first.

  ---
  Pinecone Cost Projection

  Current: 47,197 records × 3,072 dims in aws us-east-1. Adding ~5,000 records is a ~10% increase — well within the 2GB
  storage limit (you're at 0.65GB). No tier upgrade needed until you exceed ~100K records.

Phase 2 is complete. Here's a summary of every script written:

  ---
  Phase 2 — Data Sources: All 5 Scripts Complete

  Script: fetch_oceania_market.py
  Region: Oceania
  Countries: AU, NZ + Pacific
  Curated Industries: 19 ANZSIC divisions (AU), 10 NZ sectors, Pacific overviews
  ────────────────────────────────────────
  Script: fetch_asia_market.py
  Region: Asia
  Countries: SG, IN, JP, CN, KR, PH, MY, TH, ID, VN, BD, HK, PK, LK
  Curated Industries: 14 country overviews + per-industry docs
  ────────────────────────────────────────
  Script: fetch_africa_market.py
  Region: Africa
  Countries: NG, ZA, KE, ET, GH, TZ, UG, RW, AO, EG, MA, SN, CI, CM, DZ
  Curated Industries: 15 country overviews + per-industry docs
  ────────────────────────────────────────
  Script: fetch_latam_market.py
  Region: LATAM
  Countries: BR, MX, AR, CO, CL, PE, PA, CR, TT + 8 smaller via ILO
  Curated Industries: 9 country overviews + per-industry docs
  ────────────────────────────────────────
  Script: fetch_mena_market.py
  Region: MENA
  Countries: AE, SA, QA, KW, BH, OM, TR, IL, JO, TN + ILO for DZ/IQ/LB
  Curated Industries: 10 country overviews + per-industry docs
  ────────────────────────────────────────
  Script: fetch_global_market.py
  Region: Master
  Countries: All 5 regions
  Curated Industries: Merges all regional outputs → global_market_real.json

  Every script covers ALL job families across all industries — agriculture, manufacturing, construction, retail,
  healthcare, education, finance, hospitality, logistics, mining, etc. — not just tech roles.

  To generate the full KB:
  cd agents
  python scripts/fetch_global_market.py
  # or selective regions:
  python scripts/fetch_global_market.py --regions asia africa
  # dry run to validate without writing:
  python scripts/fetch_global_market.py --dry-run

  The generated global_market_real.json feeds directly into the ingest_global_market Celery task, which is
  beat-scheduled every Sunday at 02:30 UTC.


PLEASE NOT THAT FOR ALL PHASES, YOU
  SHOULD NOT JUST LIMIT IT TO TECH JOBS. YOU SHOULD ALWAYS COVER ALL AREA OF JOBS. THIS APPLICATION IS NOT ONLY
  INTENDED TO TECH PEOPLE BUT TO EVERYONE. AND WHEN YOU NEED CLARIFICATION FROM MY SIDE YOU SHOULD ASK ME AND NOT
  ASSUME ANYTHING

