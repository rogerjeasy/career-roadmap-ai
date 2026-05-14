"""Rules-based job title normalisation client.

Maps raw job title strings to canonical forms using a curated lookup table
covering common tech industry variants, abbreviations, and international
equivalents.  Runs entirely in-process — no network, no API key.

The normaliser also extracts:
  - seniority_level: junior | mid | senior | lead | principal | staff | manager
                     | director | vp | c-level
  - role_family: engineering | data | product | design | management |
                 devops | security | sales | marketing | operations
"""
from __future__ import annotations

import re

from models import NormalizedJobTitle

# ── Seniority keyword sets ─────────────────────────────────────────────────────

_SENIORITY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(c-level|cto|cio|cso|chief\s+\w+\s+officer)\b", "c-level"),
    (r"\b(vp|vice\s*president)\b", "vp"),
    (r"\b(director|head\s+of)\b", "director"),
    (r"\b(principal|distinguished|fellow)\b", "principal"),
    (r"\b(staff)\b", "staff"),
    (r"\b(lead|tech\s*lead|team\s*lead)\b", "lead"),
    (r"\b(senior|sr\.?|iii)\b", "senior"),
    (r"\b(mid(-level)?|ii)\b", "mid"),
    (r"\b(junior|jr\.?|i\b|entry[-\s]level|graduate|intern|trainee)\b", "junior"),
    (r"\b(manager|mgr\.?)\b", "manager"),
]

# ── Role family keyword sets ───────────────────────────────────────────────────

_ROLE_FAMILY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(machine\s*learning|ml|artificial\s*intelligence|ai|data\s*scientist|nlp|computer\s*vision)\b", "data"),
    (r"\b(data\s*(engineer|analyst|architect|warehouse|pipeline))\b", "data"),
    (r"\b(devops|sre|site\s*reliability|platform\s*engineer|cloud\s*engineer|infrastructure|devsecops)\b", "devops"),
    (r"\b(security|appsec|penetration\s*tester|red\s*team|soc\s*analyst|cybersecurity)\b", "security"),
    (r"\b(product\s*manager|pm|product\s*owner|po|product\s*lead)\b", "product"),
    (r"\b(ux|ui|user\s*experience|user\s*interface|designer|interaction\s*design|visual\s*design)\b", "design"),
    (r"\b(engineering\s*manager|director\s*of\s*engineering|vp\s*of\s*engineering)\b", "management"),
    (r"\b(sales|account\s*(executive|manager)|business\s*development)\b", "sales"),
    (r"\b(marketing|growth|seo|content|demand\s*gen)\b", "marketing"),
    (r"\b(operations|ops|program\s*manager|project\s*manager|scrum|agile\s*coach)\b", "operations"),
    (r"\b(software|backend|frontend|full[-\s]*stack|mobile|ios|android|web|api)\b", "engineering"),
    (r"\b(engineer|developer|programmer|architect|coder)\b", "engineering"),
]

# ── Canonical title lookup table ──────────────────────────────────────────────

_CANONICAL: dict[str, str] = {
    # Software Engineering
    "software engineer": "Software Engineer",
    "software developer": "Software Engineer",
    "swe": "Software Engineer",
    "sde": "Software Development Engineer",
    "programmer": "Software Engineer",
    "coder": "Software Engineer",
    "backend engineer": "Backend Engineer",
    "backend developer": "Backend Engineer",
    "frontend engineer": "Frontend Engineer",
    "frontend developer": "Frontend Engineer",
    "front-end engineer": "Frontend Engineer",
    "front-end developer": "Frontend Engineer",
    "full stack engineer": "Full Stack Engineer",
    "full-stack engineer": "Full Stack Engineer",
    "fullstack engineer": "Full Stack Engineer",
    "full stack developer": "Full Stack Engineer",
    "web developer": "Web Developer",
    "web engineer": "Web Engineer",
    "mobile engineer": "Mobile Engineer",
    "mobile developer": "Mobile Engineer",
    "ios developer": "iOS Engineer",
    "ios engineer": "iOS Engineer",
    "android developer": "Android Engineer",
    "android engineer": "Android Engineer",
    "software architect": "Software Architect",
    "solutions architect": "Solutions Architect",
    "enterprise architect": "Enterprise Architect",
    # Data & ML
    "data scientist": "Data Scientist",
    "machine learning engineer": "Machine Learning Engineer",
    "ml engineer": "Machine Learning Engineer",
    "ai engineer": "AI Engineer",
    "artificial intelligence engineer": "AI Engineer",
    "data engineer": "Data Engineer",
    "data analyst": "Data Analyst",
    "business analyst": "Business Analyst",
    "data architect": "Data Architect",
    "analytics engineer": "Analytics Engineer",
    "research scientist": "Research Scientist",
    "applied scientist": "Applied Scientist",
    "research engineer": "Research Engineer",
    "nlp engineer": "NLP Engineer",
    "computer vision engineer": "Computer Vision Engineer",
    "mlops engineer": "MLOps Engineer",
    # DevOps / Platform
    "devops engineer": "DevOps Engineer",
    "site reliability engineer": "Site Reliability Engineer",
    "sre": "Site Reliability Engineer",
    "platform engineer": "Platform Engineer",
    "cloud engineer": "Cloud Engineer",
    "infrastructure engineer": "Infrastructure Engineer",
    "devsecops engineer": "DevSecOps Engineer",
    "kubernetes engineer": "Platform Engineer",
    # Security
    "security engineer": "Security Engineer",
    "application security engineer": "Application Security Engineer",
    "cybersecurity engineer": "Cybersecurity Engineer",
    "security analyst": "Security Analyst",
    "penetration tester": "Penetration Tester",
    "pentester": "Penetration Tester",
    # Product & Design
    "product manager": "Product Manager",
    "technical product manager": "Technical Product Manager",
    "product owner": "Product Owner",
    "ux designer": "UX Designer",
    "ui designer": "UI Designer",
    "ux/ui designer": "UX/UI Designer",
    "product designer": "Product Designer",
    "interaction designer": "Interaction Designer",
    # Management
    "engineering manager": "Engineering Manager",
    "director of engineering": "Director of Engineering",
    "vp of engineering": "VP of Engineering",
    "cto": "Chief Technology Officer",
    "chief technology officer": "Chief Technology Officer",
    "head of engineering": "Head of Engineering",
    "tech lead": "Tech Lead",
    "team lead": "Team Lead",
    # QA & Testing
    "qa engineer": "QA Engineer",
    "quality assurance engineer": "QA Engineer",
    "software test engineer": "QA Engineer",
    "test engineer": "QA Engineer",
    "sdet": "Software Development Engineer in Test",
}


def normalize_title(raw_title: str, industry: str | None = None) -> NormalizedJobTitle:
    """Normalise a raw job title to its canonical form.

    Returns a ``NormalizedJobTitle`` with canonical_title, seniority_level,
    role_family, and a confidence score between 0 and 1.
    """
    cleaned = raw_title.strip().lower()
    # Strip common suffixes: "(remote)", "- london", "| tech co."
    cleaned = re.sub(r"[\(\[].*?[\)\]]", "", cleaned)
    cleaned = re.sub(r"[-|,].*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Extract seniority
    seniority: str | None = None
    for pattern, level in _SENIORITY_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            seniority = level
            break

    # Strip seniority tokens for canonical lookup
    lookup_key = re.sub(
        r"\b(senior|sr\.?|junior|jr\.?|lead|principal|staff|mid|i+|iii?|vp|director|head of|manager|mgr\.?)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    lookup_key = re.sub(r"\s+", " ", lookup_key).strip()

    # Direct lookup
    canonical = _CANONICAL.get(lookup_key) or _CANONICAL.get(cleaned)
    confidence = 1.0 if canonical else 0.0

    if not canonical:
        # Partial match — find best substring match
        best_match: str | None = None
        best_len = 0
        for key, val in _CANONICAL.items():
            if key in cleaned and len(key) > best_len:
                best_len = len(key)
                best_match = val
        if best_match:
            canonical = best_match
            confidence = 0.7
        else:
            # Title-case fallback
            canonical = _title_case(raw_title.strip())
            confidence = 0.3

    # Re-apply seniority prefix to canonical if it was stripped
    if seniority and seniority not in ("manager", "director", "vp", "c-level"):
        prefix_map = {
            "junior": "Junior",
            "mid": "Mid-Level",
            "senior": "Senior",
            "lead": "Lead",
            "principal": "Principal",
            "staff": "Staff",
        }
        prefix = prefix_map.get(seniority)
        if prefix and not canonical.lower().startswith(prefix.lower()):
            canonical = f"{prefix} {canonical}"

    # Determine role family
    role_family: str | None = None
    for pattern, family in _ROLE_FAMILY_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            role_family = family
            break

    return NormalizedJobTitle(
        raw_title=raw_title,
        canonical_title=canonical,
        seniority_level=seniority,
        role_family=role_family,
        confidence=round(confidence, 2),
        source="rules",
    )


def _title_case(s: str) -> str:
    """Convert to Title Case but keep known acronyms uppercase."""
    _ACRONYMS = {"ai", "ml", "nlp", "ios", "api", "ux", "ui", "sre", "devops", "qa", "hr", "it"}
    words = s.split()
    result = []
    for word in words:
        if word.lower() in _ACRONYMS:
            result.append(word.upper())
        else:
            result.append(word.capitalize())
    return " ".join(result)
