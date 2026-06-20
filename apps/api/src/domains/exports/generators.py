"""Exports — pure Markdown / iCalendar generators for a roadmap.

No external dependencies: ``.ics`` is assembled by hand to RFC 5545 essentials
(VCALENDAR/VEVENT, CRLF line endings, escaped text), which every major calendar
client accepts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.domains.roadmap.schemas import RoadmapDocument


def roadmap_to_markdown(doc: RoadmapDocument) -> str:
    lines: list[str] = ["# Career Roadmap", ""]
    if doc.summary:
        lines += [doc.summary, ""]
    for phase in sorted(doc.phases, key=lambda p: p.order):
        lines.append(f"## Phase {phase.order}: {phase.title}")
        if phase.duration_weeks:
            lines.append(f"_Duration: {phase.duration_weeks} weeks_")
        if phase.description:
            lines += ["", phase.description]
        if phase.goals:
            lines += ["", "**Goals**"]
            lines += [f"- {g}" for g in phase.goals]
        if phase.milestones:
            lines += ["", "**Milestones**"]
            lines += [f"- [ ] {m}" for m in phase.milestones]
        if phase.skills_to_gain:
            lines += ["", "**Skills to gain:** " + ", ".join(phase.skills_to_gain)]
        lines.append("")
    if doc.weekly_habits:
        lines += ["## Weekly habits", ""]
        lines += [f"- {h.text}" for h in doc.weekly_habits]
        lines.append("")
    if doc.next_steps:
        lines += ["## Next steps", ""]
        lines += [f"1. {s.action}" for s in sorted(doc.next_steps, key=lambda s: s.order)]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets (approximated on characters)."""
    if len(line) <= 75:
        return line
    out = [line[:75]]
    rest = line[75:]
    while rest:
        out.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(out)


def roadmap_to_ics(doc: RoadmapDocument, start: date | None = None) -> str:
    start = start or date.today()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Career Roadmap AI//Roadmap Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    cursor = start
    for phase in sorted(doc.phases, key=lambda p: p.order):
        weeks = max(1, phase.duration_weeks or 1)
        end = cursor + timedelta(weeks=weeks)
        desc_parts = [phase.description] if phase.description else []
        if phase.milestones:
            desc_parts.append("Milestones: " + "; ".join(phase.milestones))
        description = _ics_escape(" \n".join(p for p in desc_parts if p))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{phase.id}@careerroadmap.ai",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{cursor.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_ics_escape(f'Phase {phase.order}: {phase.title}')}"),
            _fold(f"DESCRIPTION:{description}") if description else "DESCRIPTION:",
            "END:VEVENT",
        ]
        cursor = end
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
