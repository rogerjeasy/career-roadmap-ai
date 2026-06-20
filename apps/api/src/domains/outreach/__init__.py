"""AI Outreach Drafting domain (§ human-approval gate).

Drafts personalised outreach messages (cold intro, referral ask, follow-up) with
the LLM, grounded in the user's real profile. Every draft sits behind a human
approval gate: the platform never sends on its own — a draft must be reviewed,
edited, explicitly approved, and only then marked as sent by the user. This
mirrors the project's rule that write/outreach actions require human confirmation.
"""
