"""Fetch Asia-Pacific labour-market data for the global-market knowledge base.

Covers 14 countries across East Asia, South Asia, and South-East Asia:
  East Asia:       Japan (JP), China (CN), South Korea (KR), Hong Kong (HK)
  South Asia:      India (IN), Bangladesh (BD), Pakistan (PK), Sri Lanka (LK)
  South-East Asia: Singapore (SG), Philippines (PH), Malaysia (MY), Thailand (TH),
                   Indonesia (ID), Vietnam (VN)

Sources:
  - ILO ILOSTAT SDMX REST API (backbone for all countries, all job families)
  - Singapore Ministry of Manpower (MOM) / data.gov.sg — English, open licence
  - India MOSPI / PLFS Annual Report (public summaries, English)
  - Curated country context paragraphs covering ALL industries (not just tech)

Output:
  agents/data/knowledge-base/global_market_asia.json

Usage:
  python fetch_asia_market.py                        # all countries
  python fetch_asia_market.py --dry-run              # validate only
  python fetch_asia_market.py --no-cache             # bypass disk cache
  python fetch_asia_market.py --start-year 2020      # narrow year range
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ── Resolve sibling module ─────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from fetch_ilostat import (
    COUNTRY_META,
    REGION_COUNTRIES,
    fetch_ilo_data,
    build_ilo_documents,
)

# ── Output path ────────────────────────────────────────────────────────────────
_REPO_ROOT = _SCRIPTS_DIR.parent
_OUTPUT_FILE = _REPO_ROOT / "data" / "knowledge-base" / "global_market_asia.json"
_FETCHED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Singapore MOM URLs (open data, English) ───────────────────────────────────
_SG_MOM_EMPLOYMENT_URL = (
    "https://stats.mom.gov.sg/iMAS_PdfLibrary/mrsd_Demand_for_Labour.pdf"
)
_SG_CACHE_DIR = _REPO_ROOT / "data" / ".sg_cache"
_SG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Country context paragraphs ─────────────────────────────────────────────────
# Each context provides rich qualitative detail covering ALL sectors and job families,
# suitable for embedding alongside ILO quantitative data.

_COUNTRY_CONTEXT: dict[str, dict] = {
    "SG": {
        "overview": (
            "Singapore has one of the highest labour-force participation rates in Asia "
            "and a per-capita GDP exceeding USD 65,000. The economy spans financial "
            "services, wholesale and retail trade, manufacturing (semiconductors, "
            "pharmaceuticals, precision engineering), transport and logistics, "
            "information and communications, construction, healthcare, and food services. "
            "The Ministry of Manpower's Skills Framework covers more than 35 industry "
            "sectors and maps competencies for occupations from PMETs (Professionals, "
            "Managers, Executives, Technicians) through to service workers, operators, "
            "and craftsmen. Median gross monthly income for full-time employed residents "
            "was SGD 5,070 (≈ USD 3,750) in 2023. Resident employment grew 2.1% year-on-"
            "year, led by professional services, healthcare, and F&B. The SkillsFuture "
            "programme subsidises mid-career reskilling across all industries. Foreign "
            "talent policy (Employment Pass / S Pass / Work Permit tiers) shapes labour "
            "supply in construction, marine, domestic work, and skilled professional roles. "
            "Key shortage areas: nursing and allied health, data engineering, "
            "cybersecurity, precision engineering, early-childhood education."
        ),
        "industries": [
            {
                "name": "Financial Services & Insurance",
                "context": (
                    "Singapore is the third-largest foreign-exchange trading centre globally "
                    "and home to MAS-regulated banks, asset managers, and insurance firms. "
                    "Occupations include traders, risk analysts, compliance officers, "
                    "actuaries, wealth managers, and operations staff. Average monthly salary "
                    "for finance professionals: SGD 7,000-14,000. Strong demand for ESG "
                    "finance and digital-banking roles."
                ),
                "job_families": ["Finance", "Risk & Compliance", "Insurance", "Investment Management"],
            },
            {
                "name": "Manufacturing (Semiconductor & Electronics)",
                "context": (
                    "Singapore hosts wafer-fab clusters for TSMC, GlobalFoundries, and "
                    "Micron, plus electronics assembly and precision-engineering hubs. "
                    "Occupations: process engineers, equipment technicians, quality "
                    "inspectors, supply-chain planners, production supervisors. Monthly "
                    "wages range from SGD 2,500 for technicians to SGD 9,000+ for senior "
                    "engineers. Heavy investment in Industry 4.0 automation and smart "
                    "factory operators."
                ),
                "job_families": ["Engineering", "Manufacturing", "Quality Assurance", "Operations"],
            },
            {
                "name": "Healthcare & Social Services",
                "context": (
                    "Public-sector hospitals (MOH Holdings), private hospitals, polyclinics, "
                    "and a fast-growing eldercare sector. Nursing remains the single largest "
                    "healthcare occupation, with persistent shortages. Allied health roles "
                    "(physiotherapy, occupational therapy, pharmacy, radiology) are well-"
                    "compensated. Social workers, eldercare aides, and early-childhood "
                    "educators are high-growth. Average monthly salary: SGD 3,200 (aide) "
                    "to SGD 8,500 (specialist physician)."
                ),
                "job_families": ["Nursing", "Allied Health", "Medicine", "Social Work", "Eldercare"],
            },
            {
                "name": "Transport, Logistics & Maritime",
                "context": (
                    "PSA Singapore is one of the world's busiest container ports. The "
                    "maritime cluster employs 170,000 workers in ship management, offshore "
                    "and marine engineering, bunkering, and port operations. Civil aviation "
                    "at Changi supports aircraft maintenance, ground handling, and logistics. "
                    "Warehousing and last-mile delivery are digitising rapidly. Key roles: "
                    "logistics coordinators, port operations planners, marine surveyors, "
                    "freight forwarders, airline operations specialists."
                ),
                "job_families": ["Logistics", "Maritime", "Aviation", "Supply Chain", "Port Operations"],
            },
            {
                "name": "Retail, F&B & Tourism",
                "context": (
                    "Retail and food-and-beverage account for roughly 280,000 workers. "
                    "Tourism (Integrated Resorts, MICE, cultural attractions) supports "
                    "hospitality and events roles. Occupations: retail sales associates, "
                    "baristas, chefs, housekeepers, event coordinators, hotel managers. "
                    "Wages are lower (SGD 1,800-3,500) with a heavy reliance on work-permit "
                    "holders. Government productivity grants encourage automation in F&B."
                ),
                "job_families": ["Hospitality", "Food & Beverage", "Retail", "Tourism", "Events"],
            },
            {
                "name": "Construction & Real Estate",
                "context": (
                    "Large public-housing (HDB) and infrastructure pipelines sustain "
                    "construction demand. Major occupations: site supervisors, quantity "
                    "surveyors, civil and structural engineers, M&E engineers, safety "
                    "officers, and foreign construction workers (Work Permit tier). "
                    "Building Information Modelling (BIM) adoption is mandated for large "
                    "projects. Real estate agents (CEA-licensed) serve a buoyant property "
                    "market with median private-property prices of SGD 1,800 psf."
                ),
                "job_families": ["Civil Engineering", "Construction", "Real Estate", "Project Management"],
            },
            {
                "name": "Education & Training",
                "context": (
                    "MOE schools, polytechnics, autonomous universities (NUS, NTU, SMU, "
                    "SUTD), and private continuing-education providers. Teaching roles span "
                    "primary, secondary, junior-college, ITE, polytechnic, and university. "
                    "Corporate trainers and SkillsFuture-accredited instructors are growing. "
                    "Average monthly salary: SGD 3,800 (primary teacher) to SGD 10,000+ "
                    "(associate professor). Demand for STEM teachers and special-education "
                    "specialists outpaces supply."
                ),
                "job_families": ["Teaching", "Training & Development", "Educational Administration"],
            },
        ],
        "salary_context": (
            "Singapore statutory minimum wage applies only to specific sectors (e.g., "
            "cleaning, security, landscape under Progressive Wage Model). Median resident "
            "wage: SGD 5,070/month (2023). 25th percentile: SGD 2,800; 75th percentile: "
            "SGD 9,500. Strong CPF contribution (employer 17%, employee 20%) adds ~37% "
            "on top of gross salary for retirement and healthcare. Wages are among the "
            "highest in South-East Asia across all skill levels."
        ),
    },

    "IN": {
        "overview": (
            "India is the world's fifth-largest economy and the most populous country, "
            "with a labour force exceeding 500 million workers. Agriculture employs about "
            "46% of the workforce but contributes only 17% of GDP, highlighting a large "
            "informal rural sector alongside the formal urban economy. Key industries "
            "include IT and business-process outsourcing, manufacturing (textiles, auto, "
            "steel, pharmaceuticals), construction, retail trade, financial services, "
            "education, and healthcare. The Periodic Labour Force Survey (PLFS) 2022-23 "
            "reports an urban unemployment rate of 6.6% and a labour-force participation "
            "rate of 42% (urban). Average monthly earnings vary widely: INR 8,000-12,000 "
            "for informal sector workers, INR 25,000-80,000 for formal-sector professionals. "
            "The National Skills Qualifications Framework (NSQF) governs skill certifications "
            "across 37 sector skill councils, covering agriculture, automotive, BFSI, "
            "construction, electronics, food processing, garments, healthcare, hospitality, "
            "logistics, media, and more. India's 'Make in India', PLI (Production-Linked "
            "Incentive) schemes, and Digital India initiatives are reshaping labour demand."
        ),
        "industries": [
            {
                "name": "Agriculture, Forestry & Fishing",
                "context": (
                    "India is the world's second-largest producer of wheat, rice, fruits, "
                    "and vegetables. Key occupations: farm labourers, irrigation workers, "
                    "horticulture workers, fishers, and agricultural supervisors. Wages in "
                    "agriculture average INR 350-500 per day under MGNREGS (rural guarantee "
                    "scheme). Agri-tech and contract farming are gradually formalising roles "
                    "such as precision-agriculture technicians and cold-chain logistics staff."
                ),
                "job_families": ["Agriculture", "Horticulture", "Fisheries", "Forestry"],
            },
            {
                "name": "Textile, Apparel & Garments",
                "context": (
                    "India is the world's second-largest textile exporter. The industry "
                    "employs 45 million workers directly, predominantly women in handloom, "
                    "power-loom, and garment-stitching roles. Key occupations: sewing "
                    "machine operators, fabric cutters, quality controllers, dyeing "
                    "technicians, merchandisers, and fashion designers. Average monthly "
                    "wages: INR 8,000-14,000 for factory workers; INR 25,000-50,000 for "
                    "designers and buyers."
                ),
                "job_families": ["Garment Production", "Fashion Design", "Textile Engineering", "Merchandising"],
            },
            {
                "name": "Construction & Infrastructure",
                "context": (
                    "India's infrastructure push (roads, metros, smart cities, affordable "
                    "housing) sustains 50+ million construction workers, mostly informal. "
                    "Key occupations: masons, carpenters, plumbers, electricians, civil "
                    "engineers, safety supervisors, and project managers. The Construction "
                    "Sector Skill Council certifies workers. Wages: INR 400-600/day "
                    "for skilled tradespeople; INR 50,000-120,000/month for engineers."
                ),
                "job_families": ["Civil Engineering", "Construction Trades", "Project Management", "Real Estate"],
            },
            {
                "name": "Healthcare & Pharmaceuticals",
                "context": (
                    "India trains the world's largest number of doctors and nurses and is "
                    "a global hub for generic pharmaceutical manufacturing. Key occupations: "
                    "MBBS physicians, specialist doctors, nurses (ANM/GNM/BSc), pharmacists, "
                    "medical-lab technicians, and pharma quality-assurance analysts. Monthly "
                    "salaries range from INR 15,000 (ANM nurse) to INR 150,000+ (specialist "
                    "physician). Medical tourism and government Ayushman Bharat scheme are "
                    "expanding rural healthcare jobs."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Allied Health", "Life Sciences"],
            },
            {
                "name": "IT & Business Process Outsourcing",
                "context": (
                    "India's IT-BPM industry employs 5.4 million professionals and exports "
                    "USD 245 billion in services annually. While heavily tech-oriented, the "
                    "sector also creates large numbers of non-tech roles: HR business "
                    "partners, legal counsels, finance analysts, facilities managers, "
                    "training specialists, and customer-service representatives. Average "
                    "salary: INR 350,000-700,000/year for fresh graduates; INR 1,500,000+ "
                    "for senior architects and delivery managers."
                ),
                "job_families": ["Software Engineering", "Business Analysis", "HR", "Finance", "Customer Service"],
            },
            {
                "name": "Financial Services & Banking",
                "context": (
                    "India's banking system (public sector, private banks, NBFCs, payments "
                    "banks) employs 1.5 million formally. The insurance sector and mutual "
                    "fund industry are rapidly growing. Key roles: bank officers, loan "
                    "officers, insurance agents, wealth managers, actuaries, compliance "
                    "officers. Jan Dhan financial inclusion has created rural banking "
                    "correspondence jobs. Average salary: INR 30,000-80,000/month."
                ),
                "job_families": ["Banking", "Insurance", "Investments", "Compliance", "Microfinance"],
            },
            {
                "name": "Education",
                "context": (
                    "With 1.5 million schools and 1,000+ universities, education is India's "
                    "second-largest employer. Key occupations: primary and secondary school "
                    "teachers, college lecturers, private tutor, ed-tech instructors, and "
                    "school administrators. Government school teacher salaries: INR 30,000-"
                    "60,000/month. Private ed-tech (BYJU'S, Unacademy) created 50,000+ "
                    "content and teaching roles before sector consolidation in 2023-24."
                ),
                "job_families": ["Teaching", "Academic Research", "Educational Administration", "Ed-Tech"],
            },
            {
                "name": "Retail & E-commerce",
                "context": (
                    "Organised retail (Reliance, DMart, BigBasket) and e-commerce "
                    "(Flipkart, Amazon India, Meesho) have grown rapidly. Key occupations: "
                    "sales associates, store managers, warehouse pickers/packers, delivery "
                    "executives (gig), category managers, and supply-chain analysts. "
                    "Delivery gig workers earn INR 15,000-25,000/month. Formal retail "
                    "store staff earn INR 12,000-30,000/month."
                ),
                "job_families": ["Retail", "E-commerce", "Supply Chain", "Logistics", "Gig Work"],
            },
        ],
        "salary_context": (
            "India has no universal statutory minimum wage; national floor wage is "
            "INR 178/day (2023). State minimum wages vary from INR 6,000 to INR 18,000/month "
            "depending on skill category and state. Urban formal-sector median monthly "
            "earnings: approximately INR 22,000-28,000. Significant wage disparity between "
            "informal (60% of workforce) and formal sectors."
        ),
    },

    "JP": {
        "overview": (
            "Japan is the world's third-largest economy with a highly educated, ageing "
            "workforce. Labour-force participation is 63%, with women's participation "
            "rising steadily. Key sectors: automotive and manufacturing (Toyota, Honda, "
            "Sony ecosystem), financial services, retail and distribution, healthcare "
            "and eldercare, construction, agriculture, and public administration. "
            "Unemployment remains exceptionally low at 2.5-3.0%. Average monthly cash "
            "earnings: JPY 328,000 (≈ USD 2,200) across all industries. Critical labour "
            "shortages in nursing, eldercare, agriculture, construction, and trucking "
            "have driven immigration policy reforms (Specified Skilled Worker status). "
            "Keidanren member companies offer new-graduate hiring (shukatsu) every April "
            "across all industries."
        ),
        "industries": [
            {
                "name": "Automotive & Manufacturing",
                "context": (
                    "Japan's automotive industry (Toyota, Honda, Nissan, Mazda, Subaru) "
                    "employs 5.5 million directly and indirectly. EV transition is driving "
                    "demand for battery engineers and software-defined-vehicle specialists. "
                    "Production-line workers (monozukuri craftspeople), quality engineers, "
                    "and supply-chain coordinators remain core. Monthly wages: JPY 220,000 "
                    "(assembly operator) to JPY 700,000+ (senior engineer)."
                ),
                "job_families": ["Manufacturing", "Engineering", "Quality Assurance", "Supply Chain"],
            },
            {
                "name": "Healthcare & Eldercare",
                "context": (
                    "Japan's super-ageing society (29% of population over 65) creates "
                    "acute demand for care workers (kaigo), nurses, physiotherapists, "
                    "and occupational therapists. The government fast-tracks immigration "
                    "for EPA and Specified Skilled Worker care roles. Monthly salaries: "
                    "JPY 200,000-280,000 for care workers; JPY 400,000-650,000 for "
                    "nurses; JPY 600,000+ for physicians."
                ),
                "job_families": ["Eldercare", "Nursing", "Allied Health", "Medicine"],
            },
            {
                "name": "Retail, Convenience & F&B",
                "context": (
                    "Seven-Eleven Japan (21,000 stores), FamilyMart, and Lawson define "
                    "Japan's convenience-retail sector. Restaurant chains, izakayas, "
                    "and fast food employ millions of part-time workers (arubaito). "
                    "Key roles: store clerks, kitchen staff, delivery drivers, food "
                    "hygiene managers. Wages: JPY 1,000-1,200/hour for part-time; "
                    "JPY 220,000-320,000/month for full-time store managers."
                ),
                "job_families": ["Retail", "Food & Beverage", "Hospitality"],
            },
            {
                "name": "Construction & Civil Engineering",
                "context": (
                    "Infrastructure renewal (earthquake resistance upgrades, Shinkansen "
                    "expansion, 2025 Osaka Expo construction) sustains high demand for "
                    "civil engineers, rebar workers, plasterers, and construction managers. "
                    "The industry faces a 30% shortage of skilled construction workers. "
                    "BIM adoption and prefabricated construction are growing. Average "
                    "monthly salary: JPY 280,000-450,000 for engineers."
                ),
                "job_families": ["Civil Engineering", "Construction Trades", "Architecture", "Project Management"],
            },
            {
                "name": "Agriculture & Fisheries",
                "context": (
                    "Japan's food self-sufficiency target underpins support for rice "
                    "farming, vegetables, fruit orchards, livestock, and fishing. Ageing "
                    "of farmers (average age 68) creates succession challenges and opens "
                    "doors for young agricultural entrepreneurs (shintoku-farmer scheme). "
                    "Specified Skilled Worker status applies to agriculture, horticulture, "
                    "dairy, and fisheries. Monthly wages: JPY 160,000-230,000."
                ),
                "job_families": ["Farming", "Fisheries", "Agri-tech", "Food Processing"],
            },
            {
                "name": "Finance & Insurance",
                "context": (
                    "Japan's three megabanks (MUFG, SMBC, Mizuho) plus thousands of "
                    "regional banks, securities firms, and insurers employ 1.5 million. "
                    "Key roles: loan officers, securities analysts, insurance underwriters, "
                    "trust administrators, and fintech product managers. Monthly salary: "
                    "JPY 280,000-350,000 entry-level; JPY 700,000+ for senior bankers."
                ),
                "job_families": ["Banking", "Insurance", "Investment", "Compliance"],
            },
        ],
        "salary_context": (
            "Japan's 2024 minimum wage rose to JPY 1,004/hour (national average). "
            "Tokyo minimum: JPY 1,113/hour. Annual salary norms: JPY 3,000,000-4,500,000 "
            "for new graduates; JPY 5,000,000-8,000,000 for mid-career professionals. "
            "Seniority-based pay is giving way to performance-based systems under "
            "kishida-era labour reforms."
        ),
    },

    "CN": {
        "overview": (
            "China is the world's second-largest economy with a labour force of 780 "
            "million. Key industries: manufacturing (electronics, steel, automobiles, "
            "textiles), construction, agriculture, retail and wholesale trade, "
            "financial services, education, healthcare, and logistics. The hukou "
            "system creates a 300-million-strong migrant-worker population that powers "
            "manufacturing, construction, and service industries. Average urban wage: "
            "CNY 6,500/month (2023). Rural-to-urban migration continues though slowing. "
            "Priority sectors under 'Made in China 2025' and 'Dual Circulation': "
            "advanced manufacturing, new-energy vehicles, semiconductors, biomedicine. "
            "Large public-sector employer base (government, SOEs, education, healthcare) "
            "accounting for 50 million formal jobs."
        ),
        "industries": [
            {
                "name": "Manufacturing & Industrial Production",
                "context": (
                    "China produces 28% of global manufactured output. Key sub-sectors: "
                    "electronics assembly (Foxconn employs 1.2 million), steel and metals, "
                    "automotive (BYD, SAIC), chemical industry, and furniture. Factory "
                    "workers, assembly-line operators, quality inspectors, and forklift "
                    "drivers are the largest occupational groups. Average factory wage: "
                    "CNY 4,500-6,000/month in coastal provinces; CNY 3,000-4,500 inland."
                ),
                "job_families": ["Manufacturing", "Quality Control", "Industrial Engineering", "Operations"],
            },
            {
                "name": "Construction & Real Estate",
                "context": (
                    "Despite a property-sector slowdown since 2022, construction still "
                    "employs 50+ million migrant workers. Roles: construction labourers, "
                    "bricklayers, scaffolders, civil engineers, and site managers. "
                    "New construction is shifting toward infrastructure (high-speed rail, "
                    "urban metro) rather than residential. Monthly wages: CNY 5,000-8,000 "
                    "for skilled tradespeople."
                ),
                "job_families": ["Construction", "Civil Engineering", "Real Estate", "Urban Planning"],
            },
            {
                "name": "Retail, E-commerce & Logistics",
                "context": (
                    "Alibaba (Taobao/Tmall), JD.com, and Pinduoduo collectively employ "
                    "millions of warehouse, delivery (kuaidi), and customer-service staff. "
                    "Live-commerce (douyin/TikTok) created 15 million influencer-related "
                    "jobs. Delivery riders earn CNY 6,000-10,000/month; warehouse packers "
                    "CNY 4,000-6,000/month."
                ),
                "job_families": ["Logistics", "Delivery", "E-commerce", "Retail"],
            },
            {
                "name": "Education & Training",
                "context": (
                    "China's education system employs 18 million teachers from preschool "
                    "to university. The 'Double Reduction' policy (2021) restricted "
                    "private tutoring for K-12 subjects, displacing 1 million tutors but "
                    "creating vocational-training demand. Public school teachers earn "
                    "CNY 5,000-9,000/month. University professors: CNY 8,000-20,000+/month."
                ),
                "job_families": ["Teaching", "Academic Research", "Vocational Training"],
            },
            {
                "name": "Healthcare & Biomedicine",
                "context": (
                    "China is expanding rural health infrastructure and hospital capacity. "
                    "Key roles: GPs (全科医生), specialist physicians, nurses (registered/LPN), "
                    "pharmacists, and medical-device technicians. Salary: CNY 4,000-8,000 "
                    "(nurse) to CNY 20,000+ (specialist surgeon in tier-1 city). Biotech "
                    "and pharmaceutical R&D is growing in Shanghai, Beijing, and Suzhou "
                    "clusters."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Life Sciences", "Medical Devices"],
            },
            {
                "name": "Agriculture & Food Production",
                "context": (
                    "Agriculture employs 25% of China's labour force, predominantly "
                    "small-plot farmers, aquaculture workers, and livestock farmers. "
                    "Collective farming contracts and land-transfer consolidation are "
                    "creating larger agri-business operations. Agri-tech companies "
                    "(drone spraying, precision irrigation) employ technicians. "
                    "Average agricultural worker monthly income: CNY 2,500-4,000."
                ),
                "job_families": ["Farming", "Aquaculture", "Agri-tech", "Food Processing"],
            },
        ],
        "salary_context": (
            "China's monthly minimum wage varies by province and city tier: "
            "Shanghai CNY 2,690/month; Beijing CNY 2,420/month; inland cities "
            "CNY 1,500-1,900/month. Urban average monthly salary: CNY 6,508 (2022). "
            "Social insurance contributions (pension, medical, unemployment, housing "
            "fund) add 30-40% on top of gross salary."
        ),
    },

    "KR": {
        "overview": (
            "South Korea is a high-income OECD economy with a GDP per capita of "
            "USD 33,000. Major industries: electronics and semiconductors (Samsung, SK "
            "Hynix), automotive (Hyundai, Kia), steel and shipbuilding (POSCO, "
            "Hyundai Heavy), petrochemicals, retail (E-Mart, Lotte), healthcare, "
            "education, and K-content (entertainment, gaming, streaming). Employment "
            "rate: 62.6%. Youth unemployment remains structurally elevated at 6-7%. "
            "Average monthly wage: KRW 3,650,000 (≈ USD 2,750). The conglomerate "
            "(chaebol) employment system dominates white-collar hiring cycles. "
            "Gig economy and platform work are rapidly expanding in delivery, ride-"
            "hailing, and content creation."
        ),
        "industries": [
            {
                "name": "Semiconductor & Electronics",
                "context": (
                    "Samsung Electronics and SK Hynix account for >50% of global DRAM "
                    "production. Fab engineers, process developers, equipment maintenance "
                    "technicians, and supply-chain managers are in perennial demand. "
                    "Monthly salary: KRW 3,500,000-5,500,000 for engineers; "
                    "KRW 7,000,000+ for senior researchers."
                ),
                "job_families": ["Semiconductor Engineering", "Electronics Design", "Manufacturing", "R&D"],
            },
            {
                "name": "Healthcare & Pharmaceutical",
                "context": (
                    "South Korea's national health insurance (NHIS) funds universal "
                    "coverage. Physicians, nurses, and pharmacists are well-compensated "
                    "relative to OECD averages. K-beauty and pharmaceutical exports "
                    "create R&D and regulatory affairs roles. Average monthly wage: "
                    "KRW 2,800,000 (registered nurse) to KRW 8,000,000+ (specialist physician)."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Biotech R&D"],
            },
            {
                "name": "Retail & Distribution",
                "context": (
                    "Korea has one of the world's highest e-commerce penetration rates "
                    "(Coupang is the dominant player). Large offline retailers (Emart, "
                    "Homeplus, Lotte Mart) and convenience store chains (CU, GS25) employ "
                    "millions. Key roles: store cashiers, online order pickers, logistics "
                    "couriers, category buyers, visual merchandisers. Coupang's delivery "
                    "workers ('Coupang Man') earn KRW 3,000,000-4,500,000/month."
                ),
                "job_families": ["Retail", "E-commerce", "Logistics", "Delivery"],
            },
            {
                "name": "Construction & Architecture",
                "context": (
                    "Active infrastructure pipeline: GTX rapid transit in Seoul metro "
                    "area, semiconductor mega-fabs in Pyeongtaek, and housing supply "
                    "expansion. Key roles: civil engineers, architects, BIM coordinators, "
                    "safety managers, and concrete workers. Monthly salary: KRW 2,800,000-"
                    "5,000,000 for engineers; KRW 1,900,000-2,500,000 for skilled trades."
                ),
                "job_families": ["Civil Engineering", "Architecture", "Construction Management"],
            },
            {
                "name": "Education & Private Tutoring (Hagwon)",
                "context": (
                    "South Korea's private education (hagwon) market is the world's largest "
                    "relative to GDP. Over 80,000 hagwons employ English teachers, math "
                    "tutors, music instructors, and cram-school administrators. Native "
                    "English teachers earn KRW 2,200,000-3,500,000/month. Public school "
                    "teachers earn KRW 2,700,000-5,500,000/month with government pension."
                ),
                "job_families": ["Teaching", "Private Tutoring", "Educational Administration"],
            },
            {
                "name": "Entertainment, Media & Gaming",
                "context": (
                    "K-pop, K-drama, and Korean gaming (Nexon, Krafton, NCsoft) generate "
                    "significant employment in content creation, production, game development, "
                    "and talent management. K-content exports exceed USD 12 billion. "
                    "Roles: idol trainees, drama directors, writers, 3D artists, game "
                    "programmers, and social-media managers. Monthly salary: KRW 2,000,000-"
                    "6,000,000 depending on role and seniority."
                ),
                "job_families": ["Entertainment", "Media Production", "Game Development", "Content Creation"],
            },
        ],
        "salary_context": (
            "South Korea's 2024 minimum wage: KRW 9,860/hour (≈ USD 7.40). "
            "Average monthly salary across all industries: KRW 3,650,000. "
            "Chaebol companies pay 30-50% above the national average. "
            "SMEs and small businesses pay near minimum-wage levels. "
            "Regular vs. non-regular (contract) employee wage gap is approximately 30%."
        ),
    },

    "PH": {
        "overview": (
            "The Philippines is a lower-middle-income economy with a GDP per capita "
            "of USD 3,500. Key sectors: business-process outsourcing (BPO) and IT, "
            "agriculture (rice, coconut, sugar, banana), manufacturing (electronics "
            "assembly, garments), construction, retail and wholesale trade, healthcare, "
            "and OFW (overseas Filipino worker) remittances (USD 36 billion/year). "
            "Unemployment: 4.8%; underemployment: 14%. Average monthly wage in "
            "non-agriculture: PHP 18,000-22,000. The TESDA vocational system certifies "
            "workers across 130+ qualifications including automotive, electronics, "
            "culinary arts, beauty care, and healthcare. OFW deployment covers over "
            "170 countries in domestic work, nursing, maritime, and construction."
        ),
        "industries": [
            {
                "name": "BPO & Shared Services",
                "context": (
                    "The Philippines is the world's top voice-BPO destination and second-"
                    "largest IT-BPM market. Key roles: customer service representatives, "
                    "technical support agents, healthcare information specialists, finance "
                    "and accounting BPO staff, and legal process outsourcing associates. "
                    "Average monthly salary: PHP 18,000-35,000."
                ),
                "job_families": ["Customer Service", "Finance BPO", "Healthcare BPO", "IT Support"],
            },
            {
                "name": "Agriculture & Fisheries",
                "context": (
                    "Agriculture employs 25% of the workforce. Major crops: rice, corn, "
                    "coconut, sugarcane, banana (Cavendish for export). Aquaculture and "
                    "fishing support millions of coastal households. Key roles: farm workers, "
                    "irrigation technicians, fishers, and post-harvest handlers. Daily "
                    "agricultural wage: PHP 400-500."
                ),
                "job_families": ["Farming", "Fisheries", "Agri-processing"],
            },
            {
                "name": "Healthcare & Nursing Export",
                "context": (
                    "The Philippines trains and deploys more internationally mobile nurses "
                    "than any other country. Domestic roles: hospital nurses (PHP 15,000-"
                    "25,000/month), government-employed nurses (PHP 35,000+), caregivers, "
                    "midwives, and medical-lab technicians. Nursing boards for US NCLEX, "
                    "UK NMC, and Gulf DHP are widely taken."
                ),
                "job_families": ["Nursing", "Allied Health", "Caregiving", "Midwifery"],
            },
            {
                "name": "Construction & Engineering",
                "context": (
                    "BBM infrastructure programme ('Build Better More') funds expressways, "
                    "airports, and urban rail. Demand for civil engineers, structural "
                    "engineers, architects, licensed master plumbers, and NCII-certified "
                    "construction workers is high. Average monthly salary: PHP 25,000-60,000 "
                    "for engineers; PHP 600-800/day for skilled construction workers."
                ),
                "job_families": ["Civil Engineering", "Architecture", "Construction Trades"],
            },
            {
                "name": "Maritime & Seafaring",
                "context": (
                    "The Philippines supplies 25% of the world's seafarers. MARINA-licensed "
                    "officers and ratings work on container ships, tankers, cruise lines, "
                    "and bulk carriers. Key roles: deck officers, marine engineers, ratings "
                    "(AB seamen), ship cooks, and cruise ship hospitality crew. Monthly "
                    "allotments: USD 1,000-4,000 depending on rank and vessel type."
                ),
                "job_families": ["Maritime", "Marine Engineering", "Hospitality (Cruise)"],
            },
        ],
        "salary_context": (
            "Regional minimum wages (2024): NCR (Metro Manila) PHP 610/day; "
            "other regions PHP 383-533/day. Average non-farm monthly wage: PHP 18,400. "
            "BPO and IT-BPM wages are 20-50% above the national average. "
            "OFW remittances represent 9.4% of GDP and often exceed domestic wage income."
        ),
    },

    "MY": {
        "overview": (
            "Malaysia is an upper-middle-income economy with a GDP per capita of "
            "USD 12,500. Key industries: oil and gas (Petronas), electronics and "
            "semiconductors (Penang 'Silicon Valley of the East'), palm oil and "
            "rubber agriculture, financial services, manufacturing, construction, "
            "tourism, and healthcare. Unemployment: 3.3%. Average monthly wage: "
            "MYR 3,200 (USD 680). Foreign migrant workers (3-4 million) are vital "
            "in construction, agriculture, and manufacturing. HRDF-accredited "
            "skills training covers manufacturing, services, and agriculture."
        ),
        "industries": [
            {
                "name": "Oil, Gas & Energy",
                "context": (
                    "Petronas and its contractors employ 45,000 directly; the broader "
                    "oil-and-gas cluster 150,000+. Key roles: petroleum engineers, "
                    "subsea engineers, drilling engineers, HSE officers, plant operators, "
                    "and maintenance technicians. Average monthly salary: MYR 5,000-12,000 "
                    "for engineers; MYR 3,000-5,000 for technicians and operators."
                ),
                "job_families": ["Petroleum Engineering", "Energy", "HSE", "Plant Operations"],
            },
            {
                "name": "Electronics & Semiconductor",
                "context": (
                    "Penang hosts backend semiconductor packaging for Intel, Infineon, "
                    "and Bosch. Key roles: process engineers, equipment engineers, "
                    "production operators, quality technicians, and supply-chain planners. "
                    "Average monthly salary: MYR 3,500-7,000 for engineers; MYR 1,800-2,500 "
                    "for operators."
                ),
                "job_families": ["Semiconductor", "Electronics Manufacturing", "Quality Engineering"],
            },
            {
                "name": "Palm Oil & Agriculture",
                "context": (
                    "Malaysia is the world's second-largest palm oil producer. Estates employ "
                    "harvesting workers, tractor operators, and agronomists; mills employ "
                    "process operators, maintenance mechanics, and quality assurers. "
                    "Average wages: MYR 1,500-2,200 for estate workers (mostly migrants); "
                    "MYR 3,000-5,000 for agri-engineers and plantation managers."
                ),
                "job_families": ["Agronomy", "Agricultural Operations", "Plantation Management", "Food Processing"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Kuala Lumpur is a growing Islamic finance hub (Maybank, CIMB, Hong "
                    "Leong). Key roles: financial analysts, Islamic finance scholars, "
                    "risk managers, insurance underwriters, and branch banking staff. "
                    "Average monthly salary: MYR 4,000-10,000 for professionals."
                ),
                "job_families": ["Banking", "Islamic Finance", "Insurance", "Investment"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Malaysia targets 26 million tourists (2024 Visit Malaysia Year). "
                    "Roles: hotel front-desk, F&B staff, tour guides, travel agents, "
                    "event planners, and convention centre staff. Average monthly salary: "
                    "MYR 1,800-3,000 for line staff; MYR 4,000-7,000 for hotel managers."
                ),
                "job_families": ["Hospitality", "Tourism", "Food & Beverage", "Event Management"],
            },
        ],
        "salary_context": (
            "Malaysia minimum wage: MYR 1,500/month (2023, universal). "
            "Average monthly gross wage: MYR 3,200. Median monthly wage: MYR 2,600. "
            "EPF (Employees Provident Fund) contribution: employer 13%, employee 11%. "
            "Wage growth averaging 4-5% annually since 2020."
        ),
    },

    "TH": {
        "overview": (
            "Thailand is an upper-middle-income economy with GDP per capita of "
            "USD 7,100. Key industries: automotive (Toyota, Honda, Isuzu assembly "
            "hub), electronics, tourism and hospitality, agriculture (rice, rubber, "
            "cassava, sugarcane, seafood processing), financial services, and "
            "healthcare (medical tourism). Unemployment: 1.1% (very low). Average "
            "monthly wage: THB 15,000-17,000. Foreign migrant workers (3 million, "
            "mostly Myanmar, Lao, Cambodian) are concentrated in agriculture, "
            "fisheries, construction, and domestic work."
        ),
        "industries": [
            {
                "name": "Automotive & Auto Parts",
                "context": (
                    "Thailand is 'the Detroit of Asia' for pickup trucks and EVs, "
                    "producing 1.8 million vehicles annually. Key roles: production "
                    "workers (assembly, welding, painting), quality engineers, tooling "
                    "technicians, and supply-chain coordinators. Average monthly wage: "
                    "THB 12,000-18,000 for skilled workers; THB 30,000-60,000 for engineers."
                ),
                "job_families": ["Automotive Manufacturing", "Engineering", "Quality Assurance", "Supply Chain"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Tourism contributes 11% of GDP with 28 million foreign visitors (2023). "
                    "Roles: hotel staff, tour guides, spa therapists, restaurant workers, "
                    "MICE event coordinators. Average monthly wage: THB 12,000-20,000 "
                    "for line staff; THB 30,000-60,000 for hotel GMs."
                ),
                "job_families": ["Hospitality", "Tourism", "Wellness & Spa", "F&B"],
            },
            {
                "name": "Agriculture & Agro-processing",
                "context": (
                    "Thailand is one of the world's top 5 rice exporters and a major "
                    "shrimp and tuna processor. Key roles: rice farmers, rubber tappers, "
                    "poultry processors, seafood-factory workers, and cold-chain logistics "
                    "staff. Average agricultural daily wage: THB 350-400."
                ),
                "job_families": ["Farming", "Fisheries", "Food Processing", "Logistics"],
            },
            {
                "name": "Healthcare & Medical Tourism",
                "context": (
                    "Thailand attracts 1 million+ medical tourists annually (Bumrungrad, "
                    "Bangkok Hospital group). Doctors, nurses, medical translators, and "
                    "hospital administrators work in both public-sector MOPH and private "
                    "hospitals. Average monthly salary: THB 20,000-35,000 for nurses; "
                    "THB 80,000-200,000 for specialist physicians."
                ),
                "job_families": ["Medicine", "Nursing", "Allied Health", "Hospital Administration"],
            },
        ],
        "salary_context": (
            "Thailand minimum wage: THB 330-400/day (regional variation, 2024). "
            "Average monthly wage: THB 15,400. Bangkok wages are 25-40% higher "
            "than national average. Social Security Fund contributions 5% employee, "
            "5% employer."
        ),
    },

    "ID": {
        "overview": (
            "Indonesia is South-East Asia's largest economy (GDP USD 1.3 trillion) "
            "with a labour force of 140 million. Key sectors: agriculture (palm oil, "
            "rubber, rice, coffee, fishing), mining and nickel processing, "
            "manufacturing (garments, footwear, food and beverages, electronics), "
            "construction, retail and traditional market trade, financial services, "
            "transportation, and public administration. Unemployment: 5.3%. "
            "Average monthly wage: IDR 2,900,000-3,500,000. The informal sector "
            "accounts for 60% of employment."
        ),
        "industries": [
            {
                "name": "Palm Oil & Mining",
                "context": (
                    "Indonesia is the world's largest palm oil producer. Mining (coal, "
                    "nickel, tin) is a major export earner. Key roles: palm oil "
                    "harvesters, mill operators, mining engineers, heavy equipment "
                    "operators, and HSE supervisors. Average monthly wage: IDR 2,500,000-"
                    "5,000,000 for skilled workers; IDR 8,000,000-20,000,000 for engineers."
                ),
                "job_families": ["Agriculture", "Mining Engineering", "HSE", "Heavy Equipment Operations"],
            },
            {
                "name": "Manufacturing (Garments & Footwear)",
                "context": (
                    "Indonesia is a major garment and footwear exporter (Adidas, Nike "
                    "supply chain). Factories employ millions of sewing operators, cutters, "
                    "quality inspectors, and production supervisors. Monthly minimum wage: "
                    "IDR 2,000,000-4,900,000 by province. Brands demand HIGG index compliance "
                    "and social auditing skills."
                ),
                "job_families": ["Garment Production", "Quality Control", "Manufacturing Management"],
            },
            {
                "name": "Financial Services & Fintech",
                "context": (
                    "Indonesia's banking sector (BRI, BCA, Mandiri) and fast-growing "
                    "fintech ecosystem (GoPay, OVO, Dana) serve 180 million adults. "
                    "Key roles: bank officers, microfinance field officers, mobile-banking "
                    "product managers, and digital lending analysts. Average salary: "
                    "IDR 5,000,000-15,000,000/month for professionals."
                ),
                "job_families": ["Banking", "Microfinance", "Fintech", "Insurance"],
            },
            {
                "name": "Retail & E-commerce",
                "context": (
                    "Tokopedia, Shopee, and Lazada dominate Indonesia's USD 52 billion "
                    "e-commerce market. Key roles: courier riders (Gojek, Grab), warehouse "
                    "pickers, seller-support agents, and digital marketing staff. "
                    "Gig couriers earn IDR 3,000,000-5,000,000/month."
                ),
                "job_families": ["Logistics", "Delivery", "E-commerce", "Digital Marketing"],
            },
        ],
        "salary_context": (
            "Indonesia provincial minimum wages (UMP 2024): Jakarta IDR 5,067,381; "
            "Java average IDR 2,700,000-3,200,000; Papua IDR 4,024,270. "
            "Jamsostek social insurance covers pension, health (BPJS), and employment "
            "injury. Average formal-sector monthly wage: IDR 3,200,000."
        ),
    },

    "VN": {
        "overview": (
            "Vietnam is a lower-middle-income, fast-growing economy (GDP per capita "
            "USD 4,300, growing 7%+ annually). Key industries: electronics and "
            "high-tech manufacturing (Samsung, Intel, LG), garments and footwear "
            "(Nike, H&M supply chain), agriculture (coffee, rice, cashew, shrimp), "
            "tourism and hospitality, construction, financial services, and retail. "
            "Labour force: 52 million. Unemployment: 2.3%. Average monthly wage: "
            "VND 7,500,000-9,000,000 (USD 300-360). Vietnam's cost-competitive "
            "manufacturing workforce underpins its 'China+1' strategy appeal."
        ),
        "industries": [
            {
                "name": "Electronics Manufacturing",
                "context": (
                    "Samsung Vietnam (Bắc Ninh, Thái Nguyên) manufactures 50% of Samsung's "
                    "global smartphone output. Intel Việt Nam assembles chips in Hồ Chí "
                    "Minh City. Key roles: SMT operators, quality technicians, production "
                    "engineers, import-export specialists. Average monthly wage: VND 8,000,000-"
                    "12,000,000 for operators; VND 20,000,000-35,000,000 for engineers."
                ),
                "job_families": ["Electronics Manufacturing", "Quality Assurance", "Engineering", "Logistics"],
            },
            {
                "name": "Garments & Footwear",
                "context": (
                    "Vietnam is the world's third-largest garment exporter. Factories in "
                    "industrial zones employ millions of sewing operators, patternmakers, "
                    "and quality controllers. Average factory wage: VND 6,000,000-9,000,000/month. "
                    "EVFTA and CPTPP tariff advantages drive continued expansion."
                ),
                "job_families": ["Garment Production", "Pattern Making", "Quality Control", "Merchandising"],
            },
            {
                "name": "Agriculture & Food Export",
                "context": (
                    "Vietnam is the world's second-largest coffee exporter and top-3 "
                    "rice exporter. The Mekong Delta agri-food cluster employs millions "
                    "in rice farming, seafood processing, and tropical-fruit cultivation. "
                    "Average daily agricultural wage: VND 200,000-300,000."
                ),
                "job_families": ["Farming", "Agri-processing", "Food Technology", "Export Trade"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Vietnam welcomed 12.6 million international tourists in 2023. "
                    "Da Nang, Hội An, Hà Nội, and Hồ Chí Minh City are main hubs. "
                    "Roles: hotel staff, tour guides, resort managers, visa agents. "
                    "Average monthly wage: VND 6,000,000-12,000,000."
                ),
                "job_families": ["Hospitality", "Tourism", "F&B", "Event Management"],
            },
        ],
        "salary_context": (
            "Vietnam minimum wage zones (2024): Zone 1 (Hanoi, HCMC): VND 4,680,000/month; "
            "Zone 4 (rural): VND 3,450,000/month. Average formal wage: VND 8,200,000/month. "
            "Si bảo hiểm xã hội (BHXH social insurance): employer 17.5%, employee 8%."
        ),
    },

    "BD": {
        "overview": (
            "Bangladesh is a lower-middle-income economy with GDP per capita of "
            "USD 2,700, historically one of the world's fastest-growing economies. "
            "Key industries: ready-made garments (RMG, 80% of export earnings), "
            "agriculture (rice, jute, fish), remittances (USD 22 billion), "
            "pharmaceuticals, leather and footwear, IT and freelancing, and "
            "construction. Labour force: 67 million. Unemployment: 4.4%. "
            "Minimum wage for garment workers: BDT 12,500/month (2024)."
        ),
        "industries": [
            {
                "name": "Garments & Textiles (RMG)",
                "context": (
                    "Bangladesh is the world's second-largest garment exporter "
                    "(H&M, Zara, Primark supply chain), with 4 million workers in 3,500 "
                    "factories. Key roles: sewing machine operators, pattern graders, "
                    "quality checkers, production supervisors, compliance officers, and "
                    "merchandisers. Factory workers earn BDT 12,500-18,000/month; "
                    "mid-management BDT 30,000-60,000/month."
                ),
                "job_families": ["Garment Production", "Quality Assurance", "Compliance", "Merchandising"],
            },
            {
                "name": "Agriculture & Food",
                "context": (
                    "Agriculture employs 40% of the labour force (rice, wheat, jute, "
                    "vegetable farming; inland and coastal fisheries). Day labour wages: "
                    "BDT 400-600/day. Agro-processing (frozen shrimp, jute bags, biscuits) "
                    "employs factory workers at BDT 8,000-14,000/month."
                ),
                "job_families": ["Farming", "Fisheries", "Agro-processing"],
            },
            {
                "name": "Pharmaceuticals",
                "context": (
                    "Bangladesh meets 98% of domestic drug needs through 250+ manufacturers "
                    "and exports generics to 150 countries. Key roles: pharmacists, quality-"
                    "control analysts, production operators, and regulatory affairs specialists. "
                    "Average monthly salary: BDT 25,000-60,000."
                ),
                "job_families": ["Pharmaceutical Manufacturing", "Pharmacy", "Quality Assurance", "Regulatory Affairs"],
            },
        ],
        "salary_context": (
            "RMG minimum wage: BDT 12,500/month (2024). National minimum wage for other "
            "sectors: BDT 8,000-10,000/month depending on grade. Average formal-sector "
            "monthly wage: BDT 18,000-25,000."
        ),
    },

    "HK": {
        "overview": (
            "Hong Kong is a high-income special administrative region and global "
            "financial centre with GDP per capita of USD 50,000. Key industries: "
            "financial services and asset management, trade and logistics, tourism "
            "and retail, professional services (legal, accounting), construction "
            "and real estate, education, and hospitality. Labour-force participation: "
            "58%. Unemployment: 3.1%. Median monthly household income: HKD 30,000 "
            "(USD 3,800). Strong demand for wealth managers, compliance officers, "
            "ESG analysts, and professional services lawyers."
        ),
        "industries": [
            {
                "name": "Financial Services & Asset Management",
                "context": (
                    "Hong Kong manages USD 3.9 trillion in AUM and hosts 2,200+ banks, "
                    "fund managers, and insurers. Key roles: investment analysts, fund "
                    "managers, private bankers, compliance officers, actuaries, and trade-"
                    "finance specialists. Average monthly salary: HKD 40,000-120,000 for "
                    "professionals."
                ),
                "job_families": ["Investment Management", "Banking", "Compliance", "Insurance"],
            },
            {
                "name": "Trade, Logistics & Shipping",
                "context": (
                    "Hong Kong is the world's seventh-busiest container port. Freight "
                    "forwarders, customs brokers, shipping agents, logistics analysts, "
                    "and supply-chain managers work across Kwai Chung container port and "
                    "the airport cargo hub. Average monthly salary: HKD 18,000-35,000."
                ),
                "job_families": ["Logistics", "Shipping", "Trade Finance", "Supply Chain"],
            },
            {
                "name": "Retail, Tourism & Hospitality",
                "context": (
                    "Post-COVID tourism recovery in 2023 brought 34 million visitors. "
                    "Retail, hotel, and F&B sectors employ 300,000+. Luxury retail "
                    "(watches, jewellery) remains a key employer. Key roles: retail "
                    "sales staff, hotel concierge, restaurant managers, MICE coordinators. "
                    "Average monthly salary: HKD 16,000-25,000 for line staff."
                ),
                "job_families": ["Retail", "Hospitality", "Tourism", "F&B"],
            },
        ],
        "salary_context": (
            "Hong Kong minimum wage: HKD 40/hour (2023). Average monthly wage: "
            "HKD 19,300 (all industries). Professional services median: HKD 40,000-60,000. "
            "No mandatory pension outside of MPF (Mandatory Provident Fund, 5% each). "
            "Living costs rank among the world's highest."
        ),
    },

    "PK": {
        "overview": (
            "Pakistan is a lower-middle-income economy with GDP per capita of "
            "USD 1,600 and a labour force of 72 million. Key industries: agriculture "
            "(cotton, wheat, rice, sugarcane — 22% of GDP), textile and garment "
            "manufacturing (67% of exports), construction, retail and wholesale trade, "
            "financial services, remittances (USD 27 billion), and IT/freelancing. "
            "Unemployment: 6.3%. Inflation and currency depreciation challenge real "
            "wage growth. NAVTTC vocational certificates cover construction, "
            "electronics, automotive, tailoring, and hospitality trades."
        ),
        "industries": [
            {
                "name": "Textile & Apparel",
                "context": (
                    "Pakistan is the world's fourth-largest cotton producer and eighth-"
                    "largest textile exporter. Key roles: spinning machine operators, "
                    "fabric weavers, garment stitchers, denim finishers, quality inspectors. "
                    "Factory wages: PKR 25,000-40,000/month. Export managers and "
                    "merchandisers earn PKR 80,000-150,000/month."
                ),
                "job_families": ["Textile Manufacturing", "Garment Production", "Quality Control", "Export Management"],
            },
            {
                "name": "Agriculture",
                "context": (
                    "Agriculture employs 37% of the workforce. Cotton, wheat, rice, "
                    "and sugarcane are key crops; mango and citrus for export. "
                    "Large landholding system means sharecropper farm labour is prevalent. "
                    "Agricultural daily wages: PKR 700-1,200."
                ),
                "job_families": ["Farming", "Agri-processing", "Irrigation"],
            },
            {
                "name": "Construction",
                "context": (
                    "Pakistan's housing deficit of 10 million units and CPEC infrastructure "
                    "projects sustain construction demand. Key roles: masons, carpenters, "
                    "plumbers, electricians, site engineers. Average monthly wage: PKR 35,000-"
                    "70,000 for skilled tradespeople."
                ),
                "job_families": ["Construction Trades", "Civil Engineering", "Infrastructure"],
            },
        ],
        "salary_context": (
            "Pakistan minimum wage: PKR 37,000/month (2024). Average formal-sector "
            "monthly wage: PKR 45,000-55,000. Remittances from Gulf, UK, and US are a "
            "key household income supplement for 10 million OPW families."
        ),
    },

    "LK": {
        "overview": (
            "Sri Lanka is a lower-middle-income island economy (GDP per capita "
            "USD 3,800 post-crisis) with a labour force of 8.5 million. Key sectors: "
            "agriculture (tea, rubber, coconut, spices), garments and apparel, "
            "tourism, IT and BPO services, financial services, construction, and "
            "diaspora remittances (USD 3.8 billion). Unemployment: 5.2%. "
            "Free-trade-zone factories in Katunayake and Biyagama employ 350,000 "
            "garment workers. Tea estates employ 350,000 Tamil workers."
        ),
        "industries": [
            {
                "name": "Tea & Agriculture",
                "context": (
                    "Ceylon Tea is Sri Lanka's iconic export. Tea estate pluckers, "
                    "factory workers, and supervisors form a distinct labour market. "
                    "Daily plucking wage: LKR 1,000-1,400. Rubber tappers and coconut "
                    "estate workers follow similar wage patterns."
                ),
                "job_families": ["Tea Cultivation", "Agriculture", "Agro-processing"],
            },
            {
                "name": "Garments & Apparel",
                "context": (
                    "Sri Lanka's apparel sector exports USD 5 billion annually (Victoria's "
                    "Secret, Marks & Spencer supply chain). Factories employ machine "
                    "operators, quality controllers, IE technicians, and production managers. "
                    "Monthly wages: LKR 30,000-50,000 for operators; LKR 80,000-150,000 "
                    "for managers."
                ),
                "job_families": ["Garment Manufacturing", "Quality Assurance", "Industrial Engineering"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Tourism contributes 6% of GDP with 1.5 million visitors (2023). "
                    "Colombo, Galle, Kandy, and safari lodges employ hotel staff, "
                    "tour guides, travel agents, and wildlife rangers. Average monthly "
                    "wage: LKR 40,000-80,000."
                ),
                "job_families": ["Hospitality", "Tourism", "F&B", "Wildlife Conservation"],
            },
        ],
        "salary_context": (
            "Sri Lanka minimum wage: LKR 17,500/month (2024). Garment FTZ workers "
            "earn LKR 30,000-50,000 with productivity bonuses. Tea estate daily wage: "
            "LKR 1,000-1,400. Average formal-sector monthly wage: LKR 55,000-75,000."
        ),
    },
}

# ── Document builders ─────────────────────────────────────────────────────────

def _base_meta(
    country_iso2: str,
    doc_type: str,
    industry: str | None = None,
) -> dict:
    cm = COUNTRY_META.get(country_iso2, {})
    return {
        "doc_type": "global_market",
        "continent": cm.get("continent", "Asia"),
        "country": country_iso2,
        "region": cm.get("region", "Asia"),
        "sub_region": cm.get("sub_region", ""),
        "market_tier": cm.get("market_tier", "emerging"),
        "currency": cm.get("currency", ""),
        "industries": [industry] if industry else [],
        "job_families": [],
        "published_at": _FETCHED_AT[:10],
        "tags": ["asia", cm.get("region", "asia").lower().replace(" ", "-")],
        "source": "curated + ILO ILOSTAT",
        "fetched_at": _FETCHED_AT,
    }


def build_country_overview(country_iso2: str) -> dict | None:
    ctx = _COUNTRY_CONTEXT.get(country_iso2)
    if not ctx:
        return None
    cm = COUNTRY_META.get(country_iso2, {})
    country_name = cm.get("name", country_iso2)
    all_industries = [ind["name"] for ind in ctx.get("industries", [])]
    all_job_families = list({
        jf
        for ind in ctx.get("industries", [])
        for jf in ind.get("job_families", [])
    })

    content = f"# {country_name} — Labour Market Overview\n\n"
    content += ctx["overview"] + "\n\n"
    if ctx.get("salary_context"):
        content += "## Wages & Salary Context\n\n" + ctx["salary_context"] + "\n\n"
    content += f"## Key Industries Covered\n\n" + ", ".join(all_industries) + "\n"

    meta = _base_meta(country_iso2, "overview")
    meta["industries"] = all_industries
    meta["job_families"] = all_job_families
    meta["tags"] += ["overview", "labour-market", "all-industries"]

    return {
        "doc_id": f"asia_overview_{country_iso2.lower()}",
        "title": f"{country_name} Labour Market Overview",
        "content": content.strip(),
        "metadata": meta,
    }


def build_industry_doc(country_iso2: str, industry_data: dict) -> dict:
    cm = COUNTRY_META.get(country_iso2, {})
    country_name = cm.get("name", country_iso2)
    ind_name = industry_data["name"]
    slug = ind_name.lower().replace(" ", "_").replace("&", "and")[:40]

    content = f"# {country_name} — {ind_name}\n\n"
    content += industry_data["context"] + "\n"

    meta = _base_meta(country_iso2, "industry", ind_name)
    meta["industries"] = [ind_name]
    meta["job_families"] = industry_data.get("job_families", [])
    meta["tags"] += ["industry", slug]

    return {
        "doc_id": f"asia_{country_iso2.lower()}_{slug}",
        "title": f"{country_name} — {ind_name}",
        "content": content.strip(),
        "metadata": meta,
    }


def build_curated_docs() -> list[dict]:
    docs = []
    for iso2, ctx in _COUNTRY_CONTEXT.items():
        overview = build_country_overview(iso2)
        if overview:
            docs.append(overview)
        for ind in ctx.get("industries", []):
            docs.append(build_industry_doc(iso2, ind))
    return docs


# ── ILO supplement ─────────────────────────────────────────────────────────────

def build_ilo_supplement(
    *,
    start_year: int = 2018,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch ILO ILOSTAT data for all 14 Asian countries and return documents."""
    asia_countries = REGION_COUNTRIES.get("asia", [])
    if not asia_countries:
        print("[WARN] No Asian countries found in REGION_COUNTRIES")
        return []

    print(f"[ILO] Fetching occupation earnings for {len(asia_countries)} countries...")
    occ_data = fetch_ilo_data(
        "EAR_4MTH_SEX_OCU_NB_A",
        asia_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    print(f"[ILO] Fetching industry earnings for {len(asia_countries)} countries...")
    ind_data = fetch_ilo_data(
        "EAR_4MTH_SEX_ECO_NB_A",
        asia_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    docs = []
    for iso2 in asia_countries:
        cm = COUNTRY_META.get(iso2)
        if not cm:
            continue
        country_docs = build_ilo_documents(iso2, cm, occ_data, ind_data)
        docs.extend(country_docs)
        print(f"[ILO] {cm['name']}: {len(country_docs)} documents generated")

    return docs


# ── Master builder ─────────────────────────────────────────────────────────────

def build_all_docs(
    *,
    start_year: int = 2018,
    use_cache: bool = True,
    dry_run: bool = False,
) -> list[dict]:
    print("[Asia] Building curated country/industry documents...")
    curated = build_curated_docs()
    print(f"[Asia] Curated docs: {len(curated)}")

    print("[Asia] Fetching ILO supplement...")
    ilo_docs = build_ilo_supplement(start_year=start_year, use_cache=use_cache)
    print(f"[Asia] ILO docs: {len(ilo_docs)}")

    all_docs = curated + ilo_docs

    # Deduplicate by doc_id (curated takes precedence over ILO for same id)
    seen: dict[str, dict] = {}
    for doc in all_docs:
        doc_id = doc.get("doc_id", "")
        if doc_id not in seen:
            seen[doc_id] = doc
    deduped = list(seen.values())
    print(f"[Asia] Total unique docs: {len(deduped)}")

    if dry_run:
        print("[Asia] Dry run — not writing output file")
        return deduped

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)
    print(f"[Asia] Written: {_OUTPUT_FILE}")

    return deduped


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Asia labour-market data for RAG KB")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not write output")
    parser.add_argument("--no-cache", action="store_true", help="Bypass ILO disk cache")
    parser.add_argument("--start-year", type=int, default=2018, help="Earliest ILO data year")
    args = parser.parse_args()

    docs = build_all_docs(
        start_year=args.start_year,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )

    print(f"\n[Asia] Done. {len(docs)} documents produced.")
    country_counts: dict[str, int] = {}
    for doc in docs:
        c = doc.get("metadata", {}).get("country", "unknown")
        country_counts[c] = country_counts.get(c, 0) + 1
    for c, n in sorted(country_counts.items()):
        print(f"  {c}: {n} docs")


if __name__ == "__main__":
    main()
