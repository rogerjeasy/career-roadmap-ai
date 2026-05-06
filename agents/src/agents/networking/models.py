"""Networking & Outreach domain models — pure data, no I/O, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class EventType(str, Enum):
    CONFERENCE = "conference"
    MEETUP = "meetup"
    ONLINE_COMMUNITY = "online_community"
    WEBINAR = "webinar"
    NEWSLETTER = "newsletter"
    FORUM = "forum"
    HACKATHON = "hackathon"


class RecipientType(str, Enum):
    MENTOR = "mentor"
    PEER = "peer"
    HIRING_MANAGER = "hiring_manager"
    COMMUNITY_LEADER = "community_leader"
    OPEN_SOURCE_MAINTAINER = "open_source_maintainer"


class OutreachTone(str, Enum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    CONCISE = "concise"


class ConnectionStatus(str, Enum):
    IDENTIFIED = "identified"
    REACHED_OUT = "reached_out"
    REPLIED = "replied"
    CONNECTED = "connected"
    MENTOR = "mentor"


@dataclass(frozen=True)
class LinkedInProfileScore:
    """Structured score and actionable feedback for a LinkedIn profile."""

    headline_score: float           # 0-1 quality of the headline
    summary_score: float            # 0-1 quality of the about/summary section
    experience_score: float         # 0-1 impact of experience descriptions
    skills_score: float             # 0-1 completeness and relevance of skills section
    overall_score: float            # 0-1 weighted composite score
    ats_score: float                # 0-1 estimated ATS match for target role
    strengths: list[str]            # 2-4 specific positive observations
    improvements: list[str]         # 3-6 concrete, actionable changes
    recommended_keywords: list[str] # 5-10 ATS keywords to add for target role


@dataclass(frozen=True)
class CommunityEvent:
    """A single event or online community relevant to the user's career."""

    event_id: str
    title: str
    event_type: EventType
    platform: str               # Meetup.com, LinkedIn Events, Discord, Slack, etc.
    skill_tags: list[str]       # normalised lowercase skill keywords
    relevance_score: float      # 0-1 relevance to target role + skills
    description: str
    url: str | None = None
    date: str | None = None     # ISO date string or human-readable
    location: str | None = None
    is_online: bool = True
    source: str = "mcp_industry_news"


@dataclass(frozen=True)
class OutreachDraft:
    """A single outreach message draft for a specific recipient type."""

    draft_id: str
    recipient_type: RecipientType
    subject: str                    # LinkedIn message title or email subject
    body: str                       # 3-5 sentence message body
    tone: OutreachTone
    platform: str                   # LinkedIn | Email | Discord/Slack
    target_skill: str               # The skill gap this outreach aims to address
    call_to_action: str             # Specific ask (one item, not vague)
    estimated_response_rate: str    # "high" | "medium" | "low"


@dataclass(frozen=True)
class RelationshipContact:
    """A potential contact in the relationship pipeline."""

    contact_id: str
    role: str                        # Descriptive role label
    recipient_type: RecipientType
    connection_status: ConnectionStatus
    target_skill: str                # Skill gap this contact can help with
    source: str                      # "linkedin", "github", "event", "community"
    name: str | None = None
    company: str | None = None
    notes: str = ""


@dataclass
class RelationshipPipeline:
    """Complete relationship pipeline for the user's networking strategy."""

    total_contacts: int
    by_status: dict[str, int]            # ConnectionStatus.value -> count
    contacts: list[RelationshipContact]
    next_actions: list[str]              # Prioritised actionable next steps
    outreach_priority_skills: list[str]  # Skills to target first (from gap ranking)


@dataclass
class NetworkingResult:
    """Full output produced by the Networking & Outreach pipeline."""

    target_role: str
    linkedin_review: LinkedInProfileScore | None = None
    events_and_communities: list[CommunityEvent] = field(default_factory=list)
    outreach_drafts: list[OutreachDraft] = field(default_factory=list)
    relationship_pipeline: RelationshipPipeline | None = None
    data_sources: list[str] = field(default_factory=list)
    processing_steps: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
