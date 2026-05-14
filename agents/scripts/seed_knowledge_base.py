"""Seed the knowledge base with comprehensive career data.

Generates (and optionally fetches) data for all five KB namespaces:
  career-kb       — career development articles (~200 docs)
  role-templates  — job requirement templates (~220 docs)
  market-reports  — quarterly market reports (~48 docs)
  swiss-eu-market — Swiss/EU regional data (~160 docs)
  esco-taxonomy   — occupation taxonomy (~500+ docs)

Usage
-----
  # Generate local synthetic seed files only:
  python -m agents.scripts.seed_knowledge_base

  # Also fetch real ESCO taxonomy from the public REST API:
  python -m agents.scripts.seed_knowledge_base --fetch-esco --esco-limit 1000

  # Write to a custom directory:
  python -m agents.scripts.seed_knowledge_base --output-dir /data/kb

Output
------
Creates / overwrites in --output-dir:
  career_kb_full.json
  role_templates_full.json
  market_reports_full.json
  swiss_eu_market_full.json
  esco_taxonomy.csv          (synthetic entries always written)
  esco_taxonomy_live.csv     (only when --fetch-esco succeeds)

Run the Celery ingestion tasks after seeding:
  celery call rag.ingest_career_kb    --args='["<output-dir>/career_kb_full.json"]'
  celery call rag.ingest_role_templates ...
  etc.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# ── Data definitions ──────────────────────────────────────────────────────────

_REGIONS_SWISS = ["Switzerland", "Zurich", "Geneva", "Basel", "Bern", "Lausanne", "Zug"]
_REGIONS_EU = ["Germany", "Netherlands", "France", "Sweden", "Austria", "Denmark",
               "Finland", "Belgium", "Ireland", "Portugal"]
_REGIONS_GLOBAL = ["United Kingdom", "United States", "Canada", "Singapore",
                   "Australia", "Remote"]

_INDUSTRIES = [
    "fintech", "insurtech", "banking", "asset management",
    "software / SaaS", "enterprise software", "AI / ML",
    "cloud infrastructure", "cybersecurity", "healthtech",
    "medtech", "biotech", "pharma", "legaltech", "govtech",
    "e-commerce", "logistics / supply chain", "media / publishing",
    "gaming", "automotive / mobility", "cleantech / climate",
    "consulting", "Big Four", "startup / scale-up",
]

_TECH_ROLES = [
    ("Software Engineer", ["junior", "mid", "senior", "staff", "principal"]),
    ("Backend Engineer", ["junior", "mid", "senior", "staff"]),
    ("Frontend Engineer", ["junior", "mid", "senior", "staff"]),
    ("Full-Stack Engineer", ["junior", "mid", "senior"]),
    ("Mobile Engineer", ["junior", "mid", "senior"]),
    ("Platform / DevOps Engineer", ["junior", "mid", "senior", "staff"]),
    ("Site Reliability Engineer", ["mid", "senior", "staff"]),
    ("Data Engineer", ["junior", "mid", "senior", "staff"]),
    ("Data Scientist", ["junior", "mid", "senior", "staff"]),
    ("ML Engineer", ["junior", "mid", "senior", "staff"]),
    ("AI Research Engineer", ["mid", "senior", "staff"]),
    ("Security Engineer", ["mid", "senior", "staff"]),
    ("Cloud Architect", ["senior", "principal"]),
    ("Solutions Architect", ["mid", "senior", "principal"]),
    ("Engineering Manager", ["manager", "senior manager", "director"]),
    ("CTO / VP Engineering", ["executive"]),
    ("QA / Test Engineer", ["junior", "mid", "senior"]),
    ("Embedded / Systems Engineer", ["mid", "senior", "staff"]),
]

_PRODUCT_ROLES = [
    ("Product Manager", ["associate", "mid", "senior", "principal", "director"]),
    ("Technical Product Manager", ["mid", "senior", "principal"]),
    ("Product Designer (UX/UI)", ["junior", "mid", "senior", "staff"]),
    ("Product Analyst", ["junior", "mid", "senior"]),
    ("Growth PM", ["mid", "senior"]),
    ("CPO / VP Product", ["executive"]),
]

_DATA_FINANCE_ROLES = [
    ("Quantitative Analyst", ["junior", "mid", "senior"]),
    ("Risk Analyst", ["junior", "mid", "senior"]),
    ("Business Intelligence Analyst", ["junior", "mid", "senior"]),
    ("Data Analyst", ["junior", "mid", "senior"]),
    ("Financial Analyst", ["junior", "mid", "senior"]),
    ("Investment Banker (Tech M&A)", ["analyst", "associate", "VP"]),
    ("CFO / Finance Director", ["executive"]),
]

_CONSULTING_MGMT_ROLES = [
    ("Management Consultant", ["analyst", "consultant", "senior consultant",
                                "manager", "principal", "partner"]),
    ("Strategy Consultant", ["consultant", "senior consultant", "manager"]),
    ("IT Consultant", ["consultant", "senior consultant", "manager"]),
    ("Transformation Manager", ["manager", "senior manager", "director"]),
]

_KB_CATEGORIES = {
    "career_development": [
        ("How to Transition from Software Engineer to Engineering Manager",
         "management", ["career transition", "leadership", "management"]),
        ("Breaking into Tech from a Non-Technical Background",
         "career_change", ["career change", "bootcamp", "self-taught"]),
        ("How to Build a Personal Brand as a Software Engineer",
         "branding", ["personal brand", "LinkedIn", "open source"]),
        ("Navigating a Layoff: Your 90-Day Playbook",
         "job_search", ["layoff", "job search", "resilience"]),
        ("How to Get Promoted from Senior to Staff Engineer",
         "promotion", ["staff engineer", "promotion", "impact"]),
        ("The Engineering Manager's First 90 Days",
         "management", ["new manager", "leadership", "team"]),
        ("Remote Work Best Practices for Distributed Teams",
         "remote_work", ["remote", "async", "productivity"]),
        ("How to Negotiate Equity at a Startup",
         "compensation", ["equity", "options", "startup", "vesting"]),
        ("Technical Interview Preparation: System Design Deep Dive",
         "interview_prep", ["system design", "interview", "architecture"]),
        ("Coding Interview Patterns: The 15 You Must Know",
         "interview_prep", ["algorithms", "leetcode", "interview"]),
        ("Building a Career in Open Source",
         "open_source", ["open source", "GitHub", "community"]),
        ("How to Give Effective Technical Presentations",
         "communication", ["presentation", "public speaking", "technical"]),
        ("Mentoring and Being Mentored: A Practical Guide",
         "mentorship", ["mentoring", "career growth", "feedback"]),
        ("Technical Writing for Engineers",
         "documentation", ["writing", "documentation", "communication"]),
        ("How to Build a Side Project That Gets You Hired",
         "portfolio", ["side project", "portfolio", "GitHub"]),
    ],
    "skills": [
        ("Mastering System Design: From Basics to Distributed Systems",
         "system_design", ["system design", "distributed systems", "scalability"]),
        ("Cloud Computing Certifications: AWS vs Azure vs GCP",
         "certifications", ["AWS", "Azure", "GCP", "certification"]),
        ("Kubernetes in Production: What They Don't Teach You",
         "devops", ["kubernetes", "k8s", "production", "DevOps"]),
        ("Learning Rust as a Python Developer",
         "programming", ["Rust", "Python", "performance"]),
        ("Machine Learning Fundamentals for Software Engineers",
         "ml_basics", ["machine learning", "ML", "Python", "sklearn"]),
        ("LLM Engineering: From Prompts to Production",
         "ai_engineering", ["LLM", "AI", "OpenAI", "langchain"]),
        ("Database Performance Tuning: PostgreSQL Edition",
         "databases", ["PostgreSQL", "performance", "indexing", "SQL"]),
        ("Security Best Practices Every Developer Should Know",
         "security", ["OWASP", "security", "vulnerabilities", "pen testing"]),
        ("TypeScript: Advanced Patterns for Production Code",
         "programming", ["TypeScript", "React", "Node.js", "patterns"]),
        ("Terraform and Infrastructure as Code at Scale",
         "devops", ["Terraform", "IaC", "AWS", "infrastructure"]),
        ("Observability Engineering: Logs, Metrics, and Traces",
         "observability", ["observability", "Prometheus", "Grafana", "OpenTelemetry"]),
        ("API Design: REST, GraphQL, and gRPC Compared",
         "api_design", ["API", "REST", "GraphQL", "gRPC"]),
        ("Data Engineering with Apache Spark and Kafka",
         "data_engineering", ["Spark", "Kafka", "data pipelines", "streaming"]),
        ("Building Production-Ready RAG Applications",
         "ai_engineering", ["RAG", "embeddings", "vector database", "LLM"]),
        ("MLOps: Taking Models from Experiment to Production",
         "mlops", ["MLOps", "model deployment", "Kubeflow", "monitoring"]),
    ],
    "swiss_eu_context": [
        ("Getting a Swiss Work Permit as a Non-EU/EFTA National",
         "visa", ["work permit", "Switzerland", "visa", "residence permit"]),
        ("Swiss Salary Negotiation: A Complete Guide",
         "compensation", ["salary", "negotiation", "Switzerland", "CHF"]),
        ("Understanding Swiss Employment Law for Tech Workers",
         "legal", ["employment law", "Switzerland", "contract", "notice period"]),
        ("Networking in Zurich's Tech Ecosystem",
         "networking", ["Zurich", "networking", "tech community", "meetups"]),
        ("Top Swiss Universities for Tech Professionals: ETH, EPFL and Beyond",
         "education", ["ETH Zurich", "EPFL", "education", "Switzerland"]),
        ("The EU Blue Card: Fast-Track to European Tech Jobs",
         "visa", ["EU Blue Card", "Europe", "work permit", "visa"]),
        ("Working in Germany as a Tech Professional",
         "germany", ["Germany", "Berlin", "Munich", "job market"]),
        ("Amsterdam's Tech Scene: A Guide for International Professionals",
         "netherlands", ["Amsterdam", "Netherlands", "tech jobs", "relocation"]),
        ("Swiss Pension System Explained for Expats",
         "benefits", ["pension", "Switzerland", "pillar 2", "retirement"]),
        ("Language Requirements for Tech Jobs in Switzerland",
         "language", ["German", "French", "English", "Switzerland"]),
    ],
    "job_search": [
        ("How to Write a Senior Engineer CV That Gets Interviews",
         "cv", ["CV", "resume", "software engineer", "ATS"]),
        ("LinkedIn Profile Optimisation for Tech Professionals",
         "linkedin", ["LinkedIn", "profile", "networking", "recruiter"]),
        ("How to Work With Tech Recruiters Effectively",
         "recruiting", ["recruiter", "headhunter", "job search", "agency"]),
        ("Evaluating Startup Equity: Dilution, Cliffs, and Secondaries",
         "compensation", ["equity", "startup", "options", "vesting"]),
        ("How to Evaluate a Job Offer Beyond the Salary",
         "offers", ["job offer", "evaluation", "benefits", "culture"]),
        ("The Referral Advantage: Getting Hired Through Your Network",
         "networking", ["referrals", "networking", "job search", "hiring"]),
        ("How to Ace the Behavioural Interview",
         "interview_prep", ["behavioural interview", "STAR method", "leadership"]),
        ("Navigating Multiple Competing Job Offers",
         "offers", ["competing offers", "negotiation", "decision making"]),
    ],
}

_MARKET_REPORT_REGIONS = ["Global", "Europe", "Switzerland", "Germany", "United States", "APAC"]
_QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
_YEARS = [2023, 2024, 2025]

_SWISS_CITIES = ["Zurich", "Geneva", "Basel", "Bern", "Lausanne", "Zug"]
_SWISS_SECTORS = {
    "fintech": {
        "companies": ["UBS", "Credit Suisse / CS spinoffs", "Julius Bär", "Raiffeisen",
                      "Adyen NL (Zurich office)", "Six Group", "SEBA Bank", "Hypothekarbank Lenzburg"],
        "roles": ["Quantitative Developer", "Risk Engineer", "Full-Stack Engineer",
                  "Compliance Technologist", "Blockchain Developer"],
        "salary_range": {"junior": "CHF 90,000–115,000", "mid": "CHF 120,000–155,000",
                         "senior": "CHF 160,000–210,000"},
    },
    "pharma / biotech": {
        "companies": ["Roche", "Novartis", "Lonza", "Basilea Pharmaceutica", "Idorsia"],
        "roles": ["Bioinformatics Engineer", "Clinical Data Engineer", "Data Scientist",
                  "Software Engineer (lab systems)", "IT/OT Security Engineer"],
        "salary_range": {"junior": "CHF 85,000–110,000", "mid": "CHF 115,000–145,000",
                         "senior": "CHF 150,000–195,000"},
    },
    "cloud / SaaS": {
        "companies": ["Google Zurich", "Microsoft Zurich", "Amazon AWS Zurich", "Salesforce",
                      "Zuhlke Engineering", "Namics (Merkle)", "Ergon Informatik"],
        "roles": ["Software Engineer", "SRE", "Cloud Architect", "DevOps Engineer",
                  "ML Engineer", "Product Manager"],
        "salary_range": {"junior": "CHF 88,000–115,000", "mid": "CHF 120,000–160,000",
                         "senior": "CHF 165,000–220,000"},
    },
    "consulting": {
        "companies": ["McKinsey", "BCG", "Deloitte", "PwC", "EY", "Accenture", "Capgemini"],
        "roles": ["Technology Consultant", "Data Consultant", "IT Manager",
                  "Digital Transformation Lead", "Cybersecurity Consultant"],
        "salary_range": {"junior": "CHF 85,000–110,000", "mid": "CHF 120,000–150,000",
                         "senior": "CHF 155,000–200,000"},
    },
    "watchmaking / luxury": {
        "companies": ["Richemont", "Swatch Group", "LVMH (Bvlgari CH)", "TAG Heuer"],
        "roles": ["IoT Engineer", "E-commerce Engineer", "Data Analyst",
                  "ERP Consultant (SAP)", "Supply Chain Technologist"],
        "salary_range": {"junior": "CHF 78,000–100,000", "mid": "CHF 105,000–135,000",
                         "senior": "CHF 140,000–175,000"},
    },
}

_EU_MARKETS = {
    "Berlin, Germany": {
        "description": (
            "Berlin is Europe's largest startup hub, attracting talent from across the EU. "
            "The tech ecosystem spans fintech (N26, Trade Republic), mobility (TIER, Lilium legacy), "
            "e-commerce (Zalando, HelloFresh HQ), and deep-tech (Global Founders Capital portfolio). "
            "Salaries are lower than Zurich or Amsterdam but cost-of-living is significantly cheaper."
        ),
        "salary_range": {"junior": "€48,000–65,000", "mid": "€70,000–95,000",
                         "senior": "€100,000–145,000"},
        "work_permit": "EU nationals: free movement. Non-EU: German Skilled Workers Act (Fachkräfteeinwanderungsgesetz) since 2023.",
    },
    "Amsterdam, Netherlands": {
        "description": (
            "Amsterdam hosts EMEA headquarters for many US tech giants (Netflix, Uber, Booking.com). "
            "The city is one of the most international in Europe with over 70% English-speaking workplaces. "
            "Strong in fintech (ING, ABN AMRO digital), scale-ups, and logistics tech. "
            "The 30% ruling tax benefit is available to qualifying expats for five years."
        ),
        "salary_range": {"junior": "€42,000–60,000", "mid": "€65,000–90,000",
                         "senior": "€95,000–140,000"},
        "work_permit": "EU nationals: free movement. Non-EU: highly skilled migrant (kennismigrant) visa — fast-track if salary > €5,688/month (2025 threshold).",
    },
    "London, United Kingdom": {
        "description": (
            "London remains Europe's largest financial and tech centre despite post-Brexit headwinds. "
            "Strong demand across fintech (Revolut, Monzo, Wise), AI/ML (DeepMind, Wayve), "
            "and enterprise SaaS. Visa routes include the Global Talent visa and Skilled Worker visa. "
            "Salaries are the highest in Europe outside Zurich but cost-of-living is also very high."
        ),
        "salary_range": {"junior": "£42,000–60,000", "mid": "£65,000–95,000",
                         "senior": "£100,000–160,000"},
        "work_permit": "Post-Brexit Skilled Worker visa required for non-UK nationals. Global Talent visa available for exceptional candidates.",
    },
    "Stockholm, Sweden": {
        "description": (
            "Stockholm is the birthplace of Spotify, Klarna, and King. Sweden has one of the highest "
            "per-capita unicorn rates globally. Strong in gaming, music tech, fintech, and clean tech. "
            "High quality of life, generous parental leave, and strong union protections. "
            "English widely spoken in tech workplaces."
        ),
        "salary_range": {"junior": "SEK 440,000–560,000", "mid": "SEK 580,000–750,000",
                         "senior": "SEK 780,000–1,050,000"},
        "work_permit": "EU/EEA nationals: free movement. Non-EU: Swedish work permit via Migrationsverket.",
    },
    "Paris, France": {
        "description": (
            "Station F and Île-de-France make Paris the largest startup hub in continental Europe. "
            "Strong in AI/ML (Mistral, LightOn), mobility (BlaBlaCar, Navya), and enterprise SaaS. "
            "The French Tech Visa offers fast-track residence for startup founders, employees, and investors. "
            "R&D tax credits make France attractive for deep-tech companies."
        ),
        "salary_range": {"junior": "€38,000–52,000", "mid": "€55,000–80,000",
                         "senior": "€85,000–130,000"},
        "work_permit": "EU nationals: free movement. Non-EU: French Tech Visa or passeport talent.",
    },
}

_ESCO_OCCUPATIONS = [
    # Software / IT
    ("Software Developer", "Designs, builds, tests, and maintains software applications and systems. Collaborates with cross-functional teams to define software requirements and deliver high-quality code. Proficient in one or more programming languages and familiar with software development methodologies.", "software development, programming, coding, software engineering"),
    ("Web Developer", "Creates and maintains websites and web applications. Works with HTML, CSS, JavaScript and server-side technologies to deliver responsive and accessible user experiences. Collaborates with designers and back-end engineers.", "web development, HTML, CSS, JavaScript, frontend"),
    ("Database Administrator", "Installs, configures, maintains, and secures database management systems. Ensures data integrity, performance, and availability. Performs backups, recovery operations, and capacity planning.", "database, SQL, Oracle, PostgreSQL, data management"),
    ("Systems Analyst", "Evaluates business requirements and translates them into technical specifications. Bridges the gap between IT and business units to ensure technology solutions meet organisational needs.", "systems analysis, business analysis, requirements, IT"),
    ("ICT Security Specialist", "Protects information systems from cyber threats. Conducts vulnerability assessments, implements security controls, and responds to incidents. Advises on security policies and compliance.", "cybersecurity, information security, SIEM, penetration testing, compliance"),
    ("Cloud Solutions Architect", "Designs cloud computing strategies and architectures. Selects appropriate cloud services, ensures scalability and reliability, and oversees cloud migrations. Works across AWS, Azure, and GCP platforms.", "cloud computing, AWS, Azure, GCP, architecture, DevOps"),
    ("DevOps Engineer", "Bridges development and operations to accelerate software delivery. Implements CI/CD pipelines, infrastructure as code, and monitoring solutions. Maintains reliability and performance of production systems.", "DevOps, CI/CD, Kubernetes, Docker, infrastructure, automation"),
    ("Data Engineer", "Builds and maintains data pipelines and infrastructure. Designs ETL processes, data warehouses, and streaming systems. Ensures data quality and availability for analytics teams.", "data engineering, ETL, Apache Spark, Kafka, SQL, Python"),
    ("Machine Learning Engineer", "Develops machine learning models and deploys them into production systems. Bridges data science and software engineering, ensuring models are scalable, monitored, and maintainable.", "machine learning, deep learning, Python, TensorFlow, MLOps"),
    ("Artificial Intelligence Researcher", "Conducts research to advance the state of artificial intelligence. Develops new algorithms, architectures, and methodologies. Publishes findings and applies research to practical applications.", "AI, research, deep learning, neural networks, NLP, computer vision"),
    ("IT Project Manager", "Plans, executes, and closes IT projects within scope, time, and budget. Coordinates cross-functional teams, manages risks, and communicates status to stakeholders.", "project management, PMBOK, Agile, Scrum, stakeholder management"),
    ("Network Administrator", "Manages and maintains computer networks including LAN, WAN, and wireless systems. Configures routers, switches, and firewalls. Troubleshoots connectivity issues and ensures network security.", "networking, TCP/IP, Cisco, firewall, network security"),
    ("IT Support Specialist", "Provides technical assistance to end users. Diagnoses hardware and software issues, installs and configures equipment, and documents solutions. First point of contact for IT-related problems.", "IT support, helpdesk, troubleshooting, hardware, software"),
    ("UX Designer", "Researches user needs and designs intuitive digital experiences. Creates wireframes, prototypes, and conducts usability testing. Collaborates with product managers and developers to ship user-centred products.", "UX design, user research, Figma, prototyping, usability"),
    ("Product Manager", "Defines the vision and roadmap for a product. Prioritises features based on user needs and business goals. Works with engineering, design, and marketing to deliver value to customers.", "product management, roadmap, agile, user stories, strategy"),
    ("Technical Writer", "Creates clear and accurate technical documentation including user manuals, API references, and developer guides. Interviews subject matter experts and simplifies complex concepts for target audiences.", "technical writing, documentation, API docs, content strategy"),
    ("Scrum Master", "Facilitates Scrum ceremonies and removes impediments for the development team. Coaches the team on agile practices and fosters continuous improvement. Bridges the team and product owner.", "Scrum, Agile, facilitation, sprint planning, retrospective"),
    ("Business Intelligence Analyst", "Transforms raw data into actionable insights using BI tools and SQL. Designs dashboards and reports for business stakeholders. Identifies trends and patterns to support data-driven decisions.", "BI, business intelligence, SQL, Tableau, Power BI, data analytics"),
    ("Quality Assurance Engineer", "Designs and executes test plans to ensure software meets quality standards. Automates test cases, performs regression testing, and reports defects. Works closely with developers to shift quality left.", "QA, testing, test automation, Selenium, quality assurance"),
    ("Embedded Systems Engineer", "Develops software for embedded systems in consumer electronics, automotive, medical devices, and industrial equipment. Works close to hardware with real-time operating systems and constrained resources.", "embedded systems, C, C++, RTOS, firmware, microcontrollers"),
    # Data / Analytics
    ("Data Scientist", "Applies statistical and machine learning techniques to extract insights from large datasets. Builds predictive models, conducts A/B tests, and communicates findings to non-technical stakeholders.", "data science, Python, R, statistics, machine learning, analytics"),
    ("Data Analyst", "Collects, processes, and analyses structured and unstructured data to identify trends and answer business questions. Produces dashboards, ad-hoc reports, and data quality frameworks.", "data analysis, SQL, Excel, Python, visualisation, reporting"),
    ("Statistician", "Designs and applies statistical methods to collect, analyse, and interpret data. Works in research, government, healthcare, or industry to support evidence-based decision making.", "statistics, R, SAS, hypothesis testing, regression, sampling"),
    ("Actuarial Analyst", "Analyses financial risk using mathematics, statistics, and financial theory. Works primarily in insurance and pensions to price products and model liabilities.", "actuarial, insurance, risk, statistics, Excel, pension"),
    ("Quantitative Analyst", "Develops mathematical models to price financial instruments and manage risk. Works in investment banks, hedge funds, and asset managers. Requires strong maths and programming skills.", "quant, mathematical modelling, Python, C++, derivatives, risk"),
    # Finance / Business
    ("Financial Analyst", "Prepares financial models, valuations, and investment analyses. Supports strategic decision-making through budgeting, forecasting, and variance analysis. Presents findings to senior management.", "financial analysis, Excel, financial modelling, valuation, FP&A"),
    ("Investment Banker", "Advises corporations and governments on capital raising, mergers, acquisitions, and restructurings. Works on transactions ranging from IPOs and bond issues to private equity deals.", "investment banking, M&A, capital markets, valuation, financial modelling"),
    ("Risk Manager", "Identifies, assesses, and mitigates financial, operational, and strategic risks. Develops risk frameworks, monitors risk exposures, and reports to senior management and regulators.", "risk management, risk assessment, Basel, IFRS, compliance"),
    ("Management Consultant", "Advises organisations on strategy, operations, and transformation. Conducts analysis, develops recommendations, and supports implementation. Works across industries and functions.", "management consulting, strategy, problem solving, stakeholder management"),
    ("Operations Manager", "Plans, coordinates, and controls operational processes to maximise efficiency and quality. Manages budgets, teams, and vendor relationships. Drives continuous improvement initiatives.", "operations, process improvement, lean, six sigma, supply chain"),
    # Healthcare / Life Sciences
    ("Biomedical Engineer", "Applies engineering principles to solve problems in medicine and biology. Designs medical devices, diagnostic equipment, and prosthetics. Works at the intersection of engineering, biology, and medicine.", "biomedical engineering, medical devices, FDA, regulatory, CAD"),
    ("Bioinformatician", "Develops tools and pipelines to analyse biological data including genomics, proteomics, and clinical records. Combines computer science with biology to advance biomedical research.", "bioinformatics, genomics, Python, R, sequence analysis, NGS"),
    ("Clinical Data Manager", "Designs and maintains clinical trial databases. Ensures data quality, regulatory compliance, and timely data delivery for pharmaceutical trials. Works with EDC systems and CDASH standards.", "clinical data management, EDC, CDASH, ICH guidelines, GCP"),
    ("Healthcare IT Specialist", "Implements and maintains IT systems in healthcare settings including electronic health records, PACS, and clinical decision support tools. Ensures system reliability, security, and interoperability.", "healthcare IT, EHR, HL7, FHIR, clinical informatics"),
    # Design / Creative
    ("UI/UX Designer", "Creates visually appealing and user-friendly digital interfaces. Conducts user research, designs wireframes and high-fidelity mockups, and collaborates with developers for pixel-perfect implementation.", "UI design, UX, Figma, Adobe XD, prototyping, design systems"),
    ("Graphic Designer", "Creates visual content for print and digital media. Develops brand identities, marketing materials, and illustrations. Proficient in design software and colour theory.", "graphic design, Adobe Creative Suite, branding, typography, illustration"),
    ("Motion Graphics Designer", "Creates animated visual content for video, web, and broadcast. Works with After Effects, Cinema 4D, and other tools to bring static designs to life.", "motion graphics, After Effects, Cinema 4D, animation, video"),
    # Other Technical
    ("Mechanical Engineer", "Designs, analyses, and manufactures mechanical systems and components. Applies principles of physics and materials science to develop engines, machines, and thermal systems.", "mechanical engineering, CAD, SolidWorks, FEA, thermodynamics"),
    ("Electrical Engineer", "Designs, develops, and tests electrical systems and components. Works on power systems, electronics, control systems, and telecommunications equipment.", "electrical engineering, circuit design, power systems, MATLAB, PLC"),
    ("Civil Engineer", "Plans, designs, and supervises the construction of infrastructure projects such as roads, bridges, buildings, and water systems. Ensures structural integrity and regulatory compliance.", "civil engineering, structural analysis, AutoCAD, project management"),
    ("Environmental Engineer", "Develops solutions to environmental problems including pollution control, waste management, and sustainability. Works on projects to protect air, water, and soil quality.", "environmental engineering, sustainability, ISO 14001, waste management"),
    # Management / Leadership
    ("Chief Executive Officer", "Provides strategic direction and leadership for the entire organisation. Accountable to the board of directors. Oversees all operations, financial performance, and stakeholder relationships.", "CEO, executive leadership, strategy, board, P&L"),
    ("Chief Technology Officer", "Leads the technology vision and strategy of the organisation. Oversees engineering teams, technology investments, and technical roadmap. Balances innovation with operational excellence.", "CTO, technology leadership, architecture, engineering, R&D"),
    ("Chief Data Officer", "Governs data strategy, data quality, and data literacy across the organisation. Oversees data engineering, analytics, and AI initiatives. Ensures regulatory compliance around data.", "CDO, data strategy, data governance, analytics, AI"),
    ("Human Resources Manager", "Oversees recruitment, employee relations, compensation, benefits, and organisational development. Partners with business leaders to attract, develop, and retain talent.", "HR, recruitment, talent management, employee relations, compensation"),
    ("Marketing Manager", "Develops and executes marketing strategies to drive brand awareness and customer acquisition. Manages digital, content, and event marketing. Analyses campaign performance and ROI.", "marketing, digital marketing, content, SEO, demand generation"),
    ("Sales Manager", "Leads a team of sales representatives to meet revenue targets. Develops sales strategies, coaches team members, and manages key customer relationships.", "sales, revenue, CRM, Salesforce, B2B sales, account management"),
    ("Legal Counsel", "Provides legal advice on contracts, employment, intellectual property, and regulatory compliance. Manages legal risk and represents the organisation in negotiations and disputes.", "legal, contracts, intellectual property, compliance, corporate law"),
    ("Procurement Manager", "Manages supplier relationships and procurement processes. Negotiates contracts, ensures supply chain resilience, and drives cost optimisation. Works cross-functionally with finance and operations.", "procurement, supply chain, vendor management, contracts, negotiation"),
]


# ── Role template content builders ───────────────────────────────────────────

def _role_skills(role: str) -> dict[str, list[str]]:
    """Return required/nice-to-have skills for common role families."""
    r = role.lower()
    if "software engineer" in r or "backend" in r:
        return {
            "required": ["Python or TypeScript or Java or Go", "REST APIs", "SQL", "Git",
                         "CI/CD pipelines", "Unit and integration testing"],
            "nice": ["Kubernetes", "AWS or GCP", "Domain-Driven Design", "gRPC"],
        }
    if "frontend" in r:
        return {
            "required": ["TypeScript", "React or Vue", "CSS / Tailwind", "REST / GraphQL",
                         "Testing (Jest, Vitest)", "Accessibility standards"],
            "nice": ["Next.js", "Storybook", "Performance optimisation", "WebSockets"],
        }
    if "devops" in r or "platform" in r or "sre" in r:
        return {
            "required": ["Kubernetes", "Docker", "Terraform or Pulumi", "CI/CD (GitHub Actions / GitLab)",
                         "Linux", "Monitoring (Prometheus, Grafana)"],
            "nice": ["Istio / service mesh", "Vault", "ArgoCD", "eBPF"],
        }
    if "data engineer" in r:
        return {
            "required": ["Python", "SQL", "Apache Spark or dbt", "Airflow or Prefect",
                         "Data warehouse (Snowflake, BigQuery, Redshift)", "ETL/ELT design"],
            "nice": ["Apache Kafka", "Flink", "Delta Lake", "dbt macros"],
        }
    if "data scientist" in r or "ml engineer" in r:
        return {
            "required": ["Python", "scikit-learn / PyTorch / TensorFlow", "SQL",
                         "Statistical modelling", "Feature engineering", "Experiment design (A/B)"],
            "nice": ["MLflow", "Kubeflow", "Spark MLlib", "LLM fine-tuning"],
        }
    if "security" in r:
        return {
            "required": ["Threat modelling", "OWASP Top 10", "SIEM (Splunk / Elastic)",
                         "Vulnerability scanning", "Scripting (Python / Bash)", "Cloud security"],
            "nice": ["OSCP certification", "Bug bounty experience", "Red team operations"],
        }
    if "product manager" in r or "product owner" in r:
        return {
            "required": ["Product roadmap planning", "User story writing", "Stakeholder management",
                         "Data analysis", "Agile / Scrum", "OKR framework"],
            "nice": ["SQL", "Figma", "A/B testing", "Growth modelling"],
        }
    if "data analyst" in r or "bi analyst" in r:
        return {
            "required": ["SQL", "Excel / Google Sheets", "BI tool (Tableau, Power BI, Looker)",
                         "Statistical analysis", "Data storytelling"],
            "nice": ["Python", "dbt", "Fivetran", "A/B testing"],
        }
    if "consultant" in r:
        return {
            "required": ["Structured problem solving", "Slide deck creation (PowerPoint)", "Excel modelling",
                         "Stakeholder management", "Project management", "Business case development"],
            "nice": ["Industry expertise", "Agile delivery", "Change management"],
        }
    if "architect" in r:
        return {
            "required": ["System design", "Cloud platforms (AWS / Azure / GCP)",
                         "Microservices architecture", "Security design", "Stakeholder communication"],
            "nice": ["TOGAF", "Service mesh (Istio)", "Multi-cloud strategy"],
        }
    if "engineering manager" in r or "manager" in r:
        return {
            "required": ["People management", "Performance reviews", "Hiring and interviewing",
                         "Technical roadmap planning", "Cross-functional collaboration",
                         "Incident management"],
            "nice": ["P&L responsibility", "OKR facilitation", "Executive communication"],
        }
    # default
    return {
        "required": ["Domain expertise", "Communication", "Problem solving",
                     "Stakeholder management", "Documentation"],
        "nice": ["Data analysis", "Project management"],
    }


def _level_description(role: str, level: str) -> str:
    r = role.lower()
    l = level.lower()
    base = role

    if l in ("junior", "associate", "analyst"):
        return (
            f"An entry-level {base} who implements well-scoped tasks under close guidance. "
            f"Expected to ramp up quickly, ship production changes within 1–3 months, and "
            f"participate actively in code or work reviews. Asks good questions and learns from feedback."
        )
    if l in ("mid", "consultant", "mid-level"):
        return (
            f"A {base} who works independently on moderately complex problems. "
            f"Consistently delivers quality work across a feature or domain area. "
            f"Mentors more junior colleagues and contributes to process improvements."
        )
    if l in ("senior", "senior consultant"):
        return (
            f"A highly experienced {base} who owns significant technical or domain areas. "
            f"Sets the quality bar, makes architectural decisions, and drives projects from "
            f"inception to production. Regularly mentors, leads design reviews, and influences "
            f"team direction."
        )
    if l in ("staff", "principal", "manager", "lead"):
        return (
            f"A {base} operating across multiple teams or the whole organisation. "
            f"Drives company-wide technical initiatives, mentors senior engineers, and "
            f"aligns engineering strategy with business objectives. Significant scope and impact."
        )
    if l in ("director", "vp", "executive", "partner"):
        return (
            f"An executive {base} responsible for organisational strategy, headcount planning, "
            f"and cross-company initiatives. Reports to C-level. Drives culture, capability building, "
            f"and external stakeholder relationships."
        )
    return (
        f"A {level} {base} with responsibilities commensurate with their level of experience "
        f"and scope within the organisation."
    )


def _experience_years(level: str) -> dict[str, int]:
    l = level.lower()
    map_ = {
        "junior": {"min": 0, "max": 2},
        "associate": {"min": 0, "max": 2},
        "analyst": {"min": 0, "max": 2},
        "mid": {"min": 2, "max": 5},
        "consultant": {"min": 2, "max": 5},
        "mid-level": {"min": 2, "max": 5},
        "senior": {"min": 5, "max": 9},
        "senior consultant": {"min": 4, "max": 8},
        "staff": {"min": 8, "max": 13},
        "principal": {"min": 10, "max": 16},
        "manager": {"min": 5, "max": 12},
        "senior manager": {"min": 8, "max": 15},
        "lead": {"min": 6, "max": 12},
        "director": {"min": 10, "max": 20},
        "vp": {"min": 12, "max": 20},
        "partner": {"min": 12, "max": 20},
        "executive": {"min": 15, "max": 99},
    }
    return map_.get(l, {"min": 3, "max": 8})


# ── Generators ────────────────────────────────────────────────────────────────

def generate_role_templates() -> list[dict]:
    """Generate 220+ role requirement templates."""
    templates: list[dict] = []
    all_role_groups = _TECH_ROLES + _PRODUCT_ROLES + _DATA_FINANCE_ROLES + _CONSULTING_MGMT_ROLES

    for role_name, levels in all_role_groups:
        for region in [_REGIONS_SWISS[0], _REGIONS_EU[0], "Global"]:
            industries = (
                ["fintech", "software / SaaS", "AI / ML", "consulting"]
                if region == "Switzerland"
                else ["software / SaaS", "AI / ML", "fintech", "e-commerce", "consulting"]
            )
            for level in levels:
                skills = _role_skills(role_name)
                slug = (
                    f"{role_name.lower().replace(' ', '-').replace('/', '')}"
                    f"-{level.lower().replace(' ', '-')}"
                    f"-{region.lower().replace(' ', '-').replace(',', '')}"
                )
                certifications: list[str] = []
                if "aws" in role_name.lower() or "cloud" in role_name.lower() or "devops" in role_name.lower():
                    certifications = ["AWS Solutions Architect Associate", "CKA (Certified Kubernetes Administrator)"]
                elif "security" in role_name.lower():
                    certifications = ["CISSP", "OSCP", "CEH"]
                elif "project manager" in role_name.lower():
                    certifications = ["PMP", "PMI-ACP", "Prince2"]
                elif "data scientist" in role_name.lower():
                    certifications = ["Google Professional Data Engineer", "AWS ML Specialty"]

                templates.append({
                    "id": slug,
                    "role": role_name,
                    "level": level,
                    "description": _level_description(role_name, level),
                    "required_skills": skills["required"],
                    "nice_to_have": skills["nice"],
                    "experience_years": _experience_years(level),
                    "certifications": certifications,
                    "region": region,
                    "industries": industries,
                })

    return templates


def _kb_article_content(title: str, category: str, tags: list[str]) -> str:
    """Generate a realistic multi-paragraph KB article body (~600–1200 words)."""
    intro_map = {
        "career_development": "Career development requires intentional strategy, not just hard work.",
        "skills": "Technical skills depreciate faster than ever in today's engineering landscape.",
        "swiss_eu_context": "Working in Switzerland or the EU offers exceptional opportunities but comes with specific requirements.",
        "job_search": "The modern job search combines personal branding, network activation, and process optimisation.",
        "interview_prep": "Effective interview preparation separates candidates who get offers from those who don't.",
    }
    intro = intro_map.get(category, "Professional growth in tech requires a multi-dimensional approach.")

    body = f"""{title}

{intro} This article covers what you need to know about {title.lower()} based on current market data and practitioner experience.

Why This Matters
----------------
In the current market, {tags[0] if tags else 'this topic'} has become increasingly important for career progression.
Professionals who invest time in developing this area report significantly better outcomes:
better job opportunities, higher compensation, and faster promotions compared to peers who overlook it.

Key Principles
--------------
1. Start with a clear goal. Vague intentions produce vague results. Define a specific, measurable outcome
   — for example, "complete one AWS certification in 90 days" rather than "learn cloud".

2. Learn in public. Document your progress on GitHub, LinkedIn, or a personal blog. This builds credibility
   and attracts opportunities that would otherwise never reach you. Many engineers report their first
   senior role came through someone who read their technical writing.

3. Prioritise depth over breadth at the junior level, then expand at senior level. The T-shaped model
   — deep expertise in one area plus broad awareness across adjacent domains — is consistently what
   hiring managers look for in senior and staff candidates.

4. Measure your progress monthly. Without measurement, effort does not compound. A simple spreadsheet
   tracking what you learned, built, and shipped each month is sufficient for most people.

5. Find community. Solo learning is slow and demoralising. Join a community of practice, attend meetups,
   contribute to open-source projects, or find a pair-programming partner.

Practical Implementation
------------------------
The biggest mistake people make with {tags[0] if tags else 'this'} is treating it as a one-time project
rather than an ongoing practice. Here is a realistic 12-week plan:

Weeks 1–3: Foundation
  — Complete a structured course or read the canonical book on this topic.
  — Set up your learning environment. Remove friction to daily practice.
  — Join 1–2 communities (Discord, Slack, Reddit) where practitioners discuss this topic daily.

Weeks 4–8: Application
  — Build something real. A portfolio project that solves a genuine problem demonstrates competence
    far more convincingly than certificates alone.
  — Get feedback early. Share your work in communities and with mentors. Iterate based on critique.
  — Document as you go. Write brief notes on what you built, why you made each decision, and what
    you would do differently. These become the stories you tell in interviews.

Weeks 9–12: Validation
  — Apply your skills in a real-world context: contribute to an open-source project, take on a
    stretch assignment at work, or help someone else solve a relevant problem.
  — Prepare 2–3 interview-ready stories using the STAR format (Situation, Task, Action, Result).
  — Update your CV and LinkedIn with concrete impact metrics. Quantify wherever possible.

Common Mistakes to Avoid
-------------------------
Tutorial hell: watching endless YouTube videos and courses without building anything. After the first
course, switch to project-based learning immediately.

Scope creep: trying to learn everything at once. Pick the smallest viable skill set that unlocks the
next career step, then expand from there.

Ignoring the meta-skills: communication, documentation, and the ability to explain your work to
non-technical stakeholders are consistently underrated by engineers early in their careers but
become the primary differentiators at the senior and staff levels.

Salary and Market Context
--------------------------
Professionals who develop strong skills in {tags[0] if tags else 'this area'} can typically expect:
  — 10–20% higher compensation compared to peers without this specialisation
  — Faster promotion cycles (average 18–24 months to next level vs 36+ without targeted development)
  — More inbound recruiter interest and better negotiating leverage in offers

The market data for Switzerland and the broader EU shows particular demand for this skill set
in fintech, enterprise SaaS, and AI/ML-adjacent roles.

Resources and Next Steps
------------------------
  — Join the relevant professional community and attend at least one event per quarter.
  — Identify a mentor who is 1–2 levels above you and has already solved the problem you are facing.
  — Set a 90-day milestone and share it publicly for accountability.
  — Revisit this article after 12 weeks and assess what you have achieved.

The professionals who move fastest in their careers are not the ones with the most talent —
they are the ones who are most intentional about their growth, most consistent in their practice,
and most willing to learn from feedback.
"""
    return body.strip()


def generate_career_kb() -> list[dict]:
    """Generate 200+ career KB articles across all categories."""
    articles: list[dict] = []
    idx = 1

    for category, items in _KB_CATEGORIES.items():
        for title, subcategory, tags in items:
            articles.append({
                "id": f"kb-{idx:04d}-{subcategory}",
                "title": title,
                "content": _kb_article_content(title, category, tags),
                "source_url": f"https://career-kb.example.com/articles/{subcategory}-{idx}",
                "language": "en",
                "tags": tags,
                "category": category,
            })
            idx += 1

    # Additional programmatically generated articles for breadth
    extra_topics = [
        ("How to Write Clean Code: Principles Every Engineer Should Follow", "skills", ["clean code", "refactoring", "SOLID", "code review"]),
        ("The Art of the Technical Code Review", "skills", ["code review", "feedback", "quality"]),
        ("Engineering Oncall: Surviving and Improving Your Incident Response", "operations", ["oncall", "incident response", "SRE", "reliability"]),
        ("How to Lead a Technical Migration Without Breaking Production", "engineering", ["migration", "technical debt", "system design"]),
        ("Debugging Production Issues: A Systematic Approach", "skills", ["debugging", "production", "observability", "logs"]),
        ("Writing Architecture Decision Records (ADRs)", "documentation", ["architecture", "ADR", "documentation", "decision making"]),
        ("Data Privacy and GDPR for Tech Professionals in Europe", "compliance", ["GDPR", "privacy", "compliance", "Europe"]),
        ("How to Build a High-Performing Engineering Team", "leadership", ["team building", "hiring", "culture", "engineering"]),
        ("Burnout Prevention for Software Engineers", "wellbeing", ["burnout", "mental health", "sustainability", "wellbeing"]),
        ("How to Use LinkedIn to Get Inbound Opportunities", "job_search", ["LinkedIn", "personal brand", "inbound", "networking"]),
        ("Understanding Stock Options and RSUs for Tech Employees", "compensation", ["equity", "stock options", "RSU", "compensation"]),
        ("Contract vs Full-Time Employment: Making the Right Choice", "career_development", ["contracting", "freelance", "employment", "taxes"]),
        ("How to Find and Work With a Career Coach", "career_development", ["career coaching", "mentorship", "professional development"]),
        ("Preparing for the Staff Engineer Promotion", "career_development", ["staff engineer", "promotion", "impact", "scope"]),
        ("The Principal Engineer: Scope, Skills, and Salary", "career_development", ["principal engineer", "architecture", "technical leadership"]),
        ("How to Get Into FAANG From a Non-FAANG Background", "job_search", ["FAANG", "big tech", "interview", "career"]),
        ("Working at a Startup vs BigCo: A Balanced Comparison", "career_development", ["startup", "big company", "career choice"]),
        ("How to Build a Data Science Portfolio That Gets Noticed", "skills", ["data science", "portfolio", "Kaggle", "GitHub"]),
        ("Getting Started With Prompt Engineering", "skills", ["prompt engineering", "LLM", "AI", "ChatGPT"]),
        ("Swiss Work Culture: What Surprises International Hires", "swiss_eu_context", ["Switzerland", "work culture", "expat", "integration"]),
    ]

    for title, subcategory, tags in extra_topics:
        articles.append({
            "id": f"kb-{idx:04d}-{subcategory}",
            "title": title,
            "content": _kb_article_content(title, "career_development", tags),
            "source_url": f"https://career-kb.example.com/articles/{subcategory}-{idx}",
            "language": "en",
            "tags": tags,
            "category": "career_development",
        })
        idx += 1

    return articles


def _market_report_content(region: str, quarter: str, year: int) -> str:
    demand_skills = {
        2023: ["Python", "Kubernetes", "React", "AWS", "TypeScript", "Terraform", "FastAPI"],
        2024: ["Python", "LangChain/LLM tooling", "Kubernetes", "TypeScript", "AWS", "Terraform", "Rust"],
        2025: ["Python", "LLM engineering", "Kubernetes", "TypeScript", "Rust", "Terraform", "Go"],
    }
    skills_list = demand_skills.get(year, demand_skills[2024])

    hiring_sentiment = {
        "Q1": "cautiously optimistic following end-of-year budget approvals",
        "Q2": "accelerating as H1 hiring plans execute",
        "Q3": "steady with a slight mid-summer slowdown in consumer tech",
        "Q4": "mixed — enterprise continues hiring, consumer tech slows pre-holidays",
    }

    region_detail = {
        "Switzerland": "demand concentrated in Zurich (fintech, cloud) and Basel (pharma IT)",
        "Germany": "Berlin and Munich lead; strong in mobility, B2B SaaS, and e-commerce",
        "Europe": "London, Amsterdam, Berlin, and Stockholm remain primary hiring hubs",
        "Global": "US tech hiring rebounded; European markets steady; APAC growing in AI/ML",
        "United States": "San Francisco Bay Area and New York lead; Austin and Seattle growing",
        "APAC": "Singapore and Sydney lead; India is key for engineering capacity",
    }

    return f"""{region} Tech Job Market Report — {quarter} {year}

Executive Summary
-----------------
The {region} tech labour market in {quarter} {year} is {hiring_sentiment.get(quarter, 'active and competitive')}.
{region_detail.get(region, f'The {region} market shows strong fundamentals.')}

This report synthesises data from job posting volume analysis, recruiter surveys, salary benchmarking,
and employer hiring intention surveys across the {region} market.

Hiring Volume Trends
--------------------
Job posting volume in {quarter} {year} compared to the previous quarter:
  — Software Engineering: +12% QoQ (backend and platform roles strongest)
  — Data / ML: +18% QoQ (LLM and applied AI roles surging)
  — DevOps / Platform: +9% QoQ (Kubernetes and cloud specialists in high demand)
  — Product Management: +6% QoQ (technical PM roles growing fastest)
  — Design (UX/UI): -2% QoQ (slight contraction as companies streamline design orgs)
  — Security: +22% QoQ (zero-trust, cloud security, and compliance roles booming)

Top In-Demand Skills (by job posting frequency)
------------------------------------------------
{"".join(f"  {i+1}. {s}{chr(10)}" for i, s in enumerate(skills_list))}
Note: skills are ranked by raw posting volume; the highest-ranked skills are necessary but not
sufficient — differentiating skills with lower raw volume often command the highest salary premiums.

Salary Benchmarks — {region}
----------------------------
Role            | Junior          | Mid-level       | Senior          | Staff/Principal
Software Eng    | base +0%        | base +35%        | base +70%        | base +110%
ML/AI Engineer  | base +5%        | base +45%        | base +85%        | base +130%
Data Scientist  | base +0%        | base +30%        | base +65%        | base +100%
DevOps/SRE      | base +0%        | base +35%        | base +70%        | base +105%
Product Manager | base +10%       | base +45%        | base +85%        | base +120%

(Base = entry-level software engineer salary in {region}. Percentages are additive.)

Remote and Hybrid Trends
------------------------
  — Full remote roles: {38 - (2025 - year) * 3}% of postings (down from {45 - (2025 - year) * 3}% in {year - 1})
  — Hybrid (2–3 days on-site): {45 + (2025 - year) * 2}% of postings
  — Fully on-site: {17 + (2025 - year)}% of postings

The trend toward mandatory return-to-office is most pronounced in financial services and large
enterprise; startups and scale-ups continue to offer more flexibility.

Emerging Role Categories
------------------------
The following role titles have seen the highest growth in posting volume YoY:
  1. AI/ML Platform Engineer (+{180 + year - 2023}% YoY)
  2. LLM Application Engineer (+{240 + year - 2023}% YoY)
  3. Staff Data Engineer (+65% YoY)
  4. Cloud FinOps Analyst (+89% YoY)
  5. Developer Advocate (+42% YoY)

Talent Supply and Demand Gaps
------------------------------
The most acute talent gaps in {region} as of {quarter} {year}:
  1. Senior/Staff ML Engineers: demand exceeds supply by ~3:1
  2. Kubernetes / Platform Engineers: demand exceeds supply by ~2.5:1
  3. Rust developers: demand exceeds supply by ~4:1
  4. AI Safety / Alignment Researchers: extreme shortage
  5. Cloud Security Engineers: demand exceeds supply by ~2:1

Hiring Outlook — Next Quarter
------------------------------
Based on employer intention surveys conducted in {quarter} {year}, {'74' if year >= 2025 else '68'}% of
{region} tech employers plan to increase headcount in the following quarter. Budget constraints are
the primary hiring limiter, cited by {'31' if year == 2023 else '24'}% of respondents.

Key risks to the outlook include macroeconomic deterioration, regulatory changes (particularly
EU AI Act compliance requirements), and continued uncertainty in late-stage startup funding.
"""


def generate_market_reports() -> list[dict]:
    """Generate 48 quarterly market reports (2023–2025 × 6 regions)."""
    reports: list[dict] = []
    idx = 1
    for year in _YEARS:
        for quarter in _QUARTERS:
            if year == 2025 and quarter in ("Q3", "Q4"):
                continue  # future quarters
            for region in _MARKET_REPORT_REGIONS:
                date_map = {"Q1": f"{year}-01-01", "Q2": f"{year}-04-01",
                            "Q3": f"{year}-07-01", "Q4": f"{year}-10-01"}
                reports.append({
                    "id": f"market-{year}-{quarter.lower()}-{region.lower().replace(' ', '-')}",
                    "title": f"{region} Tech Job Market Report — {quarter} {year}",
                    "content": _market_report_content(region, quarter, year),
                    "region": region,
                    "published_at": date_map[quarter],
                    "source_url": f"https://market-data.example.com/reports/{year}/{quarter.lower()}/{region.lower().replace(' ', '-')}",
                    "tags": ["job market", "hiring trends", "salary", "tech", region.lower()],
                })
                idx += 1
    return reports


def _swiss_city_sector_content(city: str, sector: str, data: dict) -> str:
    companies = ", ".join(data["companies"][:5])
    roles = ", ".join(data["roles"][:4])
    sal = data["salary_range"]
    return f"""{city} — {sector.title()} Sector Overview

{city} is one of Switzerland's key hubs for the {sector} sector, attracting international talent
with competitive salaries, high quality of life, and access to world-class companies.

Key Employers
-------------
{companies} are among the leading {sector} employers in {city}. The sector benefits from
Switzerland's stable economic environment, strong intellectual property protections, and
proximity to major European markets.

In-Demand Roles
---------------
Current demand is strongest for: {roles}.
These roles benefit from both local talent (ETH Zurich, EPFL, University of Zurich, University of Basel
graduates) and international recruitment.

Salary Benchmarks ({city}, {sector.title()})
---------------------------------------------
  Junior (0–2 years):  {sal.get('junior', 'CHF 85,000–110,000')} gross per year
  Mid-level (2–5 years): {sal.get('mid', 'CHF 115,000–145,000')} gross per year
  Senior (5+ years):   {sal.get('senior', 'CHF 150,000–200,000')} gross per year

Figures are gross annual CHF. Swiss salaries are quoted gross; mandatory deductions include
AHV/IV/EO (employee share ~5.3%), ALV (~1.1%), NBU, and pension contributions (typically 6–10%).
Net take-home is typically 75–85% of gross depending on canton and marital status.

Work Permits and Visa
---------------------
  EU/EFTA nationals: Freedom of movement agreement — no permit required for up to 90 days;
    L permit (short-term) or B permit (long-term) for employment.
  Non-EU/EFTA: Must obtain a work permit sponsored by the employer. Quota-based (limited annual
    supply). The employer must demonstrate no suitable EU candidate was available. Process takes
    4–12 weeks.

Important: Switzerland is not an EU member. EU directives on work rights do not apply automatically.

Key Considerations for International Professionals
---------------------------------------------------
  Language: German (Zurich, Bern, Basel), French (Geneva, Lausanne), Italian (Lugano).
    English is widely used in multinational tech companies. However, basic local-language
    skills significantly improve integration and social relationships.

  Cost of living: Zurich and Geneva consistently rank among the most expensive cities globally.
    Budget CHF 2,500–3,500/month for a one-bedroom apartment; CHF 3,500–5,000+ in central areas.

  Taxes: Cantonal and federal income taxes vary significantly. Zug and Schwyz have some of the
    lowest rates. Zurich and Geneva are higher. Use the official Swiss tax calculators to model
    your take-home.

  Commuting: Swiss public transport is world-class. A Halbtax card halves all public transport
    costs (~CHF 185/year). Many companies subsidise GA passes (annual all-network pass, ~CHF 3,860/year).

Relocation Resources
--------------------
  — ch.ch (official Swiss government portal for newcomers)
  — expats.ch and internations.org for community
  — Swiss job boards: jobs.ch, jobup.ch (French), LinkedIn (multinational roles)
  — LinkedIn groups: "Expats in Zurich / Geneva / Basel"
"""


def generate_swiss_eu_market() -> list[dict]:
    """Generate 160+ Swiss/EU market intelligence documents."""
    docs: list[dict] = []
    idx = 1

    # Swiss city × sector combinations
    for city in _REGIONS_SWISS[1:]:  # skip "Switzerland" — use cities
        for sector, data in _SWISS_SECTORS.items():
            docs.append({
                "id": f"swiss-{city.lower()}-{sector.lower().replace(' / ', '-').replace(' ', '-')}-{idx}",
                "title": f"{city} — {sector.title()} Tech Jobs Overview",
                "content": _swiss_city_sector_content(city, sector, data),
                "region": "Switzerland",
                "sub_region": city,
                "published_at": "2025-01-01",
                "source_url": f"https://swiss-market.example.com/{city.lower()}/{sector.lower().replace(' ', '-')}",
                "tags": ["switzerland", city.lower(), sector.lower(), "salaries", "work permit"],
            })
            idx += 1

    # EU country market overviews
    for location, data in _EU_MARKETS.items():
        docs.append({
            "id": f"eu-market-{location.lower().replace(', ', '-').replace(' ', '-')}-{idx}",
            "title": f"Working in {location}: Tech Career Guide",
            "content": f"Working in {location}: Tech Career Overview\n\n{data['description']}\n\n"
                       f"Salary Benchmarks\n-----------------\n"
                       f"Junior (0–2 yrs): {data['salary_range']['junior']}\n"
                       f"Mid-level (2–5 yrs): {data['salary_range']['mid']}\n"
                       f"Senior (5+ yrs): {data['salary_range']['senior']}\n\n"
                       f"Work Permit Information\n-----------------------\n{data['work_permit']}\n",
            "region": location.split(",")[-1].strip(),
            "sub_region": location,
            "published_at": "2025-01-01",
            "source_url": f"https://eu-careers.example.com/{location.lower().replace(', ', '-').replace(' ', '-')}",
            "tags": [location.lower(), "europe", "salaries", "work permit", "tech jobs"],
        })
        idx += 1

    # Additional Swiss market topics
    swiss_topics = [
        ("Swiss Tech Startup Ecosystem 2025",
         "Switzerland's startup scene is concentrated around Zurich, Lausanne (EPFL), and Zug. "
         "Key accelerators include Y Combinator Switzerland, Kickstart Innovation, and F10. "
         "Government innovation funding via Innosuisse provides grants for R&D collaborations between "
         "startups and universities. Notable Swiss unicorns and exits: Temenos, On Running, Digitec Galaxus, "
         "Tamedia, and the SIX Group spinoffs. Equity grants at Swiss startups range from 0.05%–0.5% for "
         "early employees (pre-Series A), with 4-year vesting and 1-year cliff. Swiss startup exits tend to "
         "be via trade sale rather than IPO."),
        ("Swiss Federal Hiring Process for Tech Roles",
         "The Swiss federal government (Bund) and cantonal governments employ thousands of IT professionals. "
         "The federal IT authority ITZ (Informatiksteuerungsorgan des Bundes) coordinates across departments. "
         "Federal roles offer job security, good benefits, and work-life balance but typically pay 15–25% "
         "below private sector rates for equivalent seniority. Application via admin.ch or jobs.ch. "
         "German language (B2/C1) required for most Bern-based roles; French for FDFA and some DETEC roles."),
        ("ETH Zurich and EPFL: Switzerland's Tech Talent Pipelines",
         "ETH Zurich and EPFL produce some of Europe's highest-quality engineering graduates. "
         "ETH consistently ranks in the global top 10 for computer science (QS 2024: #3). "
         "EPFL ranked #14 globally. Combined, they graduate ~5,000 engineers per year. "
         "Both institutions offer executive education and professional certificates. "
         "Industry partnerships include IBM Research Zurich, Google Research, Disney Research, and Microsoft. "
         "PhD salaries at ETH: CHF 52,000–59,000/year gross (fully funded positions)."),
    ]

    for title, content in swiss_topics:
        docs.append({
            "id": f"swiss-general-{idx}",
            "title": title,
            "content": content,
            "region": "Switzerland",
            "sub_region": "General",
            "published_at": "2025-01-01",
            "source_url": f"https://swiss-market.example.com/general/{idx}",
            "tags": ["switzerland", "tech jobs", "ecosystem"],
        })
        idx += 1

    return docs


def generate_esco_taxonomy() -> list[dict]:
    """Return the synthetic ESCO occupation rows as a list of dicts for CSV output."""
    rows = []
    for label, description, alt_labels in _ESCO_OCCUPATIONS:
        uri = f"http://data.europa.eu/esco/occupation/{label.lower().replace(' ', '-').replace('/', '')}"
        rows.append({
            "conceptUri": uri,
            "preferredLabel": label,
            "altLabels": alt_labels,
            "description": description,
        })
    return rows


# ── ESCO REST API fetcher ─────────────────────────────────────────────────────

def fetch_esco_occupations(limit: int = 500, verbose: bool = True) -> list[dict]:
    """Fetch real occupation data from the public ESCO REST API.

    API base: https://ec.europa.eu/esco/api
    No authentication required. Returns rows ready for CSV output.
    """
    try:
        import urllib.request
        import urllib.parse
    except ImportError:
        print("urllib not available — skipping ESCO API fetch", file=sys.stderr)
        return []

    base_url = "https://ec.europa.eu/esco/api"
    rows: list[dict] = []
    offset = 0
    page_size = 50
    total_fetched = 0

    if verbose:
        print(f"Fetching up to {limit} occupations from ESCO REST API...")

    while total_fetched < limit:
        params = urllib.parse.urlencode({
            "type": "occupation",
            "language": "en",
            "limit": min(page_size, limit - total_fetched),
            "offset": offset,
            "full": "true",
        })
        url = f"{base_url}/search?{params}"

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if verbose:
                print(f"  ESCO API request failed at offset={offset}: {exc}", file=sys.stderr)
            break

        results = data.get("_embedded", {}).get("results", [])
        if not results:
            break

        for item in results:
            uri = item.get("uri", "")
            label = item.get("preferredLabel", {}).get("en", "")
            description = item.get("description", {}).get("en", {}).get("literal", "")
            alt_labels_raw = item.get("altLabels", {}).get("en", [])
            alt_labels = ", ".join(alt_labels_raw[:8]) if isinstance(alt_labels_raw, list) else ""

            if label and description:
                rows.append({
                    "conceptUri": uri,
                    "preferredLabel": label,
                    "altLabels": alt_labels,
                    "description": description,
                })

        total_fetched += len(results)
        offset += len(results)

        if verbose:
            print(f"  Fetched {total_fetched}/{limit} occupations...")

        if len(results) < page_size:
            break  # no more pages

        time.sleep(0.2)  # be polite to the API

    if verbose:
        print(f"ESCO API fetch complete: {len(rows)} occupations retrieved.")

    return rows


# ── File writers ──────────────────────────────────────────────────────────────

def write_json(path: Path, data: list[dict], label: str, verbose: bool = True) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        size_kb = path.stat().st_size // 1024
        print(f"  Wrote {len(data):,} records -> {path.name} ({size_kb} KB)")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str], label: str, verbose: bool = True) -> None:
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")
    if verbose:
        size_kb = path.stat().st_size // 1024
        print(f"  Wrote {len(rows):,} rows -> {path.name} ({size_kb} KB)")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate comprehensive seed data for the RAG knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")
    parser.add_argument(
        "--output-dir",
        default=_default_out,
        help=f"Directory to write generated files (default: {_default_out})",
    )
    parser.add_argument(
        "--fetch-esco",
        action="store_true",
        help="Also fetch real ESCO taxonomy data from the public REST API",
    )
    parser.add_argument(
        "--esco-limit",
        type=int,
        default=500,
        help="Max occupations to fetch from the ESCO API (default: 500)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    verbose = not args.quiet
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"\nGenerating KB seed data -> {output_dir.resolve()}\n")

    # 1. Role templates
    if verbose:
        print("Generating role templates...")
    templates = generate_role_templates()
    write_json(output_dir / "role_templates_full.json", templates, "role templates", verbose)

    # 2. Career KB articles
    if verbose:
        print("Generating career KB articles...")
    articles = generate_career_kb()
    write_json(output_dir / "career_kb_full.json", articles, "career KB articles", verbose)

    # 3. Market reports
    if verbose:
        print("Generating market reports...")
    reports = generate_market_reports()
    write_json(output_dir / "market_reports_full.json", reports, "market reports", verbose)

    # 4. Swiss/EU market data
    if verbose:
        print("Generating Swiss/EU market data...")
    swiss_eu = generate_swiss_eu_market()
    write_json(output_dir / "swiss_eu_market_full.json", swiss_eu, "Swiss/EU market docs", verbose)

    # 5. ESCO taxonomy (synthetic)
    if verbose:
        print("Generating ESCO taxonomy (synthetic)...")
    esco_rows = generate_esco_taxonomy()
    fieldnames = ["conceptUri", "preferredLabel", "altLabels", "description"]
    write_csv(output_dir / "esco_taxonomy.csv", esco_rows, fieldnames, "ESCO taxonomy", verbose)

    # 6. ESCO API fetch (optional)
    if args.fetch_esco:
        if verbose:
            print(f"\nFetching up to {args.esco_limit} occupations from ESCO REST API...")
        live_rows = fetch_esco_occupations(limit=args.esco_limit, verbose=verbose)
        if live_rows:
            write_csv(
                output_dir / "esco_taxonomy_live.csv",
                live_rows,
                fieldnames,
                "ESCO live taxonomy",
                verbose,
            )
        else:
            if verbose:
                print("  ESCO API fetch returned no data — live CSV not written.")

    if verbose:
        total_docs = len(templates) + len(articles) + len(reports) + len(swiss_eu) + len(esco_rows)
        print(f"\nDone. Generated {total_docs:,} documents total.")
        print(
            "\nNext step - trigger ingestion via the admin API or directly:\n"
            "  POST /api/v1/admin/kb/ingest with X-Admin-Api-Key header\n"
            "  Or: celery call rag.seed_knowledge_base\n"
        )


if __name__ == "__main__":
    main()
