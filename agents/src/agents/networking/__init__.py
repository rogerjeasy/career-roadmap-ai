"""Networking & Outreach Agent package.

Public API surface — import only what callers need:

    from agents.networking import NetworkingAgent
    from agents.networking.models import (
        LinkedInProfileScore,
        CommunityEvent,
        OutreachDraft,
        RelationshipPipeline,
    )
"""
from agents.networking.networking_agent import NetworkingAgent

__all__ = ["NetworkingAgent"]
