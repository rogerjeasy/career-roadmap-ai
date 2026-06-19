"""Negotiation & Offer Coach domain (§14.14).

Helps a user evaluate and improve a job offer. Given the offer details (plus the
user's real profile/location from the session for grounding), an LLM benchmarks
the package against the market, drafts a concrete counter with rationale, and
surfaces talking points and risks. A separate roleplay endpoint lets the user
rehearse the conversation against an LLM playing the recruiter, with private
coaching after each turn.

Per the platform's Responsible-AI rules, the coach exposes its confidence and
assumptions rather than presenting benchmarks as certainties, and never infers
protected attributes.
"""
