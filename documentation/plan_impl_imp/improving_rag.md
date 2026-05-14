Current RAG State — What I Found

  Source documents vs Pinecone records (chunking ratio ~2-7x):

  ┌─────────────────┬──────────────────────────────────────────┬──────────────────┬────────────┐
  │    Namespace    │               Source Docs                │ Pinecone Records │   Status   │
  ├─────────────────┼──────────────────────────────────────────┼──────────────────┼────────────┤
  │ taxonomy        │ 3,043 ESCO + 13,960 skills + 1,016 O*NET │ 40,044           │ Healthy    │
  ├─────────────────┼──────────────────────────────────────────┼──────────────────┼────────────┤
  │ role-templates  │ 1,016 docs                               │ 3,200            │ Healthy    │
  ├─────────────────┼──────────────────────────────────────────┼──────────────────┼────────────┤
  │ career-kb       │ 1,016 docs                               │ 2,858            │ Reasonable │
  ├─────────────────┼──────────────────────────────────────────┼──────────────────┼────────────┤
  │ swiss-eu-market │ 47 docs                                  │ 136              │ Thin       │
  ├─────────────────┼──────────────────────────────────────────┼──────────────────┼────────────┤
  │ market-reports  │ 18 docs                                  │ 102              │ Very thin  │
  └─────────────────┴──────────────────────────────────────────┴──────────────────┴────────────┘

  Root cause for the thin namespaces:

  swiss-eu-market has 1 document per EU country (only Eurostat ICT employment stats), 8 Swiss region wage docs, and 1 EU
   ranking overview. The Adzuna live job API integration is already coded but was skipped (needs API keys).

  market-reports has only 8 technology category documents (Stack Overflow tag counts + GitHub repo counts). There's no
  salary data, no regional breakdown, no hiring trend signals, and no industry reports.

  ---
  Approaches to Gather More Data

  Approach 1 — Activate What's Already Built (Quickest Win)

  The Adzuna integration in fetch_swiss_eu_market.py is fully implemented but needs credentials. It covers 9 EU
  countries × 5 role categories = up to 45 additional live job market documents. No code changes needed — just keys.

  Action: Add ADZUNA_APP_ID and ADZUNA_APP_KEY to .env, then rerun:
  cd agents && python -m scripts.fetch_swiss_eu_market --output-dir data/knowledge-base
  Free tier: 100 requests/day at developer.adzuna.com.

  ---
  Approach 2 — Stack Overflow Annual Developer Survey (Salary Data)

  The current market-reports data is community-size signals (question counts, repo counts) — not salary data. The SO
  Developer Survey (published annually, free CSV download) has salary by country × technology × years of experience.
  This would transform market-reports from usage metrics into actual compensation benchmarks.

  Data: ~65,000 respondents, salary by country, tech stack, role, YoE. File: ~30MB CSV.

  What to build: A new fetch_so_survey.py script that:
  1. Downloads the survey CSV from the Stack Overflow Insights archive
  2. Aggregates median salary by (country, primary_tech, YoE_band, role_type)
  3. Generates one document per country × role_type combination (~50-200 new docs)

  ---
  Approach 3 — Expand Eurostat Coverage (More EU Dimensions)

  fetch_swiss_eu_market.py currently pulls 3 Eurostat datasets. Eurostat has dozens more relevant ones, all free with no
   API key:

  ┌───────────────────┬──────────────────────────────────────────┐
  │      Dataset      │               What it adds               │
  ├───────────────────┼──────────────────────────────────────────┤
  │ isoc_ske_itsecac2 │ % workers needing ICT skills by country  │
  ├───────────────────┼──────────────────────────────────────────┤
  │ isoc_e_dii        │ Digital Intensity Index per enterprise   │
  ├───────────────────┼──────────────────────────────────────────┤
  │ earn_ses_pub1a    │ Earnings by occupation and ISCO code     │
  ├───────────────────┼──────────────────────────────────────────┤
  │ lfsa_egaps        │ Employment rate gaps (part-time, gender) │
  ├───────────────────┼──────────────────────────────────────────┤
  │ htec_sti_emp1     │ R&D employment by country                │
  ├───────────────────┼──────────────────────────────────────────┤
  │ road_eqr_carmot   │ (not relevant, just showing breadth)     │
  └───────────────────┴──────────────────────────────────────────┘

  Each dataset adds 27+ data points (one per EU country). Adding 3-4 new datasets to the existing
  fetch_swiss_eu_market.py would expand each country document from a 1-metric summary into a rich multi-dimensional
  profile, likely tripling the content per document.

  ---
  Approach 4 — Add OECD.Stat Data for Switzerland

  The OECD JSON API (stats.oecd.org/SDMX-JSON) covers 37 countries with deeper labour market data than Eurostat alone —
  especially valuable for Switzerland (not EU). Key datasets:
  - EARNINGS — hourly/annual earnings by occupation and industry
  - LFS_SEXAGE_I_R — labour force by age, gender, education
  - JOBQUALITY_SUMMARY — job quality indicators
  - EAG_GRAD_ENTR_RATE — graduation rates by field of study (pipeline signal)

  This is the best source for Swiss occupation-level salary benchmarks (which is currently just the BFS aggregate wage
  by region).

  ---
  Approach 5 — Job Board APIs for Live Vacancy Data

  Beyond Adzuna (which is coded already), two more job board APIs have free tiers and no auth complexity:

  RemoteOK (remoteok.com/api): No key, returns JSON of remote jobs with salary ranges. Focused on tech roles. ~100-300
  live listings at any time. Good for building a "remote work in Switzerland/EU" document set.

  Jobicy (jobicy.com/api/v0/jobs): Free, no auth, JSON, filters by region and category. Returns up to 50 jobs per
  request with salary ranges.

  Both complement Adzuna which covers on-site EU roles. A combined script could produce weekly-refreshed documents like
  "Remote Software Engineering Roles — Europe (live data, {date})".

  ---
  Approach 6 — Industry Reports as Structured Documents

  Several annual tech industry reports publish free downloadable data that can be parsed into KB documents:

  ┌───────────────────────────────┬──────────────┬─────────────────────────────────────┬──────────────────────────┐
  │            Report             │  Publisher   │               Content               │          Format          │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ CNCF Annual Survey            │ CNCF         │ Cloud native adoption, tools in use │ Free PDF + data          │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ State of DevOps               │ DORA/Google  │ DevOps practices and productivity   │ Free PDF                 │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ JetBrains Developer Ecosystem │ JetBrains    │ Tech adoption by category           │ Free PDF + data download │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ GitHub Octoverse              │ GitHub       │ Language trends, open-source        │ Free HTML/JSON           │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ State of JS / State of CSS    │ Sacha Greif  │ JS/CSS ecosystem usage              │ Free, JSON data          │
  ├───────────────────────────────┼──────────────┼─────────────────────────────────────┼──────────────────────────┤
  │ Thoughtworks Tech Radar       │ Thoughtworks │ Technology adoption curve           │ Free                     │
  └───────────────────────────────┴──────────────┴─────────────────────────────────────┴──────────────────────────┘

  These don't have live APIs but their structured data (often published as JSON or CSV alongside the report) can be
  parsed into 5-20 documents per report — roughly 50-100 new market-reports documents from this source alone.

  ---
  Approach 7 — Swiss-Specific Job Market Data (SECO + ch.ch)

  For the swiss-eu-market namespace specifically, Switzerland has official free data sources that aren't currently used:

  - SECO RAV (www.arbeit.swiss): The official Swiss job market registry. Has aggregate vacancy counts by canton and
  occupation. The SECO publishes monthly labour market reports as PDFs with structured data.
  - Swiss Federal Office for Migration (SEM): Admission statistics for work permits (B/L/C) by nationality, canton, and
  occupation. Important for users planning to relocate to Switzerland.
  - Lohnrechner / Salarium (salarium.ch): The BFS-backed salary calculator. Has an API endpoint (api.salarium.ch) that
  returns salary ranges by occupation code, canton, and education level. This is the most granular Swiss salary data
  available publicly.

  ---
  Approach 8 — Scheduled Auto-Refresh via Celery Beat

  The infrastructure for this already exists (the rag.ingest_* Celery tasks). What's missing is a Celery Beat schedule
  to:

  1. Weekly: re-fetch market_reports_real.json via fetch_market_reports.py (GitHub + SO stats change weekly)
  2. Monthly: re-fetch swiss_eu_market_real.json (Eurostat + Adzuna)
  3. Quarterly: re-run full seed for career-kb and role-templates

  This turns the KB from a static snapshot into a live-updating system — which matters especially for market-reports
  where data staleness directly triggers the retriever's [STALE] filter.

  ---
  Summary — Recommended Priority Order

  ┌──────────┬──────────────────────────────────────────────────────┬───────────────────────────────────┬──────────┐
  │ Priority │                       Approach                       │       Estimated New Records       │  Effort  │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 1        │ Activate Adzuna (already coded, need keys)           │ +45 docs → ~150 records           │ 1 hour   │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 2        │ SO Developer Survey salary CSV                       │ +50-200 docs → +300-1,000 records │ 1 day    │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 3        │ Expand Eurostat (3-4 more datasets)                  │ +100 docs → +300 records          │ half day │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 4        │ RemoteOK + Jobicy live job APIs                      │ +50-100 docs → +200 records       │ half day │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 5        │ Salarium.ch Swiss salary API                         │ +200 docs → +600 records          │ 1 day    │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 6        │ Industry report JSONs (State of JS, Octoverse, etc.) │ +50-100 docs → +300 records       │ 1 day    │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 7        │ OECD.Stat occupation earnings                        │ +30-50 docs → +150 records        │ 1 day    │
  ├──────────┼──────────────────────────────────────────────────────┼───────────────────────────────────┼──────────┤
  │ 8        │ Celery Beat auto-refresh schedule                    │ keeps existing data fresh         │ 2 hours  │
  └──────────┴──────────────────────────────────────────────────────┴───────────────────────────────────┴──────────┘

  Which would you like to start with? I can implement any of these — the Adzuna activation (approach 1) is the fastest
  since the code is already there, and the SO Developer Survey (approach 2) would give the biggest boost to
  market-reports quality.


 Gap 1 — Non-tech EU salary data
  - Original plan said: earn_ses_pub2q (ISCO occupation codes)
  - What was built: earn_ses_pub2i (ISCED education level) + earn_ses_pub2n (NACE industry sector)
  - Why it diverged: earn_ses_pub2q and all ISCO-based SES datasets return 404 from the Eurostat REST API — they're not
  accessible that way. The ISCED/NACE approach gives EU wage data that's genuinely useful but is organized by education
  level and industry rather than by occupation title directly.

  Gap 2 — Non-tech job demand
  - Done exactly as planned: Adzuna queries expanded to product manager, UX designer, financial analyst, marketing
  manager, project manager, business analyst, data analyst.

  Gap 3 — Finance/consulting/pharma
  - Original plan said: LinkedIn Salary Insights or Glassdoor (scraping/API deal)
  - What was built: BLS OES industry-specific data for NAICS 5200 (Finance), 5416 (Consulting), 3254 (Pharma), 6200
  (Healthcare), 5112 (Software), 5182 (Cloud) — US only, not EU
  - The EU side of this gap remains partially open: the NACE sector doc from Gap 1 covers J/K/M/C/Q sectors but only has
   hourly median rates, not role-level breakdowns

  Gap 4 — US non-tech salaries
  - Done: 23 SOC major groups from embedded BLS OES 2024 reference data, covering all occupation families including
  Management (13-0000), Business/Financial (13-0000), Legal (23-0000), Healthcare (29-0000), etc. — not limited to O*NET
   occupations

  The remaining real gap is EU role-level salary data for non-tech functions (product manager, financial analyst, etc.
  by country). No public API provides that at the resolution Glassdoor would. The closest available is the NACE sector
  doc (K=Finance, M=Consulting) but it's sector-median, not role-specific.

# Both namespaces in one call
  curl -X POST http://localhost:8000/api/v1/admin/kb/ingest \
    -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"doc_types": ["market_reports", "swiss_eu_market"]}'


