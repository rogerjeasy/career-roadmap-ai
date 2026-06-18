"""Autopilot domain — surfaces adaptation proposals (the 'nudge layer').

Computes consent-gated plan-adjustment proposals from real user signals
(weekly-review staleness, habit consistency, market drift, missing roadmap) and
lets the user accept or dismiss each one. Autopilot never changes the plan on
its own — it only proposes.
"""
