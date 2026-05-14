"""Fetch Latin America & Caribbean labour-market data for the global-market KB.

Covers 17 countries across South America, Central America, and the Caribbean:
  South America:   Brazil (BR), Mexico (MX), Argentina (AR), Colombia (CO),
                   Chile (CL), Peru (PE), Ecuador (EC), Bolivia (BO),
                   Uruguay (UY), Paraguay (PY)
  Central America: Panama (PA), Costa Rica (CR), Guatemala (GT), Honduras (HN)
  Caribbean:       Dominican Republic (DO), Jamaica (JM), Trinidad & Tobago (TT)

Sources:
  - ILO ILOSTAT SDMX REST API (backbone for all countries, all job families)
  - Curated country context covering ALL industries for the 5 largest economies
    (Brazil, Mexico, Argentina, Colombia, Chile)

Output:
  agents/data/knowledge-base/global_market_latam.json

Usage:
  python fetch_latam_market.py                        # all countries
  python fetch_latam_market.py --dry-run              # validate only
  python fetch_latam_market.py --no-cache             # bypass disk cache
  python fetch_latam_market.py --start-year 2018      # narrow year range
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
_OUTPUT_FILE = _REPO_ROOT / "data" / "knowledge-base" / "global_market_latam.json"
_FETCHED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Curated country context ────────────────────────────────────────────────────

_COUNTRY_CONTEXT: dict[str, dict] = {
    "BR": {
        "overview": (
            "Brazil is Latin America's largest economy (GDP USD 2.1 trillion) and "
            "the world's seventh most populous country (215 million). Key industries: "
            "agriculture and agribusiness (soybeans, maize, coffee, sugar, beef, "
            "poultry — Brazil is the world's largest beef exporter), mining (iron ore, "
            "bauxite, niobium — Vale is the world's largest iron-ore producer), oil "
            "and gas (Petrobras deepwater pre-salt), manufacturing (automotive, aircraft "
            "with Embraer, food processing, chemicals, pulp and paper), financial "
            "services, construction, retail and wholesale trade, and healthcare. "
            "Unemployment: 7.8% (IBGE, 2023). Average formal monthly wage: BRL 3,300. "
            "The CLT labour regime governs most formal employment; the gig economy "
            "(delivery apps, freelancers) now accounts for 13 million workers."
        ),
        "industries": [
            {
                "name": "Agribusiness & Food",
                "context": (
                    "Brazil's agribusiness complex (agronegócio) contributes 25% of GDP. "
                    "Soybeans and maize (Centre-West cerrado), sugarcane (São Paulo state, "
                    "ethanol/sugar), coffee (Minas Gerais, Espírito Santo), citrus, poultry "
                    "(BRF, JBS supply chain), and beef cattle ranching are the pillars. "
                    "Key roles: agronomists (CREA-registered), farm managers, rural credit "
                    "officers, cooperative technicians, tractor operators, and food-plant "
                    "workers. Monthly wages: BRL 1,400-2,500 for rural workers; BRL 6,000-15,000 "
                    "for agronomists and agribusiness analysts."
                ),
                "job_families": ["Agronomy", "Animal Science", "Food Technology", "Agri-trade", "Rural Finance"],
            },
            {
                "name": "Mining & Metals",
                "context": (
                    "Vale produces 300 million tonnes of iron ore/year (Carajás, Minas Gerais). "
                    "Brazil is the world's sole commercial producer of niobium and a top-5 "
                    "bauxite/aluminium producer. Key roles: mining engineers, geologists, "
                    "metallurgists, heavy-equipment operators, blasters, environmental analysts, "
                    "and HSE officers. Monthly salary: BRL 5,000-12,000 for engineers; "
                    "BRL 3,000-5,500 for technicians."
                ),
                "job_families": ["Mining Engineering", "Geology", "Metallurgy", "HSE"],
            },
            {
                "name": "Oil, Gas & Renewable Energy",
                "context": (
                    "Petrobras operates in deepwater pre-salt basins (Santos and Campos). "
                    "Brazil is also the world's second-largest biofuel producer (sugarcane "
                    "ethanol). Wind and solar capacity (Nordeste region) are growing rapidly. "
                    "Key roles: petroleum engineers, offshore rig operators, subsea engineers, "
                    "energy traders, bioenergy specialists. Monthly salary: BRL 8,000-20,000."
                ),
                "job_families": ["Petroleum Engineering", "Renewable Energy", "Offshore Operations", "Energy Trading"],
            },
            {
                "name": "Manufacturing (Automotive & Aerospace)",
                "context": (
                    "Brazil's automotive industry (VW, GM, Stellantis, Toyota, Hyundai "
                    "in São Paulo-Paraná cluster) produces 2.7 million vehicles/year. "
                    "Embraer is the world's third-largest commercial aircraft maker. "
                    "Footwear (Vale dos Sinos) and home appliances (Manaus Free Zone) "
                    "are other key clusters. Monthly salary: BRL 2,800-5,500 for skilled "
                    "production workers; BRL 8,000-18,000 for aerospace engineers."
                ),
                "job_families": ["Automotive Manufacturing", "Aerospace Engineering", "Manufacturing", "Quality Engineering"],
            },
            {
                "name": "Financial Services & Fintech",
                "context": (
                    "Brazil's banking sector (Itaú Unibanco, Bradesco, Caixa, Banco do "
                    "Brasil, BTG Pactual) is the most sophisticated in Latin America. "
                    "Nubank, PicPay, and Mercado Pago are global-scale fintechs. "
                    "Key roles: financial analysts, credit underwriters, investment bankers, "
                    "actuaries, insurance brokers, and digital-product managers. Monthly "
                    "salary: BRL 7,000-25,000 for professionals."
                ),
                "job_families": ["Banking", "Fintech", "Insurance", "Actuarial", "Capital Markets"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Brazil's SUS (universal public health system) plus a large private "
                    "health-insurance market (Hapvida, Unimed, Amil) employ 4 million. "
                    "Key roles: physicians (CRM-registered), nurses (COREN), pharmacists "
                    "(CRF), physiotherapists, psychologists, and dentists. Federal public "
                    "servant salary: BRL 4,500-11,000. Private hospital specialists: "
                    "BRL 12,000-35,000."
                ),
                "job_families": ["Medicine", "Nursing", "Pharmacy", "Allied Health", "Dentistry"],
            },
            {
                "name": "Retail & E-commerce",
                "context": (
                    "Magazine Luiza, Grupo Americanas, Mercado Livre, and Amazon Brazil "
                    "employ hundreds of thousands. Brazil has Latin America's largest "
                    "e-commerce market (BRL 185 billion, 2023). Key roles: store associates, "
                    "warehouse pickers, delivery couriers (iFood, Rappi, Lalamove gig "
                    "workers), category managers, and logistics analysts. Gig couriers "
                    "earn BRL 1,800-3,500/month."
                ),
                "job_families": ["Retail", "E-commerce", "Logistics", "Delivery", "Digital Marketing"],
            },
        ],
        "salary_context": (
            "Brazil minimum wage: BRL 1,412/month (2024). Average formal monthly wage: "
            "BRL 3,300. São Paulo wages are 40-60% above national average. FGTS (8% "
            "employer monthly contribution) and INSS social security add ~30% to payroll cost. "
            "Informal sector (40% of workforce) earns below minimum wage."
        ),
    },

    "MX": {
        "overview": (
            "Mexico is Latin America's second-largest economy (GDP USD 1.3 trillion) "
            "and the US's largest trading partner. Key industries: manufacturing "
            "(IMMEX maquiladora programme — automotive, electronics, aerospace, medical "
            "devices), oil and gas (PEMEX), agriculture (avocado, tomato, berries, "
            "tequila, maize), tourism (Cancún, Los Cabos, Mexico City), financial "
            "services, construction, and retail (OXXO convenience stores — 20,000 "
            "locations). Labour force: 59 million. Unemployment: 2.9% (very low). "
            "Average formal monthly wage: MXN 9,200. Near-shoring driven by US-China "
            "decoupling is a major employment driver, especially in Monterrey, Saltillo, "
            "Querétaro, and Aguascalientes."
        ),
        "industries": [
            {
                "name": "Automotive & Near-shore Manufacturing",
                "context": (
                    "Mexico is the world's fourth-largest vehicle producer. GM, Ford, "
                    "Stellantis, VW, BMW, Toyota, Honda, and Kia have assembly plants. "
                    "Aerospace (Bombardier, Safran, Honeywell — Querétaro/Chihuahua) and "
                    "electronics (Foxconn, Jabil — Ciudad Juárez) are growing near-shoring "
                    "sectors. Key roles: production operators, quality engineers, tooling "
                    "technicians, IE engineers, and supply-chain planners. Monthly salary: "
                    "MXN 8,000-18,000 for operators; MXN 25,000-60,000 for engineers."
                ),
                "job_families": ["Automotive Manufacturing", "Aerospace", "Electronics Manufacturing", "Engineering"],
            },
            {
                "name": "Agriculture & Agro-export",
                "context": (
                    "Mexico is the world's largest avocado producer (Michoacán) and a "
                    "top exporter of tomatoes, berries, and tequila. SENASICA-registered "
                    "agronomists manage export certifications. Seasonal jornalero (day "
                    "labour) wages: MXN 250-350/day. Farm managers and agri-export "
                    "coordinators earn MXN 15,000-35,000/month."
                ),
                "job_families": ["Agronomy", "Horticulture", "Agri-export", "Food Safety"],
            },
            {
                "name": "Tourism & Hospitality",
                "context": (
                    "Mexico attracts 42 million tourists/year. Cancún, Los Cabos, Riviera "
                    "Maya, Puerto Vallarta, and Mexico City generate 8% of GDP. Key roles: "
                    "hotel staff, tour guides, restaurant workers, resort managers, and "
                    "MICE event coordinators. Monthly salary: MXN 6,000-14,000 for line "
                    "staff; MXN 25,000-60,000 for hotel GMs."
                ),
                "job_families": ["Hospitality", "Tourism", "F&B", "Event Management"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "BBVA México, Banorte, Citibanamex, Santander, and HSBC México are "
                    "the main employers. The fintech sector (Kueski, Clip, Konfío) has "
                    "grown rapidly. Key roles: bank relationship managers, risk analysts, "
                    "insurance agents, wealth advisers, and compliance officers. Monthly "
                    "salary: MXN 18,000-50,000."
                ),
                "job_families": ["Banking", "Fintech", "Insurance", "Wealth Management"],
            },
            {
                "name": "Oil & Gas (PEMEX)",
                "context": (
                    "PEMEX employs 140,000 directly and operates refineries, petrochemical "
                    "plants, and offshore platforms in the Gulf of Mexico. Key roles: "
                    "petroleum engineers, chemical engineers, refinery operators, HSE "
                    "supervisors, and pipeline integrity engineers. Monthly salary: "
                    "MXN 25,000-80,000."
                ),
                "job_families": ["Petroleum Engineering", "Chemical Engineering", "Refinery Operations", "HSE"],
            },
            {
                "name": "Retail & Informal Commerce",
                "context": (
                    "FEMSA (OXXO), Walmart México, Chedraui, and Soriana anchor formal "
                    "retail. Mexico's informal sector (55% of workforce) is visible in "
                    "street markets (tianguis), food vendors, and home workers. Key formal "
                    "retail roles: cashiers, store managers, buyers, distribution-centre "
                    "staff. Monthly salary: MXN 7,500-14,000."
                ),
                "job_families": ["Retail", "Supply Chain", "Customer Service"],
            },
        ],
        "salary_context": (
            "Mexico minimum wage: MXN 248.93/day (general); MXN 374.89/day in northern "
            "border zone (2024). Average formal monthly wage: MXN 9,200. IMSS social "
            "security adds ~25% to payroll cost. Manufacturing near-shoring wages in "
            "Monterrey and Querétaro are 30-50% above national average."
        ),
    },

    "AR": {
        "overview": (
            "Argentina is an upper-middle-income economy (GDP USD 620 billion) "
            "characterised by strong agricultural exports, skilled labour, and recurring "
            "macroeconomic instability. Key industries: agriculture and agribusiness "
            "(soybeans, maize, wheat, sunflower, beef, wine — Argentina is the world's "
            "fifth-largest wine producer), oil and gas (Vaca Muerta shale — world's "
            "fourth-largest shale gas reserve), mining (lithium in the Puna — 'Lithium "
            "Triangle'), manufacturing (food, automotive, chemicals, pharmaceuticals), "
            "financial services, software exports (USD 3 billion), healthcare, and "
            "education. Labour force: 20 million. Unemployment: 6.2%."
        ),
        "industries": [
            {
                "name": "Agriculture & Wine",
                "context": (
                    "Argentina is the world's third-largest soybean producer and "
                    "fifth-largest wine producer. The Pampas produce soybeans, maize, "
                    "and wheat on large estancias; Mendoza and San Juan produce Malbec "
                    "and Torrontés wines for export. Key roles: agronomists, estancia "
                    "managers, viticulturists, oenologists, grain traders, and rural "
                    "extension workers. Monthly salary: ARS 400,000-800,000 for professionals."
                ),
                "job_families": ["Agronomy", "Viticulture", "Agri-trade", "Food Science"],
            },
            {
                "name": "Oil, Gas & Lithium",
                "context": (
                    "Vaca Muerta (Neuquén province) is Argentina's shale hydrocarbon "
                    "mega-project. YPF, Shell, Chevron, and TotalEnergies operate. "
                    "Lithium extraction (Jujuy, Salta, Catamarca — 'Lithium Triangle') "
                    "is an emerging industry attracting Korean and Chinese investment. "
                    "Key roles: petroleum engineers, drilling supervisors, geologists, "
                    "hydrogeologists, and HSE officers. Monthly salary: ARS 600,000-1,500,000."
                ),
                "job_families": ["Petroleum Engineering", "Geoscience", "Mining Engineering", "HSE"],
            },
            {
                "name": "Software & Technology Services",
                "context": (
                    "Argentina exports USD 3 billion in software/IT services, mostly to "
                    "the US and Europe. Buenos Aires (Palermo 'Silicon Valley') is a top "
                    "nearshore destination. Key roles: software engineers, UX/UI designers, "
                    "data engineers, product managers, and technical support. Monthly "
                    "salary: USD 1,500-6,000 (billed internationally; paid in pesos "
                    "at official or parallel rate)."
                ),
                "job_families": ["Software Engineering", "UX Design", "Data Science", "Product Management"],
            },
            {
                "name": "Healthcare",
                "context": (
                    "Argentina has one of Latin America's strongest healthcare systems "
                    "with a large public sector and obras sociales (union-funded health). "
                    "Key roles: physicians (MN-registered), nurses, psychologists "
                    "(Argentina has the most psychologists per capita globally), "
                    "physiotherapists, and dentists. Monthly salary: ARS 500,000-2,000,000 "
                    "for physicians (varies by specialty and province)."
                ),
                "job_families": ["Medicine", "Nursing", "Psychology", "Pharmacy", "Dentistry"],
            },
        ],
        "salary_context": (
            "Argentina minimum wage (SMVM): ARS 234,000/month (June 2024). Formal-sector "
            "average: ARS 600,000-900,000/month. High inflation (220% annual rate 2023) "
            "means real wages are under severe pressure. Dollar-linked IT sector wages "
            "provide better real-wage stability."
        ),
    },

    "CO": {
        "overview": (
            "Colombia is an upper-middle-income economy (GDP USD 343 billion) with "
            "a diversified private sector. Key industries: oil and gas (Ecopetrol), "
            "coffee (Federación Nacional de Cafeteros, specialty and commercial), "
            "floriculture (Colombia is the world's second-largest cut-flower exporter), "
            "coal mining (Cerrejón, El Cerro Largo), manufacturing (food and beverages, "
            "textiles, chemicals, cement), financial services (Bancolombia, Davivienda), "
            "construction, retail, healthcare, and BPO/nearshoring. Labour force: "
            "27 million. Unemployment: 9.3%."
        ),
        "industries": [
            {
                "name": "Coffee & Agriculture",
                "context": (
                    "Colombia produces 800,000 tonnes of high-altitude Arabica coffee/year. "
                    "Smallholder cafetero families, cooperatives (Cooperativa de Caficultores), "
                    "and specialty exporters (Pergamino, La Palma y El Tucán) structure "
                    "the value chain. Floriculture in the Bogotá Sabana employs 135,000 "
                    "workers (70% women). Key roles: farm workers, florist cutters and "
                    "packers, agronomists, Q-graders. Monthly wages: COP 1,300,000-2,000,000 "
                    "for farm workers; COP 4,000,000-8,000,000 for agronomists."
                ),
                "job_families": ["Farming", "Coffee Q-grading", "Floriculture", "Agro-export"],
            },
            {
                "name": "Oil & Gas",
                "context": (
                    "Ecopetrol is Colombia's state oil company. Production: 750,000 bpd "
                    "from Llanos Basin fields (Casanare, Meta). Key roles: petroleum "
                    "engineers, production geologists, drilling supervisors, HSE officers, "
                    "and pipeline integrity specialists. Monthly salary: COP 8,000,000-25,000,000."
                ),
                "job_families": ["Petroleum Engineering", "Geology", "HSE", "Refinery Operations"],
            },
            {
                "name": "BPO & Digital Services",
                "context": (
                    "Bogotá, Medellín, and Barranquilla are leading BPO and nearshoring "
                    "hubs for US and European companies. Key roles: customer-service "
                    "representatives (bilingual), IT support analysts, data entry operators, "
                    "software developers, and digital marketers. Monthly salary: "
                    "COP 2,000,000-6,000,000."
                ),
                "job_families": ["Customer Service", "IT Support", "Software Engineering", "Digital Marketing"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Bancolombia, Davivienda, Banco de Bogotá, and BBVA Colombia are "
                    "the largest banks. The insurance sector (Sura, Bolivar) and AFP "
                    "pension funds are significant employers. Key roles: financial advisers, "
                    "credit analysts, actuaries, bank tellers, insurance agents. Monthly "
                    "salary: COP 3,000,000-12,000,000."
                ),
                "job_families": ["Banking", "Insurance", "Actuarial", "Pension Management"],
            },
        ],
        "salary_context": (
            "Colombia minimum wage (SMMLV): COP 1,300,000/month (2024). Average "
            "formal monthly wage: COP 2,800,000-4,200,000. Bogotá wages are 40-60% "
            "above national average. SENA (national training service) provides free "
            "vocational training across all industries."
        ),
    },

    "CL": {
        "overview": (
            "Chile is a high-income OECD economy (GDP per capita USD 17,000) with "
            "strong institutions and open-trade policy. Key industries: copper mining "
            "(Chile holds 28% of global reserves — Codelco, BHP Escondida, Antofagasta), "
            "lithium (SQM and Albemarle — Atacama salt flat, world's second-largest "
            "producer), salmon aquaculture (Los Lagos region, world's second-largest "
            "exporter), wine (Valle Central, Casablanca), agriculture (blueberries, "
            "cherries, avocado), financial services (BancoEstado, Banco de Chile, Santander), "
            "retail (Falabella, Cencosud), construction, and healthcare. Labour force: "
            "9.5 million. Unemployment: 8.5%."
        ),
        "industries": [
            {
                "name": "Copper & Lithium Mining",
                "context": (
                    "Codelco employs 30,000 directly; Escondida (BHP) 14,000. Key roles: "
                    "mining engineers, metallurgists, geologists, electrical engineers "
                    "(mining haul trucks and concentrators), HSE officers, and mine planning "
                    "engineers. Lithium chemical processing (Produmet, SQM) employs "
                    "electrochemists and process engineers. Monthly salary: CLP 2,500,000-"
                    "5,500,000 for engineers; CLP 1,800,000-2,800,000 for operators."
                ),
                "job_families": ["Mining Engineering", "Metallurgy", "Geology", "HSE", "Chemistry"],
            },
            {
                "name": "Salmon Aquaculture",
                "context": (
                    "Chile's salmon industry exports USD 5.5 billion/year. MOWI, Cermaq, "
                    "and AquaChile operate netpen farms in Región de Los Lagos and Aysén. "
                    "Key roles: aquaculture technicians, marine biologists, sea-cage divers, "
                    "fish health veterinarians, and cold-chain logistics staff. Monthly "
                    "salary: CLP 900,000-2,000,000 for technicians; CLP 3,000,000-5,500,000 "
                    "for marine biologists and veterinarians."
                ),
                "job_families": ["Aquaculture", "Marine Biology", "Veterinary Science", "Food Technology"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Chile's pension system (AFP) is among Latin America's most developed. "
                    "Banco Santander Chile, Banco de Chile, and BCI are major employers. "
                    "Key roles: financial analysts, AFP investment professionals, insurance "
                    "actuaries, private bankers, and compliance officers. Monthly salary: "
                    "CLP 1,800,000-5,000,000."
                ),
                "job_families": ["Banking", "Pension Management", "Insurance", "Capital Markets"],
            },
            {
                "name": "Retail & Consumer",
                "context": (
                    "Falabella (department stores, home improvement, supermarkets), "
                    "Cencosud (Jumbo, Easy), and SMU employ 200,000+ across Chile and "
                    "the wider Latin America region. Key roles: store managers, buyers, "
                    "logistics coordinators, e-commerce specialists, and customer experience "
                    "managers. Monthly salary: CLP 700,000-1,500,000 for store staff; "
                    "CLP 2,500,000-5,000,000 for buyers and managers."
                ),
                "job_families": ["Retail", "Buying", "Supply Chain", "E-commerce"],
            },
        ],
        "salary_context": (
            "Chile minimum wage: CLP 500,000/month (2024). Formal-sector average: "
            "CLP 1,200,000-1,800,000/month. Santiago wages are 30-40% above regional "
            "average. Mining industry wages are 2-3× the national average. "
            "AFP pension contribution: 10.5% employee, 0% employer (transitioning)."
        ),
    },

    "PE": {
        "overview": (
            "Peru is an upper-middle-income economy (GDP USD 243 billion) with "
            "a resource-rich export base. Key industries: mining (copper, gold, zinc, "
            "silver — Las Bambas, Antamina, Yanacocha), oil and gas, agriculture "
            "(asparagus, blueberries, coffee, cocoa, quinoa — Peru is the world's "
            "largest quinoa exporter), fishing and fish-meal processing (anchovy), "
            "tourism (Machu Picchu, Lima gastronomy), manufacturing (textiles, food), "
            "construction, financial services, and retail. Unemployment: 7.3%. "
            "Average formal monthly wage: PEN 2,000-3,500."
        ),
        "industries": [
            {
                "name": "Mining (Copper, Gold, Zinc)",
                "context": (
                    "Peru is the world's second-largest copper and zinc producer. "
                    "Las Bambas (MMG), Antamina (BHP/Glencore), and Cerro Verde (Freeport) "
                    "are large-scale operations. Key roles: mining engineers, geologists, "
                    "metallurgists, environmental specialists, and community relations officers. "
                    "Monthly salary: PEN 8,000-20,000 for engineers."
                ),
                "job_families": ["Mining Engineering", "Geology", "Metallurgy", "Environmental Management"],
            },
            {
                "name": "Agriculture & Agro-export",
                "context": (
                    "Peru exports USD 8 billion in agri-products. Asparagus (Ica), "
                    "blueberries and avocados (La Libertad), coffee (San Martín), "
                    "cocoa (Cusco), and quinoa (Altiplano) are key products. Seasonal "
                    "agricultural workers earn PEN 45-60/day. Agro-export technicians "
                    "and certifiers earn PEN 3,000-7,000/month."
                ),
                "job_families": ["Farming", "Agro-export", "Food Safety", "Organic Certification"],
            },
            {
                "name": "Tourism & Gastronomy",
                "context": (
                    "Peru's tourism (Machu Picchu, Cusco, Lima culinary circuit) generates "
                    "USD 3.5 billion. Lima is ranked among the world's top-5 dining "
                    "destinations. Key roles: tour guides (PromPerú licensed), hotel staff, "
                    "executive chefs, sous-chefs, restaurant managers. Monthly salary: "
                    "PEN 1,500-3,500 for hospitality staff; PEN 5,000-12,000 for "
                    "executive chefs at destination restaurants."
                ),
                "job_families": ["Tourism", "Hospitality", "Culinary Arts", "Event Management"],
            },
        ],
        "salary_context": (
            "Peru minimum wage (RMV): PEN 1,025/month (2022). Average formal monthly wage: "
            "PEN 2,000-3,500. Mining wages in highland regions: PEN 4,000-12,000/month. "
            "High informality (70% of workforce) keeps average wages depressed."
        ),
    },

    "PA": {
        "overview": (
            "Panama is an upper-middle-income economy (GDP per capita USD 15,000) "
            "dominated by service industries linked to the Panama Canal. Key industries: "
            "canal operations and logistics (Autoridad del Canal de Panamá), financial "
            "services and offshore banking (Panamá is the region's banking hub), "
            "tourism, construction (Cinta Costera, metro), retail (free-trade zone "
            "in Colón), and agriculture. Unemployment: 7.2%. Average monthly formal "
            "wage: USD 900-1,200. Strong demand for logistics professionals, banking "
            "officers, construction engineers, and hospitality staff."
        ),
        "industries": [
            {
                "name": "Panama Canal & Logistics",
                "context": (
                    "The Panama Canal generates USD 4.2 billion/year. ACP employs 10,000. "
                    "The Canal expansion (Neopanamax locks) demands heavy-equipment operators, "
                    "marine engineers, and logistics planners. Colón Free Zone is the largest "
                    "free-trade zone in the Americas. Key roles: maritime pilots, port "
                    "operations supervisors, logistics coordinators, and customs brokers. "
                    "Monthly salary: USD 1,500-5,000."
                ),
                "job_families": ["Maritime", "Logistics", "Customs", "Port Operations"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Panama hosts 70+ banks and is the LATAM hub for many multinationals' "
                    "treasury and shared-service operations. Key roles: bank officers, "
                    "AML/compliance specialists, financial controllers, tax advisers. "
                    "Monthly salary: USD 1,200-4,500."
                ),
                "job_families": ["Banking", "Compliance", "Corporate Finance", "Tax Advisory"],
            },
        ],
        "salary_context": (
            "Panama minimum wage: varies by occupation and region; general USD 7.68-"
            "8.65/hour (2022). Average formal monthly wage: USD 900-1,200. Canal and "
            "financial-sector workers earn significantly above the average."
        ),
    },

    "CR": {
        "overview": (
            "Costa Rica is an upper-middle-income economy (GDP per capita USD 13,000) "
            "known for biodiversity, medical devices, and ecotourism. Key industries: "
            "medical devices and pharmaceutical manufacturing (Boston Scientific, Medtronic, "
            "Baxter in Coyol Free Zone), agriculture (bananas, pineapples, coffee), "
            "tourism (eco-lodges, adventure tourism), financial and business services "
            "(American Express, Western Union shared services), construction, and ICT. "
            "Unemployment: 8.3%. Average monthly formal wage: CRC 700,000-1,000,000."
        ),
        "industries": [
            {
                "name": "Medical Devices & Life Sciences",
                "context": (
                    "Costa Rica exports USD 4 billion in medical devices — more than "
                    "tourism and coffee combined. Coyol Free Zone hosts 50+ firms. Key "
                    "roles: biomedical engineers, quality engineers, regulatory affairs "
                    "specialists, clean-room operators, and supply-chain planners. "
                    "Monthly salary: CRC 900,000-2,500,000."
                ),
                "job_families": ["Biomedical Engineering", "Quality Assurance", "Regulatory Affairs", "Manufacturing"],
            },
            {
                "name": "Ecotourism & Hospitality",
                "context": (
                    "Costa Rica pioneered ecotourism, contributing 8% of GDP. Sustainable "
                    "lodges, adventure parks (Arenal, Monteverde), and beach resorts "
                    "(Guanacaste, Manuel Antonio) are the product base. Key roles: "
                    "naturalist guides, lodge managers, surf instructors, yoga retreat "
                    "facilitators. Monthly salary: CRC 400,000-900,000."
                ),
                "job_families": ["Ecotourism", "Wildlife Guiding", "Hospitality", "Adventure Sports"],
            },
        ],
        "salary_context": (
            "Costa Rica minimum wage by occupational category: unskilled workers "
            "CRC 11,028/day; professionals CRC 23,000-30,000/day (2024). Average "
            "formal monthly wage: CRC 800,000-1,000,000. Free-zone workers earn "
            "20-50% above national average."
        ),
    },

    "TT": {
        "overview": (
            "Trinidad and Tobago is a high-income Caribbean economy (GDP per capita "
            "USD 17,000) driven by energy exports. Key industries: oil and gas "
            "(bpTT, Shell, EOG), petrochemicals (ammonia and methanol — Point Lisas "
            "industrial estate), financial services, tourism (Tobago), construction, "
            "food processing, and creative economy (Carnival, soca and steelpan music). "
            "Unemployment: 4.5%. Average monthly formal wage: TTD 7,000-10,000."
        ),
        "industries": [
            {
                "name": "Oil, Gas & Petrochemicals",
                "context": (
                    "T&T produces 70,000 bpd of oil and 2.8 billion cubic feet/day of "
                    "natural gas. Point Lisas hosts 11 ammonia plants and 5 methanol plants. "
                    "Key roles: petroleum engineers, process engineers, instrument technicians, "
                    "plant operators, and HSE officers. Monthly salary: TTD 8,000-25,000."
                ),
                "job_families": ["Petroleum Engineering", "Chemical Engineering", "Plant Operations", "HSE"],
            },
            {
                "name": "Financial Services",
                "context": (
                    "Republic Bank, First Citizens, and Scotiabank are regional financial "
                    "players. The TTSE stock exchange and insurance sector (Guardian Life, "
                    "Sagicor) provide professional employment. Key roles: financial analysts, "
                    "insurance underwriters, bank officers, and compliance managers. "
                    "Monthly salary: TTD 5,000-15,000."
                ),
                "job_families": ["Banking", "Insurance", "Capital Markets", "Compliance"],
            },
        ],
        "salary_context": (
            "Trinidad and Tobago minimum wage: TTD 20.50/hour (2024). Average "
            "monthly formal wage: TTD 8,000-12,000. Energy sector workers earn "
            "3-5× the national average. Tourism and hospitality workers in Tobago "
            "earn TTD 4,000-8,000/month."
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
        "continent": "Americas",
        "country": country_iso2,
        "region": cm.get("region", "Latin America"),
        "sub_region": cm.get("sub_region", ""),
        "market_tier": cm.get("market_tier", "emerging"),
        "currency": cm.get("currency", ""),
        "industries": [industry] if industry else [],
        "job_families": [],
        "published_at": _FETCHED_AT[:10],
        "tags": ["latam", "latin-america", cm.get("sub_region", "").lower().replace(" ", "-")],
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
        "doc_id": f"latam_overview_{country_iso2.lower()}",
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
        "doc_id": f"latam_{country_iso2.lower()}_{slug[:35]}",
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
    latam_countries = REGION_COUNTRIES.get("latam", [])
    if not latam_countries:
        print("[WARN] No LATAM countries found in REGION_COUNTRIES")
        return []

    print(f"[ILO] Fetching occupation earnings for {len(latam_countries)} LATAM countries...")
    occ_data = fetch_ilo_data(
        "EAR_4MTH_SEX_OCU_NB_A",
        latam_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    print(f"[ILO] Fetching industry earnings for {len(latam_countries)} LATAM countries...")
    ind_data = fetch_ilo_data(
        "EAR_4MTH_SEX_ECO_NB_A",
        latam_countries,
        start_year=start_year,
        use_cache=use_cache,
    )

    docs = []
    for iso2 in latam_countries:
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
    print("[LATAM] Building curated country/industry documents...")
    curated = build_curated_docs()
    print(f"[LATAM] Curated docs: {len(curated)}")

    print("[LATAM] Fetching ILO supplement...")
    ilo_docs = build_ilo_supplement(start_year=start_year, use_cache=use_cache)
    print(f"[LATAM] ILO docs: {len(ilo_docs)}")

    all_docs = curated + ilo_docs
    seen: dict[str, dict] = {}
    for doc in all_docs:
        doc_id = doc.get("doc_id", "")
        if doc_id not in seen:
            seen[doc_id] = doc
    deduped = list(seen.values())
    print(f"[LATAM] Total unique docs: {len(deduped)}")

    if dry_run:
        print("[LATAM] Dry run — not writing output file")
        return deduped

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)
    print(f"[LATAM] Written: {_OUTPUT_FILE}")
    return deduped


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch LATAM labour-market data for RAG KB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--start-year", type=int, default=2018)
    args = parser.parse_args()

    docs = build_all_docs(
        start_year=args.start_year,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )

    print(f"\n[LATAM] Done. {len(docs)} documents produced.")
    country_counts: dict[str, int] = {}
    for doc in docs:
        c = doc.get("metadata", {}).get("country", "unknown")
        country_counts[c] = country_counts.get(c, 0) + 1
    for c, n in sorted(country_counts.items()):
        print(f"  {c}: {n} docs")


if __name__ == "__main__":
    main()
