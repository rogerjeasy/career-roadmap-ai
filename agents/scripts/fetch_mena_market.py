"""Fetch Middle East & North Africa labour-market data for the global-market KB.

Covers 15 countries across Gulf Cooperation Council, Levant, and North Africa:
  Gulf (GCC):    UAE (AE), Saudi Arabia (SA), Qatar (QA), Kuwait (KW),
                 Bahrain (BH), Oman (OM)
  Levant:        Israel (IL), Jordan (JO), Lebanon (LB), Iraq (IQ)
  North Africa:  Egypt (EG — shared with Africa script, supplemented here),
                 Morocco (MA — shared with Africa script)
  Turkey:        Turkey (TR)
  Maghreb/Other: Tunisia (TN), Algeria (DZ — shared)

Note: Egypt (EG) and Morocco (MA) receive curated content in fetch_africa_market.py.
This script adds GCC, Levant, Turkey, and Tunisia which are exclusively MENA.

Sources:
  - ILO ILOSTAT SDMX REST API (backbone for all countries)
  - Curated context for UAE, Saudi Arabia, Qatar, Turkey, Israel, Jordan, Tunisia
  - Gulf labour-market data covering ALL sectors (not just oil and tech)

Output:
  agents/data/knowledge-base/global_market_mena.json

Usage:
  python fetch_mena_market.py                        # all countries
  python fetch_mena_market.py --dry-run              # validate only
  python fetch_mena_market.py --no-cache             # bypass disk cache
  python fetch_mena_market.py --start-year 2018      # narrow year range
"""
from __future__ import annotations

import argparse
import json
import sys
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
_OUTPUT_FILE = _REPO_ROOT / "data" / "knowledge-base" / "global_market_mena.json"
_FETCHED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Country context ────────────────────────────────────────────────────────────

_COUNTRY_CONTEXT: dict[str, dict] = {
    "AE": {
        "overview": (
            "The United Arab Emirates is a high-income economy (GDP per capita "
            "USD 50,000) and the Middle East's most diversified business hub. "
            "Dubai and Abu Dhabi are global cities for finance, trade, tourism, "
            "real estate, and logistics. Key industries: oil and gas (ADNOC — "
            "Abu Dhabi National Oil Company), financial services and banking "
            "(Emirates NBD, ADCB, FAB), real estate and construction (EMAAR, "
            "Aldar), trade and logistics (DP World — world's fourth-largest port "
            "operator, Dubai Airports), retail (Mall of the Emirates, Global Village), "
            "tourism and hospitality (Atlantis, Burj Al Arab brands), healthcare "
            "(Cleveland Clinic Abu Dhabi, Mediclinic), education (GEMS, Taaleem), "
            "aerospace (Emirates Airline — 110,000 employees), and technology. "
            "Expatriates comprise 88% of the labour force across all skill levels — "
            "from domestic workers and construction labourers to C-suite executives. "
            "Emiratisation (Nafis programme) targets 10% private-sector Emirati "
            "employment by 2026. Average monthly salary varies widely: AED 1,200-2,500 "
            "for domestic workers and labourers; AED 5,000-10,000 for mid-skill service "
            "workers; AED 15,000-50,000+ for professionals."
        ),
        "industries": [
            {
                "name": "Oil & Gas (ADNOC)",
                "context": (
                    "ADNOC is the UAE's state oil company, producing 4 million bpd. "
                    "ADNOC Drilling, ADNOC Distribution, ADNOC Logistics & Services "
                    "are listed subsidiaries. Key roles: petroleum engineers, reservoir "
                    "engineers, drilling engineers, HSE officers, refinery process "
                    "operators, and petrochemical engineers. Monthly salary: "
                    "AED 15,000-40,000 for engineers; AED 6,000-12,000 for operators."
                ),
                "job_families": ["Petroleum Engineering", "Reservoir Engineering", "Refinery Operations", "HSE"],
            },
            {
                "name": "Financial Services & Banking",
                "context": (
                    "Dubai International Financial Centre (DIFC) and Abu Dhabi Global "
                    "Market (ADGM) host 5,000+ financial firms. First Abu Dhabi Bank, "
                    "Emirates NBD, ADCB are top employers. Islamic finance (Sharia-"
                    "compliant products) is a significant specialisation. Key roles: "
                    "investment bankers, wealth managers, compliance officers, "
                    "Islamic finance scholars, fund managers, and treasury dealers. "
                    "Monthly salary: AED 15,000-60,000+."
                ),
                "job_families": ["Investment Banking", "Wealth Management", "Islamic Finance", "Compliance", "Insurance"],
            },
            {
                "name": "Construction & Real Estate",
                "context": (
                    "UAE's infrastructure pipeline includes EXPO 2020 legacy projects, "
                    "Abu Dhabi Vision 2030 megaprojects, and Dubai 2040 urban plan. "
                    "EMAAR, Aldar, Damac, and Meraas are major developers. Quantity "
                    "surveyors, site engineers, architects, BIM coordinators, MEP "
                    "engineers, and construction labourers (from South Asia, Africa) "
                    "comprise the workforce. Monthly salary: AED 3,500-8,000 for "
                    "skilled labourers; AED 10,000-30,000 for engineers."
                ),
                "job_families": ["Civil Engineering", "Architecture", "Quantity Surveying", "MEP Engineering", "Construction Management"],
            },
            {
                "name": "Aviation & Logistics",
                "context": (
                    "Emirates Airline (110,000 employees) and Etihad Airways (35,000) "
                    "are the flagship airlines. Dubai World Central and Abu Dhabi "
                    "airports rank among the world's busiest. DP World, Jebel Ali "
                    "Free Zone (JAFZA), and dnata cargo employ tens of thousands. "
                    "Key roles: cabin crew, aircraft engineers (EASA Part-66), "
                    "ground handlers, logistics coordinators, and freight forwarders. "
                    "Monthly salary: AED 4,500-9,000 for cabin crew; AED 12,000-25,000 "
                    "for engineers."
                ),
                "job_families": ["Aviation", "Aircraft Engineering", "Logistics", "Freight Forwarding", "Ground Operations"],
            },
            {
                "name": "Tourism, Hospitality & Retail",
                "context": (
                    "Dubai received 17 million tourists in 2023. Hospitality (Jumeirah, "
                    "Marriott, Four Seasons portfolio), retail (Dubai Mall, Mall of "
                    "Emirates), and F&B employ 250,000+. Key roles: hotel front-desk "
                    "and concierge, restaurant chefs and managers, retail sales associates, "
                    "spa therapists, and events coordinators. Monthly salary: AED 2,500-6,000 "
                    "for service staff; AED 8,000-20,000 for managers."
                ),
                "job_families": ["Hospitality", "Retail", "F&B", "Wellness", "Event Management"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "The UAE has private and public healthcare sectors. Cleveland Clinic "
                    "Abu Dhabi, Mediclinic, and NMC Health are large operators. DHA "
                    "(Dubai Health Authority) and DOH (Abu Dhabi) license practitioners. "
                    "Key roles: physicians (MBBS/MD), nurses (RN), physiotherapists, "
                    "radiographers, pharmacists, and hospital administrators. Monthly "
                    "salary: AED 8,000-18,000 for nurses; AED 20,000-55,000 for physicians."
                ),
                "job_families": ["Medicine", "Nursing", "Allied Health", "Pharmacy", "Hospital Administration"],
            },
            {
                "name": "Education",
                "context": (
                    "GEMS Education and Taaleem operate 100+ private schools in the UAE, "
                    "plus many international curriculum schools (British, American, IB, "
                    "CBSE). Universities (NYU Abu Dhabi, Khalifa University, Heriot-Watt) "
                    "hire international faculty. Key roles: teachers (all subjects), "
                    "curriculum coordinators, school principals, university lecturers. "
                    "Monthly salary: AED 5,000-15,000 for teachers; AED 18,000-40,000 "
                    "for senior faculty."
                ),
                "job_families": ["Teaching", "Educational Administration", "Academic Research", "Curriculum Design"],
            },
            {
                "name": "Domestic & Community Services",
                "context": (
                    "700,000+ domestic workers (maids, nannies, drivers, cooks) work "
                    "in UAE households under the kafala sponsorship system. Monthly "
                    "wages: AED 1,200-2,000. Construction labourers from South Asia "
                    "earn AED 900-1,500/month plus accommodation. These roles represent "
                    "a significant portion of UAE's total workforce across all nationalities."
                ),
                "job_families": ["Domestic Work", "Caregiving", "Cleaning Services", "Drivers"],
            },
        ],
        "salary_context": (
            "UAE has no income tax or minimum wage (except for domestic workers: "
            "AED 1,100/month from 2023). Salaries vary enormously by sector, nationality, "
            "and seniority. Housing, transport, and medical allowances add 30-60% to base. "
            "Construction workers: AED 900-1,500/month. Professional expatriates: "
            "AED 10,000-60,000/month. Tax-free salaries attract global talent."
        ),
    },

    "SA": {
        "overview": (
            "Saudi Arabia is the world's largest oil exporter and the Middle East's "
            "biggest economy (GDP USD 1.1 trillion). Vision 2030 is driving "
            "unprecedented economic diversification away from oil. Key sectors: "
            "oil and gas (Saudi Aramco — world's most profitable company), "
            "petrochemicals (SABIC), construction and mega-projects (NEOM, The Red "
            "Sea Project, Qiddiya, Diriyah Gate, King Salman Park), financial services "
            "(Al Rajhi Bank, SNB, Riyad Bank), retail and e-commerce, healthcare, "
            "education, tourism (Saudi Vision 2030 targets 150 million tourist visits "
            "by 2030), logistics, and manufacturing (Ma'aden aluminium, cement). "
            "Saudisation (Nitaqat programme) mandates sector-specific quotas for "
            "Saudi nationals. Women's labour participation rose from 17% to 33% "
            "between 2017-2023. Average formal monthly wage: SAR 8,000-12,000 for "
            "Saudi nationals; SAR 2,500-5,000 for expatriate workers."
        ),
        "industries": [
            {
                "name": "Oil, Gas & Petrochemicals",
                "context": (
                    "Saudi Aramco produces 12 million bpd and has a market capitalisation "
                    "exceeding USD 2 trillion. SABIC produces 50 million tonnes of chemicals/year. "
                    "Key roles: petroleum engineers, chemical process engineers, reservoir "
                    "specialists, refinery operators, pipeline engineers, and HSE professionals. "
                    "Saudi Aramco offers expatriate and Saudi professional packages of "
                    "SAR 25,000-80,000/month for engineers."
                ),
                "job_families": ["Petroleum Engineering", "Chemical Engineering", "Refinery Operations", "HSE", "Geology"],
            },
            {
                "name": "Construction & Mega-projects",
                "context": (
                    "NEOM (USD 500 billion), The Line linear city, Qiddiya entertainment "
                    "city, Red Sea tourism project, and countless urban infrastructure "
                    "projects are the backbone of Vision 2030. SBG (Saudi Binladin Group) "
                    "and NESMA are key Saudi contractors. Key roles: civil engineers, "
                    "architects, project managers, MEP engineers, construction managers, "
                    "BIM coordinators, and millions of labourers from South Asia. Monthly "
                    "salary: SAR 8,000-25,000 for engineers; SAR 1,500-2,500 for labourers."
                ),
                "job_families": ["Civil Engineering", "Architecture", "Project Management", "MEP Engineering", "Urban Planning"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Saudi Arabia is expanding healthcare capacity under Vision 2030 "
                    "to reduce dependence on medical tourism. MOH hospitals, NGHA "
                    "(National Guard Health Affairs), and Saudi Aramco Health Services "
                    "are major employers. Private hospital chains (Mouwasat, Dallah, "
                    "Dr Sulaiman Al Habib) are growing. Key roles: physicians, nurses, "
                    "pharmacists, physiotherapists, and health-informatics specialists. "
                    "Monthly salary: SAR 15,000-40,000 for physicians; SAR 5,000-12,000 "
                    "for nurses."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Allied Health", "Health Informatics"],
            },
            {
                "name": "Retail & E-commerce",
                "context": (
                    "Saudi Arabia has the largest retail market in the GCC. Panda Retail, "
                    "Alshaya Group, and Jarir Bookstore are major employers. E-commerce "
                    "(Noon, Amazon.sa, Salla) is growing rapidly post-Vision 2030 reforms. "
                    "Key roles: store managers, buyers, logistics coordinators, delivery "
                    "riders, and e-commerce product managers. Monthly salary: SAR 3,000-8,000."
                ),
                "job_families": ["Retail", "E-commerce", "Supply Chain", "Customer Service"],
            },
            {
                "name": "Tourism & Entertainment",
                "context": (
                    "Saudi Arabia opened to international tourism in 2019. NEOM, Diriyah, "
                    "AlUla, and the Red Sea Project are flagship tourism developments. "
                    "SELA (Saudi Entertainment Authority) and SCTH (Saudi Commission for "
                    "Tourism and National Heritage) are key regulators. Key roles: tour "
                    "guides, hotel managers, hospitality staff, event coordinators, and "
                    "cultural interpreters. Monthly salary: SAR 4,000-12,000."
                ),
                "job_families": ["Tourism", "Hospitality", "Event Management", "Cultural Guiding"],
            },
            {
                "name": "Education",
                "context": (
                    "Saudi Arabia has 25+ universities, 600,000+ school teachers, and "
                    "a growing private K-12 sector. MOE is the largest employer in the "
                    "country. Key roles: primary, secondary, and university teachers "
                    "(all subjects), curriculum specialists, and educational administrators. "
                    "Saudi teacher monthly salary: SAR 6,000-12,000. Private international "
                    "school teachers: SAR 8,000-18,000."
                ),
                "job_families": ["Teaching", "Academic Research", "Educational Administration"],
            },
        ],
        "salary_context": (
            "Saudi Arabia has no income tax. No national minimum wage for expatriates. "
            "Saudi national minimum wage: SAR 4,000/month (private sector, Nitaqat). "
            "Average Saudi formal salary: SAR 8,000-12,000/month. GOSI social insurance "
            "applies to Saudi nationals (employer 12%, employee 10%)."
        ),
    },

    "QA": {
        "overview": (
            "Qatar is a high-income GCC state (GDP per capita USD 90,000 — among the "
            "world's highest) with its economy historically dominated by LNG exports. "
            "Key industries: oil and gas (QatarEnergy, world's largest LNG exporter), "
            "construction (post-World Cup 2022 legacy infrastructure), financial "
            "services (QNB — largest Arab bank), healthcare, education, aviation "
            "(Qatar Airways — world's top airline brand), tourism, and hospitality. "
            "Expatriates make up 88% of the population. The kafala sponsorship reform "
            "(2020-2023) introduced minimum wage and job mobility. Monthly minimum "
            "wage: QAR 1,000 (basic) + allowances. Average professional salary: "
            "QAR 8,000-20,000."
        ),
        "industries": [
            {
                "name": "LNG & Energy (QatarEnergy)",
                "context": (
                    "QatarEnergy produces 77 million tonnes of LNG/year and is expanding "
                    "to 126 MTPA by 2027. Key roles: LNG process engineers, drilling "
                    "engineers, subsurface geologists, pipeline integrity specialists, "
                    "and HSE officers. Monthly salary: QAR 15,000-45,000 for engineers; "
                    "QAR 4,000-8,000 for operators."
                ),
                "job_families": ["LNG Engineering", "Petroleum Engineering", "Geoscience", "HSE"],
            },
            {
                "name": "Aviation (Qatar Airways)",
                "context": (
                    "Qatar Airways employs 50,000+ from 170 nationalities. Key roles: "
                    "cabin crew, pilots (MPL/ATPL), aircraft maintenance engineers "
                    "(CAMO), airport customer service agents, cargo handlers, and "
                    "catering staff. Monthly salary: QAR 4,000-8,000 for cabin crew; "
                    "QAR 18,000-40,000 for pilots."
                ),
                "job_families": ["Aviation", "Aircraft Maintenance", "Customer Service", "Cargo Operations"],
            },
            {
                "name": "Construction & Infrastructure",
                "context": (
                    "Post-World Cup 2022 legacy: Lusail City, Hamad Port expansion, "
                    "and metro Phase 2. Qatar Rail, Ashghal (Public Works Authority), "
                    "and Barwa Real Estate drive demand. Key roles: civil engineers, "
                    "structural engineers, project managers, QS, MEP engineers, and "
                    "construction workers. Monthly salary: QAR 3,000-12,000."
                ),
                "job_families": ["Civil Engineering", "Project Management", "MEP Engineering", "Quantity Surveying"],
            },
        ],
        "salary_context": (
            "Qatar no income tax. Minimum wage: QAR 1,000 basic + QAR 500 food + "
            "QAR 500 housing (if not provided) = QAR 1,000-2,000 effective minimum. "
            "Professional expatriate salaries: QAR 8,000-25,000/month. Most packages "
            "include tax-free status, housing, and schooling allowances."
        ),
    },

    "KW": {
        "overview": (
            "Kuwait is a high-income GCC state (GDP per capita USD 38,000) with an "
            "oil-dependent economy. Key industries: oil and gas (Kuwait Petroleum "
            "Corporation — 2.8 million bpd), financial services (National Bank of "
            "Kuwait), construction, government public services, healthcare, education, "
            "and retail. Kuwaiti nationals work almost exclusively in the public sector; "
            "expatriates (70% of population) dominate private-sector employment."
        ),
        "industries": [
            {
                "name": "Oil & Gas (KPC)",
                "context": (
                    "Kuwait Petroleum Corporation, KOC (Kuwait Oil Company), and KNPC "
                    "(National Petroleum Company) are the major state operators. "
                    "Key roles: petroleum engineers, drilling engineers, reservoir "
                    "engineers, maintenance technicians, and refinery operators. "
                    "Monthly salary: KWD 1,500-4,000 for engineers."
                ),
                "job_families": ["Petroleum Engineering", "Reservoir Engineering", "Refinery Operations"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "National Bank of Kuwait, Kuwait Finance House (KFH), and Gulf Bank "
                    "are major employers. The Kuwait Stock Exchange (Boursa Kuwait) lists "
                    "190+ companies. Key roles: bank officers, Islamic finance advisers, "
                    "investment analysts, insurance underwriters. Monthly salary: "
                    "KWD 800-2,500."
                ),
                "job_families": ["Banking", "Islamic Finance", "Investment", "Insurance"],
            },
            {
                "name": "Retail & Wholesale",
                "context": (
                    "Alshaya Group, Alghanim Industries, and M.H. Alshaya operate major "
                    "retail and franchise brands. Avenues Mall is the Gulf's largest "
                    "shopping mall. Key roles: retail store managers, franchise operations "
                    "staff, logistics coordinators, and customer service representatives. "
                    "Monthly salary: KWD 250-600 for retail staff."
                ),
                "job_families": ["Retail", "Franchise Management", "Logistics"],
            },
        ],
        "salary_context": (
            "Kuwait no income tax. Minimum wage for domestic workers: KWD 60/month "
            "(under revision). Private-sector average: KWD 600-1,200/month for "
            "expatriates. Government-sector Kuwaiti nationals earn KWD 1,500-3,000/month."
        ),
    },

    "BH": {
        "overview": (
            "Bahrain is a high-income GCC state (GDP per capita USD 27,000) that was "
            "the first Gulf state to develop non-oil sectors. Key industries: financial "
            "services and Islamic banking (Bahrain is the GCC's banking hub), aluminium "
            "smelting (Alba — world's largest single-site smelter), oil refining "
            "(BAPCO), tourism, logistics (Khalifa Bin Salman Port), healthcare, and "
            "ICT. Bahraini nationals comprise 45% of the labour force; expatriates 55%. "
            "The Bahrain Labour Fund (TAMKEEN) subsidises private-sector Bahraini employment."
        ),
        "industries": [
            {
                "name": "Aluminium & Manufacturing",
                "context": (
                    "Aluminium Bahrain (Alba) produces 1.65 million tonnes/year. "
                    "Downstream aluminium (Alba's coil, billet, wire rod) and "
                    "manufacturing (Midal Cables) employ 6,000+. Key roles: "
                    "metallurgical engineers, smelter pot operators, quality engineers, "
                    "electrical engineers. Monthly salary: BHD 500-1,500."
                ),
                "job_families": ["Metallurgy", "Manufacturing Engineering", "Quality Assurance"],
            },
            {
                "name": "Financial Services & Islamic Banking",
                "context": (
                    "Bahrain hosts 400+ financial firms including Ahli United Bank, "
                    "Bank of Bahrain and Kuwait, and Gulf International Bank. AAOIFI "
                    "(Accounting and Auditing Organisation for Islamic Financial "
                    "Institutions) is headquartered here. Key roles: Islamic finance "
                    "scholars, compliance officers, trade-finance specialists, and "
                    "wealth managers. Monthly salary: BHD 800-3,000."
                ),
                "job_families": ["Islamic Finance", "Banking", "Compliance", "Trade Finance"],
            },
        ],
        "salary_context": (
            "Bahrain minimum wage: BHD 300/month for Bahrainis; no minimum for "
            "expatriates. Average private-sector monthly salary: BHD 500-900. "
            "Financial-sector professionals: BHD 1,000-3,000/month."
        ),
    },

    "OM": {
        "overview": (
            "Oman is a high-income GCC state (GDP per capita USD 21,000) undergoing "
            "economic diversification under Vision 2040. Key industries: oil and gas "
            "(PDO — Petroleum Development Oman), logistics (Sohar and Salalah ports), "
            "tourism (Muscat, Wahiba Sands, Dhofar), construction, manufacturing "
            "(industrial zones in Sohar, Rusayl, Salalah), financial services, "
            "fisheries, and agriculture. Omanisation (Nationalisation) quotas apply "
            "across all private sectors. Average monthly wage: OMR 450-800."
        ),
        "industries": [
            {
                "name": "Oil & Gas (PDO)",
                "context": (
                    "PDO is a partnership between the government (60%), Shell (34%), "
                    "and others. Production: 1 million bpd. Oman LNG (Qalhat) is an "
                    "export terminal. Key roles: petroleum engineers, drilling engineers, "
                    "production technicians, HSE officers. Monthly salary: OMR 1,500-4,000 "
                    "for engineers."
                ),
                "job_families": ["Petroleum Engineering", "Production Operations", "HSE"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Oman targets 11 million tourists by 2040. Luxury lodges (Alila, "
                    "Six Senses), wadis and desert camps, and Muscat's cultural circuit "
                    "are the products. Key roles: hotel managers, eco-lodge guides, "
                    "dive instructors, tour operators. Monthly salary: OMR 200-500."
                ),
                "job_families": ["Hospitality", "Tourism", "Eco-guiding", "Diving"],
            },
            {
                "name": "Fisheries",
                "context": (
                    "Oman has a 3,000 km coastline with productive fishing grounds. "
                    "Artisanal fishers, fish-processing plant workers, and aquaculture "
                    "technicians are key roles. MAFR (Ministry of Agriculture, Fisheries "
                    "and Water Resources) promotes sardine, abalone, and shrimp exports. "
                    "Monthly wages: OMR 200-400 for fishers."
                ),
                "job_families": ["Fisheries", "Aquaculture", "Fish Processing"],
            },
        ],
        "salary_context": (
            "Oman minimum wage: OMR 325/month for Omani nationals. Average private-sector "
            "monthly wage: OMR 450-700. Oil-sector professionals: OMR 1,500-4,000/month. "
            "Hospitality and fisheries workers earn near minimum wage."
        ),
    },

    "TR": {
        "overview": (
            "Turkey is a high-income OECD economy (GDP USD 1.1 trillion) with a highly "
            "diversified industrial base. Key industries: automotive (Ford, Fiat-Stellantis, "
            "TOGG electric vehicle, Renault — Turkey is Europe's top-5 vehicle producer), "
            "textile and apparel (world's fifth-largest exporter), construction and real "
            "estate, agriculture (hazelnuts, cherries, figs, tobacco, cotton — Turkey is "
            "world's top hazelnut producer), food and beverage processing, financial "
            "services, tourism (Antalya, Istanbul, Cappadocia — 56 million tourists, "
            "2023), steel (Erdemir, Kardemir), defence (Bayraktar TB2 drone), and "
            "healthcare. Labour force: 34 million. Unemployment: 9.4%."
        ),
        "industries": [
            {
                "name": "Automotive & Industrial Manufacturing",
                "context": (
                    "Turkey produces 1.4 million vehicles/year. Ford Otosan, TOGG, "
                    "Tofaş (Fiat), and Renault Turkey are major employers in Kocaeli, "
                    "Bursa. Defence industry (Baykar, Roketsan, Aselsan) employs 30,000+. "
                    "Key roles: production operators, quality engineers, robotics "
                    "technicians, supply-chain planners. Monthly salary: TRY 25,000-60,000 "
                    "for engineers (note: high inflation erodes real wages rapidly)."
                ),
                "job_families": ["Automotive Manufacturing", "Defence Engineering", "Quality Engineering", "Supply Chain"],
            },
            {
                "name": "Textile & Apparel",
                "context": (
                    "Turkey exports USD 19 billion in textiles and apparel. Istanbul's "
                    "Laleli district and Bursa's organized industrial zones are major hubs. "
                    "Key roles: fashion designers, sewing operators, pattern makers, "
                    "quality controllers, export merchandisers. Monthly salary: TRY "
                    "15,000-25,000 for production workers; TRY 40,000-80,000 for designers "
                    "and merchandisers."
                ),
                "job_families": ["Fashion Design", "Garment Manufacturing", "Quality Control", "Merchandising"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Turkey attracted 56 million tourists (2023). Antalya, Istanbul, "
                    "Cappadocia, Bodrum, and Fethiye are major destinations. Hotel chains "
                    "(Rixos, Limak, Marriott) and tour operators employ 1 million+. "
                    "Key roles: hotel GMs, tour guides, cruise managers, restaurant chefs, "
                    "and cultural heritage interpreters. Monthly salary: TRY 20,000-50,000."
                ),
                "job_families": ["Hospitality", "Tourism", "F&B", "Heritage Tourism"],
            },
            {
                "name": "Agriculture & Agro-food",
                "context": (
                    "Turkey is among the world's top-10 agricultural producers. Hazelnuts "
                    "(Black Sea coast), cherries, apricots, figs, cotton (Aegean), and "
                    "livestock are key. Food processing (Ülker, Yıldız Holding, Koç "
                    "agribusiness) is a major industry. Key roles: farm workers, "
                    "agronomists, food technologists, export coordinators. Monthly salary: "
                    "TRY 12,000-22,000 for agricultural workers; TRY 30,000-60,000 for "
                    "agronomists."
                ),
                "job_families": ["Farming", "Agro-processing", "Food Technology", "Agri-export"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "İşbank, Ziraat Bank, Akbank, Garanti BBVA, and Yapı Kredi are "
                    "top employers. BIST (Borsa Istanbul) lists 500+ companies. "
                    "Key roles: bank relationship managers, capital-markets analysts, "
                    "insurance actuaries, investment advisers. Monthly salary: "
                    "TRY 35,000-100,000."
                ),
                "job_families": ["Banking", "Capital Markets", "Insurance", "Actuarial"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Turkey has universal healthcare (SGK) and a growing medical-tourism "
                    "sector (health tourism revenues: USD 2 billion/year, mainly for hair "
                    "transplants, dental, and cosmetic surgery). Acıbadem, Memorial, and "
                    "Medical Park hospital chains are large private employers. Key roles: "
                    "physicians, nurses, dentists, cosmetic surgeons, medical translators. "
                    "Monthly salary: TRY 30,000-80,000 for physicians."
                ),
                "job_families": ["Medicine", "Nursing", "Dentistry", "Allied Health", "Medical Tourism"],
            },
        ],
        "salary_context": (
            "Turkey minimum wage: TRY 17,002/month (2024). Average formal monthly wage: "
            "TRY 35,000-45,000. High inflation (65% annual, 2024) means real wages "
            "fluctuate rapidly. Manufacturing and tourism wages are below the European "
            "average in USD terms. Employer SGK social security contribution: 20.5%."
        ),
    },

    "IL": {
        "overview": (
            "Israel is a high-income OECD economy (GDP per capita USD 55,000) with "
            "a world-class innovation ecosystem. Key industries: high-technology "
            "(cybersecurity, semiconductors, enterprise software, medtech — Israel is "
            "'Startup Nation' with 6,500+ startups), diamonds (Ramat Gan — world's "
            "largest polished-diamond trading centre), agriculture (drip irrigation, "
            "agri-tech, citrus, avocado, tomatoes), financial services (Bank Hapoalim, "
            "Mizrahi-Tefahot), defence industry (Elbit, Rafael, IAI), tourism (Jerusalem, "
            "Tel Aviv, Dead Sea), healthcare (HMOs — Clalit, Maccabi), and construction. "
            "Labour force: 4.3 million. Unemployment: 3.6%."
        ),
        "industries": [
            {
                "name": "High-Tech & Innovation",
                "context": (
                    "Israel has the highest R&D spend/GDP ratio globally and attracts "
                    "USD 10 billion+ in VC annually. Top sectors: cybersecurity (Check "
                    "Point, CyberArk), semiconductors (Intel R&D Haifa, Mellanox/NVIDIA), "
                    "enterprise software, medtech (Given Imaging, Medigus), and agri-tech. "
                    "Non-tech roles in startups: HR, finance, legal, marketing, customer "
                    "success. Monthly salary: ILS 18,000-45,000 for tech roles; ILS "
                    "10,000-20,000 for non-tech."
                ),
                "job_families": ["Software Engineering", "Cybersecurity", "Semiconductor Engineering", "HR", "Finance"],
            },
            {
                "name": "Agriculture & Agri-tech",
                "context": (
                    "Israel pioneered drip irrigation and is a global leader in precision "
                    "agriculture, dairy genetics, and greenhouse technology. Key roles: "
                    "agronomists, agri-tech engineers, kibbutz farm workers, greenhouse "
                    "horticulturists, and precision-irrigation technicians. Monthly salary: "
                    "ILS 8,000-20,000 for agronomists."
                ),
                "job_families": ["Agronomy", "Agri-tech", "Horticulture", "Precision Agriculture"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Israel's universal healthcare via 4 competing HMOs (Clalit, Maccabi, "
                    "Meuhedet, Leumit) provides strong employment for physicians, nurses, "
                    "pharmacists, and allied health. Monthly salary: ILS 15,000-50,000 "
                    "for physicians; ILS 8,000-16,000 for nurses."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Allied Health"],
            },
        ],
        "salary_context": (
            "Israel minimum wage: ILS 5,571/month (2024). Average monthly wage: "
            "ILS 12,000-14,000. High-tech sector: ILS 20,000-50,000+. Healthcare "
            "and education: ILS 8,000-18,000. Income tax rates: 10-50% progressively."
        ),
    },

    "JO": {
        "overview": (
            "Jordan is a lower-middle-income economy (GDP per capita USD 4,700) with "
            "a service-led economy and skilled, educated workforce. Key industries: "
            "phosphate and potash mining (Jordan is world's third-largest phosphate "
            "producer), pharmaceuticals (Jordan is the Arab world's largest pharma "
            "exporter), tourism (Petra, Wadi Rum, Dead Sea), financial services, "
            "ICT and BPO (Amman is a regional digital hub), construction, healthcare, "
            "and education. Unemployment: 21.9% (very high, youth 40%+). Highly "
            "educated workforce exports labour to the Gulf. Average monthly formal "
            "wage: JOD 500-800."
        ),
        "industries": [
            {
                "name": "Pharmaceuticals",
                "context": (
                    "Jordan is the Arab world's top pharma exporter with 22 manufacturers "
                    "(Hikma, JPHCO, Arab Pharmaceutical Manufacturing). Key roles: "
                    "pharmaceutical production operators, quality-control analysts, "
                    "regulatory affairs managers, sales representatives. Monthly salary: "
                    "JOD 400-1,200."
                ),
                "job_families": ["Pharmaceutical Manufacturing", "Quality Assurance", "Regulatory Affairs", "Pharma Sales"],
            },
            {
                "name": "ICT & BPO",
                "context": (
                    "Amman is a tech and BPO hub for the Arab world. Key roles: software "
                    "developers, data engineers, Arabic-language content moderators, "
                    "customer-service agents, and digital marketing specialists. "
                    "Monthly salary: JOD 500-1,500."
                ),
                "job_families": ["Software Engineering", "BPO", "Content Moderation", "Digital Marketing"],
            },
            {
                "name": "Tourism (Petra & Dead Sea)",
                "context": (
                    "Jordan received 5.5 million tourists (2023). Petra, Wadi Rum, "
                    "Aqaba, and the Dead Sea are flagship sites. Key roles: licensed "
                    "tour guides, hotel staff, souvenir craftspeople, camel and horse "
                    "handlers. Monthly salary: JOD 300-600."
                ),
                "job_families": ["Tourism", "Hospitality", "Heritage Guiding", "Craft & Artisan"],
            },
        ],
        "salary_context": (
            "Jordan minimum wage: JOD 260/month (2023). Average formal monthly wage: "
            "JOD 450-750. High unemployment drives emigration to GCC, where Jordanians "
            "earn 3-5× domestic wages."
        ),
    },

    "TN": {
        "overview": (
            "Tunisia is a lower-middle-income economy (GDP per capita USD 4,000) with "
            "a diversified manufacturing base oriented toward the European market. Key "
            "industries: automotive components (Lear, Leoni, Yazaki cable harnesses for "
            "European car manufacturers), textiles and garments, phosphate and chemical "
            "fertilisers, tourism (Djerba, Hammamet, Sousse), agriculture (olive oil — "
            "world's second-largest producer, dates), financial services, and ICT "
            "offshoring. Labour force: 4.5 million. Unemployment: 15.6%."
        ),
        "industries": [
            {
                "name": "Automotive Components (Cable Harnesses)",
                "context": (
                    "Tunisia manufactures 35% of Europe's automotive cable harnesses. "
                    "Leoni AG, Yazaki, Delphi Technologies, and Lear Corporation operate "
                    "50+ factories in Bizerte, Sfax, and Sousse. Key roles: cable-harness "
                    "assemblers, production supervisors, quality engineers, industrial "
                    "engineers. Monthly wages: TND 600-900 for operators; TND 1,500-3,000 "
                    "for engineers."
                ),
                "job_families": ["Electronics Manufacturing", "Automotive Components", "Quality Engineering", "Industrial Engineering"],
            },
            {
                "name": "Textile & Garments",
                "context": (
                    "Tunisia exports EUR 1.5 billion in garments to European brands. "
                    "Full-package and CMT (Cut, Make, Trim) factories cluster in Sfax, "
                    "Nabeul, and Ben Arous. Key roles: sewing machine operators, cutting "
                    "supervisors, pattern technicians, quality controllers. Monthly "
                    "wages: TND 500-750 for operators; TND 1,200-2,500 for managers."
                ),
                "job_families": ["Garment Production", "Pattern Making", "Quality Control"],
            },
            {
                "name": "Olive Oil & Agriculture",
                "context": (
                    "Tunisia has 100 million olive trees and is the world's second-largest "
                    "olive oil exporter (after Spain). Dates from Deglet Nour variety "
                    "(Tozeur, Nefta) are a premium export. Key roles: olive grove workers, "
                    "olive oil mill operators, agricultural co-op managers. Daily wages: "
                    "TND 15-25."
                ),
                "job_families": ["Farming", "Agro-processing", "Agri-export"],
            },
            {
                "name": "Tourism",
                "context": (
                    "Tunisia attracted 9.5 million tourists (2023). Djerba, Hammamet, "
                    "and the Medinas of Tunis, Kairouan, and Sfax are major attractions. "
                    "Key roles: hotel front-desk staff, tour guides, medina craft artisans, "
                    "travel agency staff. Monthly salary: TND 600-1,200."
                ),
                "job_families": ["Hospitality", "Tourism", "Heritage Craft", "Tour Guiding"],
            },
        ],
        "salary_context": (
            "Tunisia minimum wage (SMIG): TND 475/month (industry, 2024); SMAG "
            "(agriculture): TND 387/month. Average formal monthly wage: TND 900-1,400. "
            "ICT and offshoring workers earn TND 1,500-3,000/month."
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
        "continent": "Asia",
        "country": country_iso2,
        "region": "Middle East & North Africa",
        "sub_region": cm.get("sub_region", "MENA"),
        "market_tier": cm.get("market_tier", "emerging"),
        "currency": cm.get("currency", ""),
        "industries": [industry] if industry else [],
        "job_families": [],
        "published_at": _FETCHED_AT[:10],
        "tags": ["mena", cm.get("sub_region", "mena").lower().replace(" ", "-").replace("&", "and")],
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
    content += "## Key Industries Covered\n\n" + ", ".join(all_industries) + "\n"

    meta = _base_meta(country_iso2, "overview")
    meta["industries"] = all_industries
    meta["job_families"] = all_job_families
    meta["tags"] += ["overview", "labour-market"]

    return {
        "doc_id": f"mena_overview_{country_iso2.lower()}",
        "title": f"{country_name} Labour Market Overview",
        "content": content.strip(),
        "metadata": meta,
    }


def build_industry_doc(country_iso2: str, industry_data: dict) -> dict:
    cm = COUNTRY_META.get(country_iso2, {})
    country_name = cm.get("name", country_iso2)
    ind_name = industry_data["name"]
    slug = ind_name.lower().replace(" ", "_").replace("&", "and")[:40]
    slug = slug.replace("(", "").replace(")", "").replace(",", "").replace("/", "_")

    content = f"# {country_name} — {ind_name}\n\n"
    content += industry_data["context"] + "\n"

    meta = _base_meta(country_iso2, "industry", ind_name)
    meta["industries"] = [ind_name]
    meta["job_families"] = industry_data.get("job_families", [])
    meta["tags"] += ["industry", slug[:30]]

    return {
        "doc_id": f"mena_{country_iso2.lower()}_{slug[:35]}",
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
    mena_countries = REGION_COUNTRIES.get("mena", [])
    if not mena_countries:
        print("[WARN] No MENA countries found in REGION_COUNTRIES")
        return []

    print(f"[ILO] Fetching occupation earnings for {len(mena_countries)} MENA countries...")
    occ_data = fetch_ilo_data(
        "EAR_4MTH_SEX_OCU_NB_A",
        mena_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    print(f"[ILO] Fetching industry earnings for {len(mena_countries)} MENA countries...")
    ind_data = fetch_ilo_data(
        "EAR_4MTH_SEX_ECO_NB_A",
        mena_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    docs = []
    for iso2 in mena_countries:
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
    print("[MENA] Building curated country/industry documents...")
    curated = build_curated_docs()
    print(f"[MENA] Curated docs: {len(curated)}")

    print("[MENA] Fetching ILO supplement...")
    ilo_docs = build_ilo_supplement(start_year=start_year, use_cache=use_cache)
    print(f"[MENA] ILO docs: {len(ilo_docs)}")

    all_docs = curated + ilo_docs
    seen: dict[str, dict] = {}
    for doc in all_docs:
        doc_id = doc.get("doc_id", "")
        if doc_id not in seen:
            seen[doc_id] = doc
    deduped = list(seen.values())
    print(f"[MENA] Total unique docs: {len(deduped)}")

    if dry_run:
        print("[MENA] Dry run — not writing output file")
        return deduped

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)
    print(f"[MENA] Written: {_OUTPUT_FILE}")
    return deduped


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch MENA labour-market data for RAG KB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--start-year", type=int, default=2018)
    args = parser.parse_args()

    docs = build_all_docs(
        start_year=args.start_year,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )

    print(f"\n[MENA] Done. {len(docs)} documents produced.")
    country_counts: dict[str, int] = {}
    for doc in docs:
        c = doc.get("metadata", {}).get("country", "unknown")
        country_counts[c] = country_counts.get(c, 0) + 1
    for c, n in sorted(country_counts.items()):
        print(f"  {c}: {n} docs")


if __name__ == "__main__":
    main()
