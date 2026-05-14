"""Fetch Africa labour-market data for the global-market knowledge base.

Covers 14 countries spanning all 5 African sub-regions:
  North Africa:    Egypt (EG), Morocco (MA), Algeria (DZ), Tunisia (TN)
  West Africa:     Nigeria (NG), Ghana (GH), Senegal (SN), Côte d'Ivoire (CI)
  East Africa:     Ethiopia (ET), Kenya (KE), Tanzania (TZ), Uganda (UG)
  Central Africa:  Cameroon (CM)
  Southern Africa: South Africa (ZA), Rwanda (RW), Angola (AO)

Sources:
  - ILO ILOSTAT SDMX REST API (backbone for all countries, all job families/industries)
  - Nigeria NBS (National Bureau of Statistics) English summaries
  - South Africa StatsSA QLFS (English) curated context
  - Kenya KNBS (Kenya National Bureau of Statistics) English context
  - Curated country context paragraphs covering ALL industries

Output:
  agents/data/knowledge-base/global_market_africa.json

Usage:
  python fetch_africa_market.py                        # all countries
  python fetch_africa_market.py --dry-run              # validate only
  python fetch_africa_market.py --no-cache             # bypass disk cache
  python fetch_africa_market.py --start-year 2018      # narrow year range
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
_OUTPUT_FILE = _REPO_ROOT / "data" / "knowledge-base" / "global_market_africa.json"
_FETCHED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Country context paragraphs ─────────────────────────────────────────────────

_COUNTRY_CONTEXT: dict[str, dict] = {
    "NG": {
        "overview": (
            "Nigeria is Africa's largest economy (GDP USD 477 billion, 2023) and most "
            "populous country with 220 million people. Key industries: crude oil and gas "
            "(90% of government revenue), agriculture (cassava, yam, maize, rice, cocoa, "
            "groundnuts — employs 36% of workforce), manufacturing (cement, food "
            "processing, beverages, textiles), financial services (banking, fintech), "
            "construction, retail and wholesale trade, telecommunications, and creative "
            "economy (Nollywood, Afrobeats). Unemployment: 4.2% (NBS 2023 rebased), "
            "though underemployment and informality are very high. Average monthly wage "
            "in formal sector: NGN 80,000-150,000. The NSITF (Nigeria Social Insurance "
            "Trust Fund) and ITF (Industrial Training Fund) govern skills development "
            "across 36 states. Lagos, Kano, and Abuja are the three largest labour markets."
        ),
        "industries": [
            {
                "name": "Oil, Gas & Petrochemicals",
                "context": (
                    "Nigeria pumps 1.4 million barrels/day. NNPC Limited, Shell, Chevron, "
                    "TotalEnergies, and Seplat operate onshore and offshore fields. Key "
                    "roles: petroleum engineers, reservoir engineers, HSE officers, "
                    "pipeline technicians, oil traders, and gas plant operators. Monthly "
                    "salary: NGN 300,000-800,000 for engineers; NGN 1,200,000+ for senior "
                    "reservoir or drilling engineers in IOCs. Dangote Refinery (650,000 "
                    "bpd capacity) will require 10,000+ operators and engineers."
                ),
                "job_families": ["Petroleum Engineering", "HSE", "Gas Operations", "Energy Trading"],
            },
            {
                "name": "Agriculture & Agro-processing",
                "context": (
                    "Agriculture employs 36% of Nigerians. Nigeria is the world's largest "
                    "cassava and yam producer, and Africa's largest cocoa producer. Key "
                    "occupations: crop farmers, livestock herders, poultry farmers, fish "
                    "farmers (catfish, tilapia), agro-processing workers (flour milling, "
                    "tomato paste, palm oil extraction), and agricultural extension workers. "
                    "Daily agricultural wages: NGN 1,500-3,000 in southern states; "
                    "NGN 900-1,500 in northern states."
                ),
                "job_families": ["Farming", "Livestock Husbandry", "Agro-processing", "Fisheries"],
            },
            {
                "name": "Financial Services & Fintech",
                "context": (
                    "Nigeria hosts Africa's most vibrant fintech ecosystem (Flutterwave, "
                    "Paystack, Interswitch). Tier-1 banks (GTBank, Zenith, Access, UBA, "
                    "First Bank) employ 200,000+. Key roles: bank tellers, credit analysts, "
                    "fintech engineers, mobile-money agents, insurance brokers, pension "
                    "fund analysts, and microfinance field officers. Average monthly salary: "
                    "NGN 150,000-400,000 for professionals."
                ),
                "job_families": ["Banking", "Fintech", "Insurance", "Microfinance", "Pension Management"],
            },
            {
                "name": "Construction & Real Estate",
                "context": (
                    "Nigeria's housing deficit of 28 million units drives construction "
                    "demand. Key roles: civil engineers, quantity surveyors, architects, "
                    "estate surveyors (NIESV), site foremen, and construction labourers. "
                    "Lagos and Abuja real-estate markets attract luxury residential, "
                    "commercial, and mixed-use development. Monthly salary: NGN 250,000-"
                    "600,000 for professional engineers; NGN 80,000-150,000 for skilled trades."
                ),
                "job_families": ["Civil Engineering", "Architecture", "Quantity Surveying", "Real Estate"],
            },
            {
                "name": "Creative Economy (Nollywood & Music)",
                "context": (
                    "Nigeria's creative industry — Nollywood (world's second-largest film "
                    "industry by volume), Afrobeats, and fashion — contributes 2.3% of GDP. "
                    "Key roles: film directors, actors, music producers, sound engineers, "
                    "costume designers, digital content creators, and streaming-platform "
                    "editors. Incomes vary widely from NGN 50,000/month (entry crew) to "
                    "NGN 5,000,000+ for A-list talent."
                ),
                "job_families": ["Film Production", "Music Industry", "Fashion Design", "Content Creation"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Nigeria's healthcare system is stressed but reforming under the "
                    "Tinubu health emergency declaration (2023). Key roles: doctors "
                    "(MBBS/FMCP), nurses (RN/RM), pharmacists, medical-lab scientists, "
                    "community health extension workers (CHEW). Brain drain remains acute — "
                    "30,000+ Nigerian doctors practise abroad. Monthly salary: NGN 130,000-"
                    "250,000 for NHS (CONHESS scale) nurses; NGN 350,000-600,000 for doctors."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Allied Health", "Community Health"],
            },
        ],
        "salary_context": (
            "National minimum wage: NGN 70,000/month (2024 amended). Federal civil "
            "service consolidated CONTISS/CONHESS pay scales range from NGN 70,000 "
            "(entry) to NGN 450,000+ (Grade Level 17). Private formal-sector average: "
            "NGN 100,000-200,000/month. Oil-sector workers earn 3-5× the national average."
        ),
    },

    "ZA": {
        "overview": (
            "South Africa is the continent's most industrialised economy (GDP USD 380 "
            "billion) with a highly segmented labour market. Key industries: mining "
            "(gold, platinum, coal, chromium, iron ore), automotive manufacturing "
            "(BMW, Toyota, VW assembly), financial services (JSE-listed banks and "
            "insurers), retail (Shoprite, Pick n Pay, Woolworths), agriculture "
            "(wine, citrus, maize, sugarcane), construction, healthcare, education, "
            "and government. Unemployment: 32.1% (QLFS Q4 2023) — one of the world's "
            "highest. Average monthly earnings (formal sector): ZAR 24,000. "
            "National Minimum Wage: ZAR 27.58/hour (2024). SETA system funds skills "
            "development across 21 sector authorities."
        ),
        "industries": [
            {
                "name": "Mining & Minerals",
                "context": (
                    "South Africa holds 80% of global platinum reserves and 50% of "
                    "manganese. Impala Platinum, Anglo American, and Sibanye-Stillwater "
                    "employ 400,000 mine workers. Key roles: rock-drill operators, "
                    "stope miners, mine surveyors, mining engineers, metallurgists, "
                    "and ventilation officers. Average monthly salary: ZAR 20,000-30,000 "
                    "for production workers; ZAR 60,000-120,000 for engineers."
                ),
                "job_families": ["Mining Engineering", "Mine Operations", "Metallurgy", "HSE"],
            },
            {
                "name": "Automotive Manufacturing",
                "context": (
                    "South Africa produces 600,000 vehicles annually (BMW, Toyota, VW, "
                    "Ford, Isuzu assembly plants in Gauteng, Durban, and Eastern Cape). "
                    "Key roles: assembly workers, quality technicians, process engineers, "
                    "tooling setters, and supply-chain coordinators. Average monthly "
                    "salary: ZAR 18,000-28,000 for production workers; ZAR 45,000-80,000 "
                    "for engineers."
                ),
                "job_families": ["Automotive Manufacturing", "Engineering", "Quality Assurance", "Supply Chain"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Four major banks (Standard Bank, ABSA, Nedbank, FNB/FirstRand) "
                    "and JSE-listed insurers (Sanlam, Old Mutual, Discovery) dominate. "
                    "Key roles: financial advisers, actuaries, chartered accountants (CA(SA)), "
                    "compliance officers, credit analysts, and insurance underwriters. "
                    "Average monthly salary: ZAR 35,000-100,000 for professionals."
                ),
                "job_families": ["Banking", "Insurance", "Actuarial", "Accounting", "Compliance"],
            },
            {
                "name": "Agriculture & Agro-processing",
                "context": (
                    "South Africa exports USD 12 billion in agricultural products. "
                    "Western Cape wine and citrus, KwaZulu-Natal sugarcane, and "
                    "Limpopo citrus/stone-fruit are key. Farm workers earn the "
                    "National Minimum Wage (ZAR 27.58/hour). Agro-processing (Clover, "
                    "Tiger Brands, Pioneer Foods) employs factory workers at ZAR 5,500-"
                    "12,000/month. Horticulture specialists and viticulturists are "
                    "in demand in the Western Cape."
                ),
                "job_families": ["Farming", "Viticulture", "Agro-processing", "Horticulture"],
            },
            {
                "name": "Retail & Wholesale",
                "context": (
                    "Shoprite Checkers, Pick n Pay, Woolworths Food, SPAR, and Clicks "
                    "collectively employ 500,000+. Informal street trading employs "
                    "millions in townships. Key formal roles: store managers, cashiers, "
                    "category buyers, supply-chain analysts, and distribution-centre staff. "
                    "Average monthly salary: ZAR 8,000-16,000 for store staff; "
                    "ZAR 30,000-60,000 for buyers and managers."
                ),
                "job_families": ["Retail", "Buying", "Supply Chain", "Customer Service"],
            },
            {
                "name": "Education",
                "context": (
                    "South Africa has 1,300+ public schools under 9 provincial departments "
                    "plus universities and TVET colleges. Teacher shortages are acute in "
                    "Mathematics, Science, and special-needs education. SACE-registered "
                    "teachers earn ZAR 18,000-45,000/month on REQV levels. University "
                    "lecturers earn ZAR 35,000-80,000/month."
                ),
                "job_families": ["Teaching", "Academic Research", "Educational Administration", "TVET"],
            },
        ],
        "salary_context": (
            "National Minimum Wage (NMW): ZAR 27.58/hour / ZAR 4,793/month (2024). "
            "Domestic workers: ZAR 23.19/hour. Farm workers: NMW applies. "
            "Formal-sector median monthly earnings: ZAR 24,000. Mining sectoral "
            "determination averages ZAR 20,000-30,000. Skills shortage in engineering, "
            "IT, healthcare, and artisan trades drives premium wages."
        ),
    },

    "KE": {
        "overview": (
            "Kenya is East Africa's economic hub with GDP per capita of USD 2,200 "
            "and a fast-growing services economy. Key industries: agriculture (tea, "
            "coffee, cut flowers, horticulture — 26% of GDP), financial services and "
            "fintech (M-Pesa ecosystem, equity bank), ICT and BPO, construction and "
            "real estate, tourism (safari, coastal), manufacturing (food processing, "
            "cement, apparel), healthcare, and education. Labour force: 26 million. "
            "Unemployment: 5.6%. Average monthly wage in formal sector: KES 50,000-80,000. "
            "Nairobi is home to Africa's largest tech-startup ecosystem (Silicon Savannah)."
        ),
        "industries": [
            {
                "name": "Agriculture & Horticulture",
                "context": (
                    "Kenya is the world's third-largest tea exporter and Africa's largest "
                    "cut-flower exporter (Naivasha lake basin supplies 35% of Europe's flowers). "
                    "Smallholder tea farmers sell through KTDA; large estates (Finlay, "
                    "James Finlay) employ seasonal pickers and factory operators. "
                    "Average daily tea-picker wage: KES 500-700. Agri-value-chain roles "
                    "(graders, cold-chain logistics, certifiers) earn KES 25,000-50,000/month."
                ),
                "job_families": ["Farming", "Horticulture", "Agri-processing", "Cold Chain Logistics"],
            },
            {
                "name": "Financial Services & Fintech",
                "context": (
                    "M-Pesa (Safaricom) pioneered mobile money; Equity Bank, KCB, and "
                    "NCBA are major employers. Nairobi is Africa's leading IBFS (international "
                    "financial services) hub post-Brexit. Key roles: mobile-money agents, "
                    "credit officers, insurance sales reps, stockbrokers, and actuaries. "
                    "Average monthly salary: KES 50,000-150,000 for professionals."
                ),
                "job_families": ["Banking", "Mobile Money", "Insurance", "Capital Markets"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Tourism contributes 8.8% of GDP. The Masai Mara, Amboseli, and "
                    "Diani Beach attract 2 million+ tourists annually. Key roles: safari "
                    "guides, lodge managers, hotel F&B staff, tour operators, wildlife "
                    "conservancy rangers, and MICE event coordinators. Average monthly "
                    "wage: KES 20,000-50,000 for lodge staff; KES 80,000+ for senior "
                    "lodge managers."
                ),
                "job_families": ["Tourism", "Hospitality", "Wildlife Conservation", "Event Management"],
            },
            {
                "name": "ICT & BPO",
                "context": (
                    "Kenya's ICT sector grew 10% annually and the Silicon Savannah cluster "
                    "includes Africa's headquarters of Google, Microsoft, IBM, and Vodafone. "
                    "BPO for data annotation and content moderation employs 25,000+. "
                    "Key roles: software developers, data annotators, network engineers, "
                    "digital-marketing specialists, and fintech product managers. "
                    "Average monthly salary: KES 80,000-250,000."
                ),
                "job_families": ["Software Engineering", "Data Science", "BPO", "Digital Marketing"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Kenya's healthcare sector is expanding under UHC (Universal Health "
                    "Coverage) reforms. Key roles: medical officers, nurses (KRCHN/BSN), "
                    "clinical officers, lab technicians, community health volunteers. "
                    "Average monthly salary: KES 50,000-120,000 for medical officers; "
                    "KES 30,000-60,000 for nurses in the public sector."
                ),
                "job_families": ["Medicine", "Nursing", "Clinical Medicine", "Allied Health", "Community Health"],
            },
        ],
        "salary_context": (
            "Kenya minimum wage (Nairobi general labourers): KES 16,012/month (2023). "
            "Formal-sector average monthly earnings: KES 55,000-80,000. Tea estates: "
            "KES 700/day including housing and rations. Nairobi tech workers earn "
            "KES 80,000-300,000/month. Remittances: KES 56 billion (2023)."
        ),
    },

    "ET": {
        "overview": (
            "Ethiopia is East Africa's second-largest economy (GDP USD 126 billion) "
            "with a population of 125 million. Key industries: agriculture (coffee, "
            "sesame, chat, teff, livestock — 40% of GDP), manufacturing (textile and "
            "garment industrial parks, leather, food processing), construction "
            "(infrastructure boom), financial services, public administration, and "
            "tourism (historical and cultural sites). Labour force: 60 million. "
            "Unemployment: 3.7% (largely reflects informality). Average urban monthly "
            "wage: ETB 4,000-8,000. Ethiopia's industrial parks (Hawassa, Bole Lemi) "
            "host H&M, PVH, and Walmart supply chains."
        ),
        "industries": [
            {
                "name": "Agriculture & Coffee",
                "context": (
                    "Ethiopia is the birthplace of coffee (Kaffa region) and Africa's "
                    "largest coffee producer. Smallholder farmers, coffee cooperatives, "
                    "and specialty-coffee exporters constitute the value chain. Teff, "
                    "sorghum, maize, and sesame are staple and export crops. Livestock "
                    "herding (cattle, camel, sheep) is the primary livelihood in pastoral "
                    "regions. Daily agricultural wages: ETB 80-150."
                ),
                "job_families": ["Farming", "Coffee Production", "Livestock Husbandry", "Agro-export"],
            },
            {
                "name": "Textile, Garment & Leather",
                "context": (
                    "Ethiopia's industrial parks host 100+ textile and garment factories. "
                    "Hawassa Industrial Park employs 30,000 workers in sewing, cutting, "
                    "and finishing. Addis Ababa Bole Lemi Park hosts leather footwear "
                    "factories (for export to Europe and US). Monthly wages: ETB 1,500-3,500 "
                    "for production workers; ETB 8,000-15,000 for supervisors and "
                    "production managers."
                ),
                "job_families": ["Garment Manufacturing", "Leather Crafts", "Quality Assurance", "Factory Management"],
            },
            {
                "name": "Construction & Infrastructure",
                "context": (
                    "Ethiopia's infrastructure boom (Grand Ethiopian Renaissance Dam, "
                    "Addis Ababa–Djibouti rail, urban metro) employs 500,000+ construction "
                    "workers. Key roles: civil engineers, masons, carpenters, plumbers, "
                    "structural engineers, and project managers. Monthly salary: "
                    "ETB 8,000-25,000 for engineers; ETB 2,000-5,000 for skilled workers."
                ),
                "job_families": ["Civil Engineering", "Construction Trades", "Project Management"],
            },
            {
                "name": "Tourism & Culture",
                "context": (
                    "Ethiopia's UNESCO World Heritage Sites (Lalibela, Aksum, Simien Mountains) "
                    "and cultural tourism attract 800,000 visitors annually. Key roles: "
                    "tour guides, hotel staff, cultural interpreters, airline (Ethiopian "
                    "Airlines) cabin crew, and travel agents. Ethiopian Airlines — Africa's "
                    "largest carrier — employs 20,000+ across aviation, ground handling, "
                    "and maintenance."
                ),
                "job_families": ["Tourism", "Hospitality", "Aviation", "Cultural Guiding"],
            },
        ],
        "salary_context": (
            "No statutory national minimum wage in Ethiopia. Public-sector wages "
            "follow civil service pay scales: ETB 2,100-4,500/month. Industrial park "
            "garment workers earn ETB 1,500-3,500/month. Addis Ababa urban average: "
            "ETB 5,000-8,000/month for formal workers."
        ),
    },

    "GH": {
        "overview": (
            "Ghana is a lower-middle-income economy (GDP USD 73 billion) known for "
            "political stability and a relatively developed private sector. Key industries: "
            "oil and gas (Jubilee, TEN, Sankofa offshore fields), cocoa (world's "
            "second-largest producer), gold mining (AngloGold, Newmont, Kinross), "
            "manufacturing (food and beverage, cement, aluminium), construction, "
            "financial services, retail and wholesale trade, education, and healthcare. "
            "Labour force: 14 million. Unemployment: 3.7%. Average monthly formal "
            "wage: GHS 1,800-3,500. Accra and Tema are the main industrial and "
            "services hubs."
        ),
        "industries": [
            {
                "name": "Cocoa & Agriculture",
                "context": (
                    "Cocoa employs 800,000 smallholder farmers and accounts for 20% of "
                    "export revenues. COCOBOD (Ghana Cocoa Board) buys from licensed "
                    "purchasing companies. Other key crops: cassava, yam, maize, plantain, "
                    "and cashew. Agro-processing (Olam, Barry Callebaut cocoa grinding) "
                    "employs factory workers at GHS 900-1,500/month."
                ),
                "job_families": ["Farming", "Agro-processing", "Commodity Trading"],
            },
            {
                "name": "Gold Mining",
                "context": (
                    "Ghana is Africa's largest gold producer. AngloGold Ashanti (Obuasi), "
                    "Newmont (Ahafo), and Kinross (Chirano) operate large open-pit and "
                    "underground mines. Key roles: geologists, mine engineers, drill-and-blast "
                    "supervisors, metallurgists, and mine security officers. Monthly salary: "
                    "GHS 3,000-7,000 for technicians; GHS 10,000-25,000 for engineers."
                ),
                "job_families": ["Mining Engineering", "Geology", "Metallurgy", "HSE"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "GCB Bank, Ecobank, Standard Chartered, and Fidelity Bank are major "
                    "employers. The Ghana Stock Exchange and NHIL insurance sector add "
                    "professional roles. Key occupations: bank officers, insurance agents, "
                    "financial analysts, and microfinance loan officers. Average monthly "
                    "salary: GHS 2,500-8,000."
                ),
                "job_families": ["Banking", "Insurance", "Microfinance", "Capital Markets"],
            },
        ],
        "salary_context": (
            "Ghana national daily minimum wage: GHS 18.15/day (2024). Average formal "
            "monthly wage: GHS 2,500-3,500. Public-sector SSSS pay scale: GHS 1,200-"
            "9,000/month. Mining and oil-and-gas workers earn 2-4× the formal average."
        ),
    },

    "TZ": {
        "overview": (
            "Tanzania is a lower-middle-income economy (GDP USD 77 billion) with "
            "significant tourism and mining sectors alongside subsistence agriculture. "
            "Key industries: agriculture (coffee, tea, tobacco, cotton, cashew, cloves), "
            "mining (gold, tanzanite, diamonds — Shinyanga belt), tourism (Serengeti, "
            "Kilimanjaro, Zanzibar), manufacturing (food processing, textiles, cement), "
            "financial services, construction, and public administration. Labour force: "
            "28 million. Unemployment: 2.7% (reflects high informality). Average monthly "
            "formal wage: TZS 500,000-800,000."
        ),
        "industries": [
            {
                "name": "Agriculture & Cashew",
                "context": (
                    "Agriculture employs 65% of Tanzania's labour force. Coffee (Kilimanjaro, "
                    "Mbeya), tea (Iringa), cashew (Mtwara), and cotton (Lake Zone) are "
                    "major export crops. Zanzibar cloves and seaweed are distinct industries. "
                    "Agricultural wages: TZS 5,000-10,000/day for seasonal pickers."
                ),
                "job_families": ["Farming", "Agro-processing", "Cash-crop Management"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Tanzania's national parks (Serengeti, Ngorongoro, Tarangire) and "
                    "the Zanzibar beach industry generate USD 2.5 billion/year. Key roles: "
                    "safari guides, game rangers, lodge managers, dive instructors, "
                    "and cultural tour operators. Monthly wages: TZS 400,000-1,000,000 "
                    "for lodge staff; TZS 2,000,000+ for senior managers."
                ),
                "job_families": ["Safari Guiding", "Hospitality", "Wildlife Conservation", "Diving"],
            },
            {
                "name": "Mining",
                "context": (
                    "Tanzania hosts Geita Gold Mine (AngloGold Ashanti) and Williamson "
                    "Diamond Mine. Artisanal small-scale mining (ASM) of tanzanite and gold "
                    "employs 1 million+ informal miners. Key formal roles: geologists, "
                    "metallurgists, mine supervisors, and blasting engineers. Monthly "
                    "salary: TZS 1,500,000-4,000,000."
                ),
                "job_families": ["Mining Engineering", "Geology", "ASM", "Environmental Management"],
            },
        ],
        "salary_context": (
            "Tanzania sector minimum wages (2022): agriculture TZS 55,000/month; "
            "manufacturing TZS 200,000/month; financial sector TZS 700,000/month. "
            "Formal-sector average: TZS 600,000-900,000/month."
        ),
    },

    "UG": {
        "overview": (
            "Uganda is a low-income economy (GDP USD 45 billion) with an agri-based "
            "economy and fast-growing services sector. Key industries: agriculture "
            "(coffee, tea, cotton, maize, sugarcane, vanilla — 24% of GDP), "
            "manufacturing (FMCG, sugar, cement, steel), oil and gas (Albertine Graben "
            "development), financial services, retail and wholesale trade, and "
            "construction. Labour force: 21 million. Unemployment: 3.0% (largely "
            "informal). Kampala is the main services and manufacturing hub."
        ),
        "industries": [
            {
                "name": "Coffee & Agriculture",
                "context": (
                    "Uganda is Africa's largest coffee exporter (Robusta and Arabica). "
                    "Smallholder farmers dominate; UGACOF and Kawacom are major exporters. "
                    "Tea estates in western Uganda, sugar (Kakira Sugar Works), and vanilla "
                    "(Uganda is world's third-largest vanilla producer) are other key sectors. "
                    "Daily agricultural wages: UGX 5,000-10,000."
                ),
                "job_families": ["Farming", "Coffee Processing", "Agro-export", "Estate Management"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Stanbic Uganda, Absa, DFCU, and Centenary Bank are major employers. "
                    "Mobile money (MTN MoMo, Airtel Money) employs thousands of agents. "
                    "Key roles: bank officers, microfinance field officers, insurance "
                    "agents, and mobile-money agents. Monthly salary: UGX 700,000-2,500,000."
                ),
                "job_families": ["Banking", "Microfinance", "Insurance", "Mobile Money"],
            },
            {
                "name": "Oil & Gas (Emerging)",
                "context": (
                    "The Lake Albert oil development (Total TotalEnergies, CNOOC, Uganda "
                    "National Oil Company) involves 6 billion barrel reserves. EACOP "
                    "(East African Crude Oil Pipeline) is under construction. Key roles: "
                    "petroleum engineers, pipeline construction workers, HSE officers, "
                    "environmental specialists, and community liaison officers."
                ),
                "job_families": ["Petroleum Engineering", "Pipeline Construction", "HSE", "Environmental Management"],
            },
        ],
        "salary_context": (
            "Uganda has no statutory national minimum wage. Civil service grade scale: "
            "UGX 350,000-2,500,000/month. Manufacturing average: UGX 600,000-900,000/month. "
            "Oil-sector technical roles: UGX 3,000,000-8,000,000/month."
        ),
    },

    "RW": {
        "overview": (
            "Rwanda is a low-income but fast-growing economy (GDP per capita USD 975, "
            "growing 8%/year). Key sectors: services and tourism (Kigali convention hub, "
            "gorilla trekking), agriculture (coffee, tea, pyrethrum, horticulture), "
            "financial services, construction, manufacturing (apparel under MADE IN "
            "RWANDA policy), ICT and BPO, and public administration. Labour force: "
            "5.2 million. Kigali is emerging as East Africa's conference and tech hub. "
            "Government targets service-led economic transformation under Vision 2050."
        ),
        "industries": [
            {
                "name": "Tourism & Gorilla Trekking",
                "context": (
                    "Rwanda earns USD 400 million+/year from tourism. Gorilla-trekking "
                    "permits (USD 1,500 each) support conservation. Key roles: park rangers, "
                    "eco-lodge managers, conference interpreters, hotel and MICE staff, "
                    "and RDB-licensed tour operators. Monthly wage: RWF 80,000-250,000."
                ),
                "job_families": ["Wildlife Conservation", "Hospitality", "MICE Management", "Tourism"],
            },
            {
                "name": "Agriculture & Coffee",
                "context": (
                    "Coffee (specialty Bourbon Arabica from Huye, Kayonza) and tea "
                    "are Rwanda's top agricultural exports. RWASHOSCCO and Maraba Coop "
                    "are premium-coffee cooperatives. Horticulture exports (flowers, "
                    "French beans) to Europe are growing. Daily agricultural wages: "
                    "RWF 2,000-4,000."
                ),
                "job_families": ["Farming", "Coffee Cooperatives", "Agro-export", "Horticulture"],
            },
            {
                "name": "Financial Services & Fintech",
                "context": (
                    "Bank of Kigali, I&M Bank, and BPR (Banque Populaire du Rwanda) "
                    "anchor the formal banking sector. MTN MoMo and Airtel Money are "
                    "dominant mobile money platforms. Kigali International Finance Centre "
                    "(KIFC) targets offshore financial services. Monthly salary for "
                    "professionals: RWF 300,000-900,000."
                ),
                "job_families": ["Banking", "Mobile Money", "Insurance", "Development Finance"],
            },
        ],
        "salary_context": (
            "Rwanda minimum wage: not nationally mandated by sector (being reformed). "
            "Public service pay scale: RWF 60,000-1,200,000/month. Private formal "
            "average: RWF 150,000-400,000/month. Kigali wage premium ~30% over rural areas."
        ),
    },

    "AO": {
        "overview": (
            "Angola is an upper-middle-income, oil-dependent economy (GDP USD 92 "
            "billion) with significant agriculture and mining potential. Key industries: "
            "oil and gas (80% of government revenue, Sonangol), diamond mining "
            "(Catoca mine, Endiama), agriculture (coffee, sisal, fishing), "
            "construction (post-civil-war reconstruction), financial services, "
            "retail, and telecommunications. Labour force: 14 million. Luanda is "
            "one of Africa's most expensive cities. Average monthly formal wage: "
            "AOA 150,000-300,000."
        ),
        "industries": [
            {
                "name": "Oil & Gas",
                "context": (
                    "Angola is Africa's second-largest oil producer, with Sonangol "
                    "and IOCs (TotalEnergies, BP, Chevron, Eni) operating offshore "
                    "deepwater fields. Key roles: petroleum engineers, subsea engineers, "
                    "HSE officers, drilling supervisors, and rig workers. Monthly salary: "
                    "USD 3,000-10,000 for expat engineers; AOA 500,000-1,500,000 for "
                    "local professionals."
                ),
                "job_families": ["Petroleum Engineering", "Offshore Operations", "HSE"],
            },
            {
                "name": "Construction & Infrastructure",
                "context": (
                    "Post-war reconstruction and ongoing urbanisation sustain massive "
                    "construction demand. Chinese contractors co-build with local firms. "
                    "Key roles: civil engineers, construction workers, architects, "
                    "quantity surveyors, and project managers. Monthly salary: "
                    "AOA 200,000-600,000 for engineers."
                ),
                "job_families": ["Civil Engineering", "Construction", "Architecture", "Infrastructure"],
            },
            {
                "name": "Agriculture & Fishing",
                "context": (
                    "Pre-independence, Angola was a major coffee and sisal exporter. "
                    "Reconstruction of the agricultural sector is a national priority. "
                    "Key roles: smallholder farmers, commercial-farm managers, "
                    "fishing-boat crews, cold-chain logistics staff, and agri-input dealers."
                ),
                "job_families": ["Farming", "Fisheries", "Agro-processing"],
            },
        ],
        "salary_context": (
            "Angola minimum wage: AOA 70,000/month (2023). Formal-sector average: "
            "AOA 200,000-400,000/month. Oil-sector and multinational pay scales are "
            "significantly higher, often partially in USD."
        ),
    },

    "EG": {
        "overview": (
            "Egypt is Africa's third-largest economy (GDP USD 396 billion) with a "
            "highly diversified labour market. Key industries: Suez Canal services "
            "(12% of world trade tonnage), tourism (Pharaonic, Red Sea), oil and "
            "gas (EGPC, Zohr gas field), manufacturing (textiles, food processing, "
            "chemicals, steel), agriculture (cotton, wheat, citrus, sugarcane), "
            "financial services, construction (New Administrative Capital megaproject), "
            "and public administration. Labour force: 32 million. Unemployment: 7.1%. "
            "Average monthly formal wage: EGP 4,500-8,000."
        ),
        "industries": [
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Egypt attracted 15 million tourists in 2023. Luxor, Cairo, Aswan, "
                    "and Red Sea (Sharm el-Sheikh, Hurghada) are major hubs. Key roles: "
                    "hotel staff, tour guides, diving instructors, antiquities guides, "
                    "travel agents, and MICE coordinators. Monthly wage: EGP 3,500-8,000 "
                    "for hotel staff; EGP 10,000-20,000 for senior managers."
                ),
                "job_families": ["Hospitality", "Tourism", "Diving", "Event Management"],
            },
            {
                "name": "Suez Canal & Logistics",
                "context": (
                    "The Suez Canal Authority employs 26,000 and generates USD 9 billion/year. "
                    "Port operations, shipping agencies, and free-zone logistics in Port Said "
                    "and Ain Sokhna employ 150,000+. Key roles: maritime pilots, port "
                    "operators, freight forwarders, customs brokers, and logistics analysts."
                ),
                "job_families": ["Maritime", "Port Operations", "Logistics", "Trade Finance"],
            },
            {
                "name": "Textile & Apparel",
                "context": (
                    "Egypt's cotton textile industry (Egyptian Giza cotton) employs 1 million+. "
                    "Garment factories in Tenth of Ramadan, Borg El Arab, and QNFTZ supply "
                    "European brands. Key roles: spinning operators, weavers, sewing machine "
                    "operators, quality controllers, and textile engineers. Monthly wage: "
                    "EGP 3,000-6,000 for production workers."
                ),
                "job_families": ["Textile Manufacturing", "Garment Production", "Quality Assurance"],
            },
            {
                "name": "Agriculture",
                "context": (
                    "Agriculture employs 23% of the workforce along the Nile Delta and valley. "
                    "Key crops: wheat, maize, cotton, sugarcane, citrus, vegetables, and "
                    "strawberries for export. Irrigation workers, seasonal farm labourers, "
                    "and agri-engineers are major occupational groups. Daily wage: EGP 150-250."
                ),
                "job_families": ["Farming", "Irrigation Engineering", "Agro-processing"],
            },
        ],
        "salary_context": (
            "Egypt minimum wage: EGP 6,000/month (2024). Government civil service average: "
            "EGP 4,500-7,000/month. Private formal sector: EGP 5,000-12,000/month. "
            "Suez Canal and tourism workers earn above average. High inflation has "
            "eroded real wages significantly since 2022."
        ),
    },

    "MA": {
        "overview": (
            "Morocco is a lower-middle-income economy (GDP USD 142 billion) with "
            "strong trade links to Europe. Key industries: phosphate mining and "
            "chemicals (OCP Group — world's largest phosphate exporter), automotive "
            "manufacturing (Stellantis, Renault assembly in Tangier and Kenitra), "
            "aerospace components (Safran, Boeing supply chain in Casablanca), "
            "textiles and garments, agriculture (citrus, olive oil, berries, tomatoes), "
            "tourism (Marrakesh, Agadir, Fes), and financial services. Labour force: "
            "12 million. Unemployment: 13% (youth: 31%). Average monthly formal wage: "
            "MAD 4,000-6,500."
        ),
        "industries": [
            {
                "name": "Automotive Manufacturing (Offshoring)",
                "context": (
                    "Morocco produces 700,000 vehicles/year at Tangier Med industrial complex. "
                    "Renault, Stellantis (Peugeot Citroën), and 300+ Tier-1 suppliers employ "
                    "90,000+ workers. Key roles: assembly operators, quality technicians, "
                    "logistics coordinators, industrial engineers, and production supervisors. "
                    "Monthly wages: MAD 2,500-4,500 for operators; MAD 8,000-20,000 for engineers."
                ),
                "job_families": ["Automotive Manufacturing", "Engineering", "Logistics", "Quality Control"],
            },
            {
                "name": "Phosphate & Chemicals (OCP Group)",
                "context": (
                    "OCP Group extracts 36 million tonnes of phosphate rock annually and "
                    "produces DAP/MAP fertilisers for Africa, Brazil, and India. Key roles: "
                    "mining engineers, chemical process engineers, R&D scientists, and "
                    "logistics coordinators. Monthly salary: MAD 8,000-20,000."
                ),
                "job_families": ["Mining Engineering", "Chemical Engineering", "Agri-chemicals R&D"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Morocco attracted 14.5 million tourists in 2023. Marrakesh riads, "
                    "Agadir beach resorts, and cultural circuits (Fes, Chefchaouen) are "
                    "main products. Key roles: hotel staff, tour guides, riad managers, "
                    "spa therapists, and craft artisans. Monthly wage: MAD 3,000-6,000."
                ),
                "job_families": ["Hospitality", "Tourism", "Handicrafts", "Wellness"],
            },
            {
                "name": "Agriculture & Agro-export",
                "context": (
                    "Morocco exports EUR 2.8 billion in agricultural products. Souss-Massa "
                    "valley produces tomatoes, citrus, and strawberries for European supermarkets. "
                    "Olive oil (Meknes), argan oil (Souss), and rose-water (Dades valley) "
                    "are premium exports. Seasonal agricultural workers earn MAD 80-120/day."
                ),
                "job_families": ["Farming", "Agro-export", "Food Technology", "Organic Certification"],
            },
        ],
        "salary_context": (
            "Morocco SMIG minimum wage: MAD 3,111/month (2024). Agricultural SMAG: "
            "MAD 84.37/day. Average formal monthly salary: MAD 4,500-6,500. "
            "Automotive and aerospace sectors pay 40-80% above national average."
        ),
    },

    "SN": {
        "overview": (
            "Senegal is a lower-middle-income economy (GDP USD 28 billion) with "
            "recent oil and gas discoveries. Key sectors: agriculture (groundnuts, "
            "millet, rice, horticulture), fishing and fish processing, mining (phosphate, "
            "gold, zircon), financial services, tourism (Dakar, Saloum delta), "
            "construction, public administration, and emerging oil and gas (Sangomar "
            "field, Greater Tortue LNG). Labour force: 7 million. Unemployment: 5.7%. "
            "Dakar is a major West African services hub and UN/NGO headquarters."
        ),
        "industries": [
            {
                "name": "Fishing & Fish Processing",
                "context": (
                    "Senegal has one of West Africa's richest fishing grounds. Artisanal "
                    "fishers in Kayar and Joal, and industrial trawlers, supply fresh "
                    "and dried fish domestically and for export to Europe. Fish-processing "
                    "plants (Thiaroye) employ women fish smokers and factory workers. "
                    "Daily wages: XOF 2,000-5,000 for artisanal fishers."
                ),
                "job_families": ["Fisheries", "Aquaculture", "Fish Processing", "Maritime"],
            },
            {
                "name": "Agriculture & Groundnuts",
                "context": (
                    "Groundnut (peanut) cultivation is the traditional backbone of Senegalese "
                    "agriculture. Horticulture exports (green beans, cherry tomatoes) to Europe "
                    "via Niayes corridor. Key roles: smallholder farmers, irrigation workers, "
                    "and cooperative managers. Daily agricultural wages: XOF 1,500-3,000."
                ),
                "job_families": ["Farming", "Horticulture", "Agro-processing"],
            },
            {
                "name": "Financial Services & Mobile Money",
                "context": (
                    "CBAO, Ecobank, BHS, and BNDE serve the formal banking market. "
                    "Orange Money and Wave (a Senegalese fintech) dominate mobile money. "
                    "Key roles: bank officers, mobile-money agents, insurance sales reps, "
                    "and microfinance credit officers. Monthly salary: XOF 150,000-400,000."
                ),
                "job_families": ["Banking", "Mobile Money", "Microfinance", "Insurance"],
            },
        ],
        "salary_context": (
            "Senegal SMIG minimum wage: XOF 63,002/month (2023). Average formal "
            "monthly salary: XOF 200,000-400,000. Dakar wages 30-50% higher than rural. "
            "Oil-sector technical roles will pay USD-equivalent rates from 2024 onwards."
        ),
    },

    "CI": {
        "overview": (
            "Côte d'Ivoire is the world's largest cocoa producer and the economic "
            "powerhouse of Francophone West Africa (GDP USD 70 billion). Key industries: "
            "cocoa and coffee agriculture (40% of export revenues), rubber, palm oil, "
            "cashew, manufacturing (FMCG, food processing, textiles), financial services, "
            "construction, petroleum refining (SIR), and port logistics (Abidjan — "
            "largest port in West Africa). Labour force: 9 million. Unemployment: 2.8%."
        ),
        "industries": [
            {
                "name": "Cocoa & Agriculture",
                "context": (
                    "Côte d'Ivoire produces 2.2 million metric tonnes of cocoa beans/year. "
                    "Farmer cooperatives (ANAPROCI, COOPAD) work with exporters Barry Callebaut, "
                    "Olam, and Cargill. Cashew is the second-largest export crop. Rubber "
                    "(SAPH, SOGB) and palm oil (PALMCI) employ plantation workers. "
                    "Daily farm wages: XOF 1,200-2,500."
                ),
                "job_families": ["Farming", "Cocoa Processing", "Cash-crop Management", "Agro-export"],
            },
            {
                "name": "Port Logistics & Trade",
                "context": (
                    "Port Autonome d'Abidjan handles 24 million tonnes/year and serves "
                    "landlocked Sahel countries (Burkina Faso, Mali, Niger). Key roles: "
                    "freight forwarders, customs brokers, port operations managers, "
                    "logistics coordinators, and ship agents. Monthly salary: "
                    "XOF 300,000-700,000."
                ),
                "job_families": ["Logistics", "Port Operations", "Customs", "Trade Finance"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Abidjan is the financial capital of Francophone West Africa, hosting "
                    "BCEAO headquarters and the BRVM regional stock exchange. SGBCI, "
                    "Ecobank CI, and Société Ivoirienne de Banque are major employers. "
                    "Key roles: bank officers, stockbrokers, insurance underwriters, "
                    "and microfinance officers. Monthly salary: XOF 200,000-600,000."
                ),
                "job_families": ["Banking", "Capital Markets", "Insurance", "Microfinance"],
            },
        ],
        "salary_context": (
            "Côte d'Ivoire SMIG minimum wage: XOF 75,000/month (2023). Formal-sector "
            "average: XOF 250,000-450,000/month. Abidjan wages 20-30% above national average. "
            "Port-sector and international-company workers earn 2-4× the SMIG."
        ),
    },

    "CM": {
        "overview": (
            "Cameroon is a low-middle-income economy often called 'Africa in miniature' "
            "for its ecological and economic diversity (GDP USD 47 billion). Key industries: "
            "oil and gas (SNH), agriculture (cocoa, coffee, palm oil, banana — Central "
            "Africa's largest agri-exporter), aluminium smelting (Alucam, Edéa), timber "
            "and wood processing, financial services, construction, and telecommunications. "
            "Douala is the primary industrial port; Yaoundé is the administrative capital. "
            "Labour force: 10 million. Unemployment: 3.5%."
        ),
        "industries": [
            {
                "name": "Cocoa, Coffee & Agriculture",
                "context": (
                    "Cameroon is Africa's fourth-largest cocoa producer and a significant "
                    "arabica coffee origin. SODECAO supports smallholder cocoa farmers. "
                    "Banana exports (Del Monte, Dole) and palm oil (Socapalm) are large "
                    "commercial operations. Daily agricultural wages: XAF 1,500-3,000."
                ),
                "job_families": ["Farming", "Agro-processing", "Plantation Management"],
            },
            {
                "name": "Oil & Gas",
                "context": (
                    "Cameroon's offshore oil production (circa 70,000 bpd) generates "
                    "key government revenue. SNH (Société Nationale des Hydrocarbures) "
                    "and IOCs (TotalEnergies, Perenco) operate offshore fields. "
                    "Key roles: petroleum engineers, HSE officers, and plant operators. "
                    "Monthly salary: XAF 400,000-1,200,000."
                ),
                "job_families": ["Petroleum Engineering", "Offshore Operations", "HSE"],
            },
            {
                "name": "Timber & Wood Processing",
                "context": (
                    "Cameroon is Central Africa's leading timber exporter. Forest concessions "
                    "employ chainsaw operators, log graders, sawmill workers, and forest "
                    "engineers. FLEG (Forest Law Enforcement and Governance) compliance "
                    "requires certified foresters. Daily wages: XAF 2,000-4,500."
                ),
                "job_families": ["Forestry", "Wood Processing", "Environmental Compliance"],
            },
        ],
        "salary_context": (
            "Cameroon SMIG minimum wage: XAF 36,270/month (2014, not yet revised). "
            "Formal-sector average: XAF 200,000-350,000/month. Oil, mining, and "
            "international-company workers earn 3-5× the SMIG."
        ),
    },

    "DZ": {
        "overview": (
            "Algeria is a lower-middle-income, hydrocarbon-dependent economy "
            "(GDP USD 191 billion). Key industries: oil and gas (Sonatrach — Africa's "
            "largest energy company), construction (infrastructure plan), agriculture "
            "(cereals, dates, vegetables, sheep and cattle), manufacturing (steel, "
            "vehicles, pharmaceuticals), financial services (largely public-sector banks), "
            "and public administration. Labour force: 13 million. Unemployment: 11.8%. "
            "Oran, Algiers, and Constantine are the main economic centres."
        ),
        "industries": [
            {
                "name": "Oil, Gas & Petrochemicals",
                "context": (
                    "Sonatrach employs 130,000 directly and is the backbone of the "
                    "Algerian economy. Hassi Messaoud oilfield and Hassi R'Mel gas "
                    "field are the largest. Key roles: petroleum engineers, refinery "
                    "operators, drilling engineers, geophysicists, and maintenance "
                    "technicians. Monthly salary: DZD 80,000-250,000 for professionals."
                ),
                "job_families": ["Petroleum Engineering", "Refinery Operations", "Geoscience"],
            },
            {
                "name": "Agriculture & Date Production",
                "context": (
                    "Algeria is the world's largest date exporter (Deglet Nour from "
                    "Biskra). The Mitidja plain produces vegetables and cereals. "
                    "Sheep and cattle husbandry is a major livelihood in highland steppes. "
                    "Agricultural daily wages: DZD 800-1,200."
                ),
                "job_families": ["Farming", "Date Production", "Livestock", "Agro-processing"],
            },
            {
                "name": "Construction & Public Works",
                "context": (
                    "Algeria's multi-year public infrastructure programmes include roads, "
                    "housing, and urban rail (Algiers, Oran, Constantine metros). Key roles: "
                    "civil engineers, construction workers, quantity surveyors, and project "
                    "managers. Monthly salary: DZD 50,000-150,000 for engineers."
                ),
                "job_families": ["Civil Engineering", "Construction Trades", "Urban Planning"],
            },
        ],
        "salary_context": (
            "Algeria SNMG minimum wage: DZD 20,000/month (2020; subject to revision). "
            "Public-sector average: DZD 40,000-80,000/month. Oil-sector workers: "
            "DZD 100,000-300,000/month. High youth unemployment drives emigration to France."
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
        "continent": "Africa",
        "country": country_iso2,
        "region": cm.get("region", "Africa"),
        "sub_region": cm.get("sub_region", ""),
        "market_tier": cm.get("market_tier", "frontier"),
        "currency": cm.get("currency", ""),
        "industries": [industry] if industry else [],
        "job_families": [],
        "published_at": _FETCHED_AT[:10],
        "tags": ["africa", cm.get("sub_region", "africa").lower().replace(" ", "-").replace("/", "-")],
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
    meta["tags"] += ["overview", "labour-market", "all-industries"]

    return {
        "doc_id": f"africa_overview_{country_iso2.lower()}",
        "title": f"{country_name} Labour Market Overview",
        "content": content.strip(),
        "metadata": meta,
    }


def build_industry_doc(country_iso2: str, industry_data: dict) -> dict:
    cm = COUNTRY_META.get(country_iso2, {})
    country_name = cm.get("name", country_iso2)
    ind_name = industry_data["name"]
    slug = ind_name.lower().replace(" ", "_").replace("&", "and")[:40]
    slug = slug.replace("(", "").replace(")", "").replace(",", "")

    content = f"# {country_name} — {ind_name}\n\n"
    content += industry_data["context"] + "\n"

    meta = _base_meta(country_iso2, "industry", ind_name)
    meta["industries"] = [ind_name]
    meta["job_families"] = industry_data.get("job_families", [])
    meta["tags"] += ["industry", slug[:30]]

    return {
        "doc_id": f"africa_{country_iso2.lower()}_{slug[:35]}",
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
    africa_countries = REGION_COUNTRIES.get("africa", [])
    if not africa_countries:
        print("[WARN] No African countries found in REGION_COUNTRIES")
        return []

    print(f"[ILO] Fetching occupation earnings for {len(africa_countries)} African countries...")
    occ_data = fetch_ilo_data(
        "EAR_4MTH_SEX_OCU_NB_A",
        africa_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    print(f"[ILO] Fetching industry earnings for {len(africa_countries)} African countries...")
    ind_data = fetch_ilo_data(
        "EAR_4MTH_SEX_ECO_NB_A",
        africa_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    docs = []
    for iso2 in africa_countries:
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
    print("[Africa] Building curated country/industry documents...")
    curated = build_curated_docs()
    print(f"[Africa] Curated docs: {len(curated)}")

    print("[Africa] Fetching ILO supplement...")
    ilo_docs = build_ilo_supplement(start_year=start_year, use_cache=use_cache)
    print(f"[Africa] ILO docs: {len(ilo_docs)}")

    all_docs = curated + ilo_docs
    seen: dict[str, dict] = {}
    for doc in all_docs:
        doc_id = doc.get("doc_id", "")
        if doc_id not in seen:
            seen[doc_id] = doc
    deduped = list(seen.values())
    print(f"[Africa] Total unique docs: {len(deduped)}")

    if dry_run:
        print("[Africa] Dry run — not writing output file")
        return deduped

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)
    print(f"[Africa] Written: {_OUTPUT_FILE}")
    return deduped


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Africa labour-market data for RAG KB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--start-year", type=int, default=2018)
    args = parser.parse_args()

    docs = build_all_docs(
        start_year=args.start_year,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )

    print(f"\n[Africa] Done. {len(docs)} documents produced.")
    country_counts: dict[str, int] = {}
    for doc in docs:
        c = doc.get("metadata", {}).get("country", "unknown")
        country_counts[c] = country_counts.get(c, 0) + 1
    for c, n in sorted(country_counts.items()):
        print(f"  {c}: {n} docs")


if __name__ == "__main__":
    main()
