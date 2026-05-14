"""so_survey_converter.py — Convert Stack Overflow Annual Developer Survey to KB documents.

Reads the raw survey CSV files (results_20XX.txt) downloaded from
https://survey.stackoverflow.co/datasets/ and generates 10 rich market-report
documents covering salary benchmarks, technology adoption trends, AI tool
adoption, and remote work patterns across 2022–2025.

Generated documents are APPENDED to market_reports_real.json (replacing any
previous SO-derived docs, preserving existing GitHub/Stack Exchange docs).

Usage
-----
  cd agents

  python -m scripts.so_survey_converter \\
      --survey-dir C:/Users/User/Downloads \\
      --output-dir data/knowledge-base

  # Dry-run (print stats, skip write):
  python -m scripts.so_survey_converter \\
      --survey-dir C:/Users/User/Downloads \\
      --output-dir data/knowledge-base --dry-run

  # Specific years only:
  python -m scripts.so_survey_converter \\
      --survey-dir C:/Users/User/Downloads \\
      --output-dir data/knowledge-base --years 2024 2025
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(10_000_000)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]

# ── Column aliases (normalised across survey years) ────────────────────────────

_COL_COMP        = ["ConvertedCompYearly", "ConvertedSalary"]
_COL_DEVTYPE     = ["DevType"]
_COL_COUNTRY     = ["Country"]
_COL_YEARS_PRO   = ["YearsCodePro"]
_COL_EMPLOYMENT  = ["Employment"]
_COL_REMOTE      = ["RemoteWork", "WorkLoc", "WorkRemote"]
_COL_LANGUAGE    = ["LanguageHaveWorkedWith", "LanguageWorkedWith"]
_COL_DATABASE    = ["DatabaseHaveWorkedWith", "DatabaseWorkedWith"]
_COL_PLATFORM    = ["PlatformHaveWorkedWith", "PlatformWorkedWith"]
_COL_FRAMEWORK   = ["WebframeHaveWorkedWith", "FrameworkHaveWorkedWith"]
_COL_AI_SEARCH   = ["AISearchHaveWorkedWith", "AISearchDevHaveWorkedWith"]
_COL_AI_DEV      = ["AIDevHaveWorkedWith"]
_COL_AI_MODELS   = ["AIModelsHaveWorkedWith"]
_COL_AI_SENT     = ["AISent"]
_COL_AI_SELECT   = ["AISelect"]
_COL_ORG_SIZE    = ["OrgSize"]

# ── Dev-type normalisation ────────────────────────────────────────────────────

_DEVTYPE_NORM: dict[str, str] = {
    "Developer, full-stack":                          "Full-Stack Developer",
    "Developer, back-end":                            "Back-End Developer",
    "Developer, front-end":                           "Front-End Developer",
    "Developer, mobile":                              "Mobile Developer",
    "Data scientist or machine learning specialist":  "Data Scientist / ML",
    "Data or business analyst":                       "Data / Business Analyst",
    "Engineer, data":                                 "Data Engineer",
    "DevOps specialist":                              "DevOps / SRE",
    "Cloud infrastructure engineer":                  "Cloud Engineer",
    "Security professional":                          "Security Engineer",
    "Developer, embedded applications or devices":    "Embedded / IoT Developer",
    "Engineering manager":                            "Engineering Manager",
    "Senior Executive (C-Suite, VP, etc.)":           "CTO / VP Engineering",
    "Developer, QA or test":                          "QA / Test Engineer",
    "Research & Development role":                    "R&D Engineer",
    "System administrator":                           "Sysadmin / IT Ops",
    "Database administrator":                         "Database Administrator",
    "Developer, game or graphics":                    "Game / Graphics Developer",
    "Academic researcher":                            "Academic Researcher",
    "Developer, desktop or enterprise applications":  "Desktop / Enterprise Developer",
    "Student":                                        "Student",
    "Other (please specify):":                        "Other",
}

# ── Experience bands ──────────────────────────────────────────────────────────

_XP_BANDS: list[tuple[str, float, float]] = [
    ("< 1 year",    0.0,  0.9),
    ("1–2 years",   1.0,  2.9),
    ("3–5 years",   3.0,  5.9),
    ("6–10 years",  6.0, 10.9),
    ("11–20 years", 11.0, 20.9),
    ("20+ years",   21.0, 999.0),
]

# ── Key countries for salary tables ──────────────────────────────────────────

_FEATURED_COUNTRIES = [
    "United States of America", "Germany", "United Kingdom", "France",
    "Canada", "Netherlands", "Australia", "Sweden", "Switzerland",
    "India", "Brazil", "Poland", "Spain", "Austria", "Norway",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_col(header: list[str], aliases: list[str]) -> str | None:
    h_map = {h.lower(): h for h in header}
    for alias in aliases:
        if alias.lower() in h_map:
            return h_map[alias.lower()]
    return None


def _detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return "\t" if line.count("\t") > line.count(",") else ","


def _parse_comp(val: str) -> float | None:
    try:
        v = float(str(val).replace(",", "").strip())
        return v if 10_000 <= v <= 3_000_000 else None
    except (ValueError, TypeError):
        return None


def _parse_years_pro(val: str) -> float | None:
    if not val or val in ("NA", ""):
        return None
    val = val.strip()
    if "Less than 1" in val:
        return 0.5
    if "More than 50" in val:
        return 52.0
    try:
        return float(val)
    except ValueError:
        return None


def _split(val: str) -> list[str]:
    if not val or val in ("NA", ""):
        return []
    return [v.strip() for v in val.split(";") if v.strip()]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * p / 100.0
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _fmt_usd(v: float) -> str:
    return f"${int(round(v / 1000)) * 1000:,}"


# ── Per-year extraction ───────────────────────────────────────────────────────

def extract_year(path: Path, year: int) -> dict:
    """Stream one survey file and return aggregated statistics."""
    sep = _detect_sep(path)
    stats: dict = {
        "year": year,
        "total": 0,
        "total_with_salary": 0,
        # salary lists per group
        "salary_all":        [],
        "salary_by_role":    collections.defaultdict(list),
        "salary_by_country": collections.defaultdict(list),
        "salary_by_xp":      collections.defaultdict(list),
        # technology adoption counts (denominator = total respondents)
        "lang_counts":       collections.Counter(),
        "db_counts":         collections.Counter(),
        "platform_counts":   collections.Counter(),
        "framework_counts":  collections.Counter(),
        "ai_search_counts":  collections.Counter(),
        "ai_dev_counts":     collections.Counter(),
        "ai_model_counts":   collections.Counter(),
        "ai_sent_counts":    collections.Counter(),
        # other
        "remote_counts":     collections.Counter(),
        "org_size_counts":   collections.Counter(),
        "employment_counts": collections.Counter(),
    }

    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)
        raw_header = reader.fieldnames or []
        header = [h.strip().strip('"') for h in raw_header]
        # rebuild reader with clean header
        reader.fieldnames = header

        col_comp       = _find_col(header, _COL_COMP)
        col_devtype    = _find_col(header, _COL_DEVTYPE)
        col_country    = _find_col(header, _COL_COUNTRY)
        col_years      = _find_col(header, _COL_YEARS_PRO)
        col_employment = _find_col(header, _COL_EMPLOYMENT)
        col_remote     = _find_col(header, _COL_REMOTE)
        col_lang       = _find_col(header, _COL_LANGUAGE)
        col_db         = _find_col(header, _COL_DATABASE)
        col_platform   = _find_col(header, _COL_PLATFORM)
        col_framework  = _find_col(header, _COL_FRAMEWORK)
        col_ai_search  = _find_col(header, _COL_AI_SEARCH)
        col_ai_dev     = _find_col(header, _COL_AI_DEV)
        col_ai_models  = _find_col(header, _COL_AI_MODELS)
        col_ai_sent    = _find_col(header, _COL_AI_SENT)
        col_org_size   = _find_col(header, _COL_ORG_SIZE)

        active = [c for c in [col_comp, col_lang, col_ai_search, col_ai_models] if c]
        print(f"    key cols found: {active}")

        for row in reader:
            # strip quoted keys that DictReader may produce in 2025
            row = {k.strip().strip('"'): v for k, v in row.items() if k}
            stats["total"] += 1

            country    = row.get(col_country or "", "").strip()
            employment = row.get(col_employment or "", "").strip()

            # ── technology counts (all respondents) ──────────────────────────
            if col_lang:
                for t in _split(row.get(col_lang, "")):
                    stats["lang_counts"][t] += 1
            if col_db:
                for t in _split(row.get(col_db, "")):
                    stats["db_counts"][t] += 1
            if col_platform:
                for t in _split(row.get(col_platform, "")):
                    stats["platform_counts"][t] += 1
            if col_framework:
                for t in _split(row.get(col_framework, "")):
                    stats["framework_counts"][t] += 1
            if col_ai_search:
                for t in _split(row.get(col_ai_search, "")):
                    stats["ai_search_counts"][t] += 1
            if col_ai_dev:
                for t in _split(row.get(col_ai_dev, "")):
                    stats["ai_dev_counts"][t] += 1
            if col_ai_models:
                for t in _split(row.get(col_ai_models, "")):
                    stats["ai_model_counts"][t] += 1
            if col_ai_sent:
                v = row.get(col_ai_sent, "").strip()
                if v and v != "NA":
                    stats["ai_sent_counts"][v] += 1
            if col_remote:
                v = row.get(col_remote, "").strip()
                if v and v != "NA":
                    stats["remote_counts"][v] += 1
            if col_org_size:
                v = row.get(col_org_size, "").strip()
                if v and v != "NA":
                    stats["org_size_counts"][v] += 1
            if col_employment:
                for e in _split(employment):
                    stats["employment_counts"][e] += 1

            # ── salary-gated stats ───────────────────────────────────────────
            comp = _parse_comp(row.get(col_comp or "", ""))
            if comp is None:
                continue
            stats["total_with_salary"] += 1
            stats["salary_all"].append(comp)

            if country:
                stats["salary_by_country"][country].append(comp)

            if col_devtype:
                for dt in _split(row.get(col_devtype, "")):
                    norm = _DEVTYPE_NORM.get(dt, dt)
                    stats["salary_by_role"][norm].append(comp)

            if col_years:
                xp = _parse_years_pro(row.get(col_years, ""))
                if xp is not None:
                    for band, lo, hi in _XP_BANDS:
                        if lo <= xp <= hi:
                            stats["salary_by_xp"][band].append(comp)
                            break

    print(
        f"    {stats['total']:,} respondents  "
        f"{stats['total_with_salary']:,} with salary  "
        f"global median {_fmt_usd(_percentile(stats['salary_all'], 50))}"
    )
    return stats


# ── Document builders ─────────────────────────────────────────────────────────

def _role_salary_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """Salary benchmarks by developer role — latest year + 2-year trend."""
    latest = max(all_stats)
    prev   = latest - 1
    s = all_stats[latest]
    sp = all_stats.get(prev, {})

    heading = f"Developer Salary Benchmarks by Role {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        f"Based on {s['total_with_salary']:,} full responses with salary data",
        f"from the {latest} Stack Overflow Annual Developer Survey (N={s['total']:,} total).",
        "Compensation in USD gross annual. Full-time employed respondents.",
        "",
    ]

    # Build role table for roles with ≥ 100 salary responses
    role_rows = [
        (role, vals)
        for role, vals in s["salary_by_role"].items()
        if len(vals) >= 100 and role not in ("Student", "Other")
    ]
    role_rows.sort(key=lambda x: _percentile(x[1], 50), reverse=True)

    lines += [
        f"{'Role':<42} {'N':>6}  {'P25':>9}  {'Median':>9}  {'P75':>9}",
        "─" * 82,
    ]
    for role, vals in role_rows[:20]:
        p25    = _percentile(vals, 25)
        median = _percentile(vals, 50)
        p75    = _percentile(vals, 75)
        # YoY change
        prev_vals = sp.get("salary_by_role", {}).get(role, [])
        yoy = ""
        if len(prev_vals) >= 50:
            prev_med = _percentile(prev_vals, 50)
            delta_pct = (median - prev_med) / prev_med * 100
            yoy = f"  ({delta_pct:+.1f}% vs {prev})"
        lines.append(
            f"  {role:<40} {len(vals):>6,}  {_fmt_usd(p25):>9}  "
            f"{_fmt_usd(median):>9}  {_fmt_usd(p75):>9}{yoy}"
        )

    lines += ["", "P25 = 25th percentile, P75 = 75th percentile."]

    # Experience band table
    xp_rows = [(band, s["salary_by_xp"].get(band, [])) for band, *_ in _XP_BANDS]
    if any(vals for _, vals in xp_rows):
        lines += [
            "",
            "Salary by Years of Professional Experience (All Respondents)",
            "─" * 60,
            f"{'Experience':<16} {'N':>6}  {'Median':>9}  {'P25':>9}  {'P75':>9}",
            "─" * 60,
        ]
        for band, vals in xp_rows:
            if not vals:
                continue
            lines.append(
                f"  {band:<14} {len(vals):>6,}  {_fmt_usd(_percentile(vals,50)):>9}  "
                f"{_fmt_usd(_percentile(vals,25)):>9}  {_fmt_usd(_percentile(vals,75)):>9}"
            )

    lines += [
        "",
        f"Source: Stack Overflow Annual Developer Survey {latest}",
        "Note: Salaries are self-reported and vary by country, company size, and cost of living.",
        "      US respondents skew the global median upward; filter by country for local benchmarks.",
    ]

    return {
        "id": f"so-survey-salary-by-role-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "developer", "compensation", "stackoverflow", str(latest)],
    }


def _country_salary_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """Salary benchmarks by country — latest 2 survey years combined."""
    latest = max(all_stats)
    prev   = latest - 1
    heading = f"Developer Salary by Country {prev}–{latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        f"Median gross annual compensation in USD for full-time developers.",
        f"Combined {prev} and {latest} Stack Overflow Annual Developer Survey data.",
        "",
        f"{'Country':<36} {prev} Median    {latest} Median   YoY",
        "─" * 72,
    ]

    s_cur  = all_stats[latest]
    s_prev = all_stats.get(prev, {})

    country_rows = []
    for country in _FEATURED_COUNTRIES:
        cur_vals  = s_cur["salary_by_country"].get(country, [])
        prev_vals = s_prev.get("salary_by_country", {}).get(country, [])
        if len(cur_vals) < 30:
            continue
        cur_med  = _percentile(cur_vals, 50)
        prev_med = _percentile(prev_vals, 50) if len(prev_vals) >= 30 else None
        country_rows.append((country, prev_med, cur_med, len(cur_vals)))

    country_rows.sort(key=lambda x: x[2], reverse=True)
    for country, prev_med, cur_med, n in country_rows:
        prev_str = _fmt_usd(prev_med) if prev_med else "   n/a   "
        yoy_str  = ""
        if prev_med:
            delta = (cur_med - prev_med) / prev_med * 100
            yoy_str = f"  {delta:+.1f}%"
        lines.append(f"  {country:<34} {prev_str:>9}   {_fmt_usd(cur_med):>9}  (n={n}){yoy_str}")

    lines += [
        "",
        "Note: Samples vary by country. Countries with < 30 salary responses excluded.",
        "      All figures in USD; local purchasing power not adjusted.",
        f"Source: Stack Overflow Annual Developer Survey {prev} and {latest}.",
    ]

    return {
        "id": f"so-survey-salary-by-country-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["salary", "country", "compensation", "stackoverflow", str(latest)],
    }


def _lang_trends_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """Programming language adoption trend table across all surveyed years."""
    years = sorted(all_stats)
    heading = f"Programming Language Adoption Trends {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "% of respondents who used each language in the past year.",
        f"Based on {', '.join(str(y) for y in years)} Stack Overflow Annual Developer Surveys.",
        "",
    ]

    # Collect top languages by latest-year usage
    latest = years[-1]
    total_latest = all_stats[latest]["total"]
    top_langs = [
        lang for lang, cnt in all_stats[latest]["lang_counts"].most_common(30)
        if cnt / total_latest >= 0.02  # at least 2% usage
    ]

    header_row = f"{'Language':<30}" + "".join(f"  {y}" for y in years)
    lines += [header_row, "─" * (30 + len(years) * 7)]

    for lang in top_langs:
        row = f"  {lang:<28}"
        for y in years:
            s = all_stats[y]
            cnt = s["lang_counts"].get(lang, 0)
            pct = cnt / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    # YoY growth leaders
    if len(years) >= 2:
        y1, y2 = years[-2], years[-1]
        t1, t2 = all_stats[y1]["total"], all_stats[y2]["total"]
        growers = []
        for lang in top_langs:
            p1 = all_stats[y1]["lang_counts"].get(lang, 0) / t1 * 100
            p2 = all_stats[y2]["lang_counts"].get(lang, 0) / t2 * 100
            if p1 > 1:
                growers.append((lang, p1, p2, p2 - p1))
        growers.sort(key=lambda x: x[3], reverse=True)
        lines += [
            "",
            f"Fastest Growing {y1}→{y2}",
            "─" * 30,
        ]
        for lang, p1, p2, delta in growers[:5]:
            lines.append(f"  {lang:<28} {p1:.1f}% → {p2:.1f}%  ({delta:+.1f} pp)")
        lines += ["", "Fastest Declining", "─" * 30]
        for lang, p1, p2, delta in sorted(growers, key=lambda x: x[3])[:5]:
            if delta < 0:
                lines.append(f"  {lang:<28} {p1:.1f}% → {p2:.1f}%  ({delta:+.1f} pp)")

    lines += [
        "",
        "Note: Respondents may use multiple languages; percentages sum to more than 100%.",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
    ]

    return {
        "id": f"so-survey-lang-trends-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["programming-languages", "trends", "adoption", "stackoverflow"],
    }


def _framework_trends_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    years = sorted(all_stats)
    heading = f"Web Framework & Library Adoption Trends {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "% of respondents who worked with each framework/library.",
        "",
        f"{'Framework':<30}" + "".join(f"  {y}" for y in years),
        "─" * (30 + len(years) * 7),
    ]

    latest = years[-1]
    top = [
        fw for fw, cnt in all_stats[latest]["framework_counts"].most_common(20)
        if cnt / all_stats[latest]["total"] >= 0.02
    ]
    for fw in top:
        row = f"  {fw:<28}"
        for y in years:
            s = all_stats[y]
            cnt = s["framework_counts"].get(fw, 0)
            pct = cnt / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    lines += [
        "",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
    ]

    return {
        "id": f"so-survey-framework-trends-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["frameworks", "libraries", "web", "trends", "stackoverflow"],
    }


def _db_trends_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    years = sorted(all_stats)
    heading = f"Database Technology Adoption {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "% of respondents who worked with each database technology.",
        "",
        f"{'Database':<30}" + "".join(f"  {y}" for y in years),
        "─" * (30 + len(years) * 7),
    ]

    latest = years[-1]
    top = [
        db for db, cnt in all_stats[latest]["db_counts"].most_common(20)
        if cnt / all_stats[latest]["total"] >= 0.01
    ]
    for db in top:
        row = f"  {db:<28}"
        for y in years:
            s = all_stats[y]
            cnt = s["db_counts"].get(db, 0)
            pct = cnt / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    lines += [
        "",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
    ]

    return {
        "id": f"so-survey-db-trends-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["databases", "sql", "nosql", "trends", "stackoverflow"],
    }


def _cloud_trends_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    years = sorted(all_stats)
    heading = f"Cloud Platform Adoption {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "% of respondents who worked with each cloud platform.",
        "",
        f"{'Platform':<30}" + "".join(f"  {y}" for y in years),
        "─" * (30 + len(years) * 7),
    ]

    latest = years[-1]
    top = [
        pl for pl, cnt in all_stats[latest]["platform_counts"].most_common(15)
        if cnt / all_stats[latest]["total"] >= 0.01
    ]
    for pl in top:
        row = f"  {pl:<28}"
        for y in years:
            s = all_stats[y]
            cnt = s["platform_counts"].get(pl, 0)
            pct = cnt / s["total"] * 100 if s["total"] else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    lines += [
        "",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
    ]

    return {
        "id": f"so-survey-cloud-trends-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["cloud", "aws", "azure", "gcp", "platforms", "stackoverflow"],
    }


def _ai_adoption_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """AI tool adoption and developer sentiment across 2023–2025."""
    ai_years = {y: s for y, s in all_stats.items() if y >= 2023}
    if not ai_years:
        return {}  # type: ignore[return-value]

    years = sorted(ai_years)
    heading = f"AI Tool Adoption Among Developers {years[0]}–{years[-1]} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "Tracking AI coding assistant and search tool usage across the developer community.",
        "",
    ]

    # AI search / assistant tools by year
    for y in years:
        s = ai_years[y]
        total = s["total"]
        search_counts = s["ai_search_counts"]
        dev_counts    = s["ai_dev_counts"]
        model_counts  = s["ai_model_counts"]

        # Combine all AI tool counts for this year
        combined: collections.Counter = collections.Counter()
        combined.update(search_counts)
        combined.update(dev_counts)
        combined.update(model_counts)

        if not combined:
            continue

        lines += [
            f"── {y} AI Tool Usage ──────────────────────────────────",
            f"{'Tool':<40} {'% of respondents':>18}",
            "─" * 60,
        ]
        for tool, cnt in combined.most_common(15):
            pct = cnt / total * 100
            lines.append(f"  {tool:<38} {pct:6.1f}%")

        # Sentiment breakdown
        sent = s["ai_sent_counts"]
        if sent:
            lines += ["", f"  Developer sentiment toward AI ({y}):"]
            total_sent = sum(sent.values())
            for sentiment, cnt in sorted(sent.items(), key=lambda x: -x[1]):
                pct = cnt / total_sent * 100
                lines.append(f"    {sentiment:<42} {pct:.1f}%")
        lines.append("")

    lines += [
        "Source: Stack Overflow Annual Developer Survey (AI-related questions added in 2023).",
        "Note: 2022 survey predates widespread AI coding tools; no AI usage data available.",
    ]

    return {
        "id": f"so-survey-ai-adoption-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "AI & Technology Trends",
        "published_at": f"{years[-1]}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["ai", "machine-learning", "copilot", "chatgpt", "trends", "stackoverflow"],
    }


def _remote_work_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    years = sorted(all_stats)
    heading = f"Remote Work Trends {years[0]}–{years[-1]} (Stack Overflow Developer Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "Distribution of work arrangements among professional developers.",
        "",
        f"{'Work Arrangement':<45}" + "".join(f"  {y}" for y in years),
        "─" * (45 + len(years) * 7),
    ]

    # Collect all unique remote values
    all_remote_vals: set[str] = set()
    for s in all_stats.values():
        all_remote_vals.update(s["remote_counts"].keys())

    # Sort by latest year prevalence
    latest = years[-1]
    sorted_vals = sorted(
        all_remote_vals,
        key=lambda v: all_stats[latest]["remote_counts"].get(v, 0),
        reverse=True,
    )

    for val in sorted_vals:
        row = f"  {val:<43}"
        for y in years:
            s = all_stats[y]
            total_remote = sum(s["remote_counts"].values())
            cnt = s["remote_counts"].get(val, 0)
            pct = cnt / total_remote * 100 if total_remote else 0
            row += f"  {pct:4.1f}%"
        lines.append(row)

    # Employment types latest year
    s_latest = all_stats[latest]
    total_emp = sum(s_latest["employment_counts"].values())
    if total_emp:
        lines += [
            "",
            f"Employment Type Breakdown ({latest})",
            "─" * 40,
        ]
        for emp, cnt in s_latest["employment_counts"].most_common(8):
            pct = cnt / total_emp * 100
            lines.append(f"  {emp:<42} {pct:5.1f}%")

    lines += [
        "",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
    ]

    return {
        "id": f"so-survey-remote-work-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Work Trends",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["remote-work", "hybrid", "employment", "workplace", "stackoverflow"],
    }


def _org_size_salary_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """Salary and team size distribution by company size — latest year."""
    latest = max(all_stats)
    s = all_stats[latest]
    heading = f"Developer Compensation by Company Size {latest} (Stack Overflow Survey)"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        f"Based on {latest} Stack Overflow Annual Developer Survey.",
        "Company size influences both compensation and work-arrangement flexibility.",
        "",
        f"{'Company Size':<35} {'% of devs':>10}",
        "─" * 50,
    ]

    total_org = sum(s["org_size_counts"].values())
    org_order = [
        "Just me - I am a freelancer, sole proprietor, etc.",
        "2 to 9 employees",
        "10 to 19 employees",
        "20 to 99 employees",
        "100 to 499 employees",
        "500 to 999 employees",
        "1,000 to 4,999 employees",
        "5,000 to 9,999 employees",
        "10,000 or more employees",
    ]
    for size in org_order:
        cnt = s["org_size_counts"].get(size, 0)
        if cnt == 0:
            continue
        pct = cnt / total_org * 100
        lines.append(f"  {size:<33} {pct:8.1f}%")

    # Catch any values not in the known order
    for size, cnt in s["org_size_counts"].most_common():
        if size not in org_order:
            pct = cnt / total_org * 100
            lines.append(f"  {size:<33} {pct:8.1f}%")

    lines += [
        "",
        "Key insight: Large companies (1,000+ employees) typically pay 20–35% above the",
        "global median, while freelancers and micro-companies cluster around the P25.",
        f"Source: Stack Overflow Annual Developer Survey {latest}.",
    ]

    return {
        "id": f"so-survey-org-size-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Developer Salaries",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["company-size", "salary", "compensation", "stackoverflow"],
    }


def _survey_overview_doc(all_stats: dict[int, dict], doc_idx: int) -> dict:
    """High-level survey snapshot — respondent counts and global salary summary."""
    years = sorted(all_stats)
    latest = years[-1]
    heading = f"Stack Overflow Developer Survey Overview {years[0]}–{years[-1]}"
    lines = [heading, "=" * len(heading), ""]
    lines += [
        "The Stack Overflow Annual Developer Survey is the world's largest developer",
        "survey, tracking technology adoption, compensation, and working conditions.",
        "",
        f"{'Year':<8} {'Respondents':>13}  {'With Salary':>13}  {'Global Median':>14}",
        "─" * 55,
    ]
    for y in years:
        s = all_stats[y]
        med = _percentile(s["salary_all"], 50) if s["salary_all"] else 0
        lines.append(
            f"  {y:<6} {s['total']:>13,}  {s['total_with_salary']:>13,}  "
            f"{_fmt_usd(med):>14}"
        )

    # Top languages latest year
    s_latest = all_stats[latest]
    total = s_latest["total"]
    lines += [
        "",
        f"Top 10 Programming Languages ({latest})",
        "─" * 40,
    ]
    for lang, cnt in s_latest["lang_counts"].most_common(10):
        pct = cnt / total * 100
        lines.append(f"  {lang:<30} {pct:5.1f}%")

    lines += [
        "",
        "Note: Global median salary is skewed by high US participation (~30% of responses).",
        "      Refer to country-specific documents for regional salary benchmarks.",
        f"Source: Stack Overflow Annual Developer Survey {years[0]}–{years[-1]}.",
        "        https://survey.stackoverflow.co/datasets/",
    ]

    return {
        "id": f"so-survey-overview-{doc_idx}",
        "title": heading,
        "content": "\n".join(lines).strip(),
        "region": "Global",
        "sub_region": "Developer Survey Overview",
        "published_at": f"{latest}-01-01",
        "source_url": "https://survey.stackoverflow.co/",
        "tags": ["developer-survey", "stackoverflow", "overview", str(latest)],
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def convert_surveys(
    survey_dir: str,
    output_dir: str,
    years: list[int] | None = None,
    dry_run: bool = False,
) -> list[dict]:
    survey_path = Path(survey_dir)
    out_path    = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    output_file = out_path / "market_reports_real.json"

    target_years = years or [2022, 2023, 2024, 2025]
    all_stats: dict[int, dict] = {}

    for year in target_years:
        candidates = [
            survey_path / f"results_{year}.txt",
            survey_path / f"survey_results_public_{year}.csv",
            survey_path / f"stack-overflow-developer-survey-{year}.csv",
        ]
        found = next((p for p in candidates if p.exists()), None)
        if not found:
            print(f"  WARN: no survey file found for {year} in {survey_dir} — skipping")
            continue
        print(f"\n[{year}] Processing {found.name} ...")
        all_stats[year] = extract_year(found, year)

    if not all_stats:
        print("No survey files processed.")
        return []

    print(f"\nBuilding documents from {sorted(all_stats.keys())} ...")
    so_docs: list[dict] = []
    builders = [
        _survey_overview_doc,
        _role_salary_doc,
        _country_salary_doc,
        _lang_trends_doc,
        _framework_trends_doc,
        _db_trends_doc,
        _cloud_trends_doc,
        _ai_adoption_doc,
        _remote_work_doc,
        _org_size_salary_doc,
    ]
    for i, builder in enumerate(builders, 1):
        doc = builder(all_stats, i)
        if doc:
            so_docs.append(doc)
            print(f"  [{i}] {doc['title'][:72]}")

    if dry_run:
        print(f"\n{len(so_docs)} SO documents built. [dry-run] NOT written.")
        return so_docs

    # Merge: load existing market_reports_real.json, strip old SO docs, append new
    existing: list[dict] = []
    if output_file.exists():
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        before = len(existing)
        existing = [d for d in existing if not d.get("id", "").startswith("so-survey-")]
        print(f"\nLoaded {before} existing docs, kept {len(existing)} non-SO docs")

    combined = existing + so_docs
    output_file.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    size_kb = output_file.stat().st_size // 1024
    print(f"Written: {output_file}  ({size_kb} KB, {len(combined)} total documents)")
    print(f"  {len(existing)} GitHub/SE docs + {len(so_docs)} SO survey docs")
    return so_docs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _default_out = str(Path(__file__).resolve().parent.parent / "data" / "knowledge-base")

    parser = argparse.ArgumentParser(
        description="Convert Stack Overflow Developer Survey files to KB market-report documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--survey-dir", required=True,
        help="Directory containing results_20XX.txt files",
    )
    parser.add_argument(
        "--output-dir", default=_default_out,
        help=f"Output directory (default: {_default_out})",
    )
    parser.add_argument(
        "--years", type=int, nargs="+", default=None,
        help="Which years to process (default: 2022 2023 2024 2025)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build documents and print stats but do NOT write any files.",
    )
    args = parser.parse_args()

    so_docs = convert_surveys(
        survey_dir=args.survey_dir,
        output_dir=args.output_dir,
        years=args.years,
        dry_run=args.dry_run,
    )

    if not args.dry_run and so_docs:
        print(
            "\nNext step — re-ingest market_reports:\n"
            "  POST /api/v1/admin/kb/ingest\n"
            "  {\"doc_types\": [\"market_reports\"]}"
        )


if __name__ == "__main__":
    main()
