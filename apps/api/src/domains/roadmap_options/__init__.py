"""Roadmap Strategy Options domain (§9).

Before committing to a single generated roadmap, a user should be able to choose
the *shape* of the journey. This module produces three distinct, comparable
strategies from the user's real profile — Aggressive, Balanced, and Long-term —
each with its own timeline, weekly intensity, phase outline, and honest
trade-offs. Selecting one records the preference on the session profile
(``preferred_strategy``) so the downstream agent pipeline can pace generation
accordingly, without this module having to re-run that pipeline itself.
"""
