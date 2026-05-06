"""RelationshipTracker — seed the initial relationship pipeline from gaps and outreach drafts.

Pure computation: no LLM calls, no I/O. Takes the gap analysis and outreach drafts,
maps them to concrete contact records, counts pipeline stages, and produces
prioritised next actions.

The pipeline starts with every contact in IDENTIFIED status. As the user sends
outreach and gets replies, the API updates status to REACHED_OUT → REPLIED → CONNECTED.
"""
from __future__ import annotations

from uuid import uuid4

from agents.core.logging import get_logger
from agents.networking.models import (
    ConnectionStatus,
    OutreachDraft,
    RecipientType,
    RelationshipContact,
    RelationshipPipeline,
)

logger = get_logger(__name__)

_SEVERITY_TO_CONTACT_COUNT: dict[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 1,
}

_CONTACT_SOURCE_BY_RECIPIENT: dict[RecipientType, str] = {
    RecipientType.MENTOR: "linkedin",
    RecipientType.PEER: "linkedin",
    RecipientType.HIRING_MANAGER: "linkedin",
    RecipientType.COMMUNITY_LEADER: "community",
    RecipientType.OPEN_SOURCE_MAINTAINER: "github",
}


class RelationshipTracker:
    """Build the initial relationship pipeline from gap analysis and outreach drafts.

    Entirely stateless and synchronous — safe to call in any context.
    """

    def build_pipeline(
        self,
        prioritised_gaps: list[dict],
        outreach_drafts: list[OutreachDraft],
        target_role: str,
        *,
        correlation_id: str = "",
    ) -> RelationshipPipeline:
        """Build the initial pipeline seeded from drafts + top gaps.

        Each outreach draft seeds one IDENTIFIED contact.  Additional contacts
        are created for top gaps not already covered by a draft.
        """
        contacts: list[RelationshipContact] = []

        # Seed from outreach drafts — one contact per draft
        for draft in outreach_drafts:
            source = _CONTACT_SOURCE_BY_RECIPIENT.get(draft.recipient_type, "linkedin")
            contacts.append(
                RelationshipContact(
                    contact_id=str(uuid4()),
                    role=_infer_contact_role(draft.recipient_type, draft.target_skill, target_role),
                    recipient_type=draft.recipient_type,
                    connection_status=ConnectionStatus.IDENTIFIED,
                    target_skill=draft.target_skill,
                    source=source,
                    notes=f"Draft ready — subject: '{draft.subject}'",
                )
            )

        # Add extra contacts for high-priority gaps not covered by a draft
        covered_skills = {d.target_skill.lower() for d in outreach_drafts}
        for gap in prioritised_gaps[:5]:
            gap_name = str(gap.get("requirement_name", ""))
            if not gap_name or gap_name.lower() in covered_skills:
                continue
            severity = str(gap.get("severity", "medium"))
            count = _SEVERITY_TO_CONTACT_COUNT.get(severity, 1)
            for _ in range(count):
                contacts.append(
                    RelationshipContact(
                        contact_id=str(uuid4()),
                        role=f"Senior {target_role} — {gap_name} expert",
                        recipient_type=RecipientType.MENTOR,
                        connection_status=ConnectionStatus.IDENTIFIED,
                        target_skill=gap_name,
                        source="linkedin",
                        notes=f"Gap severity: {severity} — draft outreach before reaching out",
                    )
                )

        by_status = _count_by_status(contacts)
        next_actions = _generate_next_actions(contacts, prioritised_gaps, target_role)
        priority_skills = _extract_priority_skills(prioritised_gaps)

        logger.info(
            "networking.pipeline_built",
            total_contacts=len(contacts),
            priority_skills=priority_skills[:3],
            correlation_id=correlation_id,
        )

        return RelationshipPipeline(
            total_contacts=len(contacts),
            by_status=by_status,
            contacts=contacts,
            next_actions=next_actions,
            outreach_priority_skills=priority_skills,
        )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _infer_contact_role(
    recipient_type: RecipientType,
    skill: str,
    target_role: str,
) -> str:
    role_labels: dict[RecipientType, str] = {
        RecipientType.MENTOR: f"Senior {target_role} — {skill} practitioner",
        RecipientType.PEER: f"{target_role} Candidate — building {skill}",
        RecipientType.HIRING_MANAGER: f"Engineering Manager hiring {target_role}s",
        RecipientType.COMMUNITY_LEADER: f"{skill} Community Organizer",
        RecipientType.OPEN_SOURCE_MAINTAINER: f"OSS Maintainer — {skill}",
    }
    return role_labels.get(recipient_type, f"{target_role} practitioner")


def _count_by_status(contacts: list[RelationshipContact]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for contact in contacts:
        key = contact.connection_status.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _generate_next_actions(
    contacts: list[RelationshipContact],
    gaps: list[dict],
    target_role: str,
) -> list[str]:
    actions: list[str] = []

    identified = [c for c in contacts if c.connection_status == ConnectionStatus.IDENTIFIED]
    if identified:
        actions.append(
            f"Send personalised outreach to {len(identified)} identified contact(s) "
            "using the prepared drafts — customise [THEIR_PROJECT] before sending"
        )

    top_gap = gaps[0].get("requirement_name") if gaps else None
    if top_gap:
        actions.append(
            f"Search LinkedIn for '{top_gap}' practitioners in your target companies "
            "and save 3-5 profiles before reaching out"
        )

    actions.append(
        "Update your LinkedIn profile based on the review suggestions "
        "before launching outreach — first impressions matter"
    )
    actions.append(
        "Join 1-2 relevant online communities from the events list "
        "and introduce yourself this week"
    )
    actions.append(
        f"Set a weekly 30-minute networking block in your calendar "
        f"specifically for {target_role} community engagement"
    )

    return actions


def _extract_priority_skills(gaps: list[dict]) -> list[str]:
    return [
        str(g.get("requirement_name", ""))
        for g in gaps
        if g.get("requirement_name")
    ]
