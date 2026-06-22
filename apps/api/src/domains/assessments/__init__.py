"""Skill Assessment domain — quiz/challenge engine for verified skill levels.

Turns a self-reported skill into a *measured* proficiency. The user starts an
assessment for a skill; the LLM generates a mix of multiple-choice and
short-answer questions (the answer key is stored server-side, never sent to the
client). On submit, the LLM grades the answers, produces a score, a proficiency
level, concrete strengths and *measured* gaps, and — when the score clears the
pass threshold — mints a verifiable credential (reusing the credentials domain)
backed by an auto-created Evidence Vault item.

Measured results are also written back into the session profile so the roadmap
pipeline can prioritise the gaps the user actually has rather than assumed ones,
strengthening the "expose uncertainty / measure don't assume" RAI principle.
"""
