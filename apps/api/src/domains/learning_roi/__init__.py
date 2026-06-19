"""Learning ROI Tracker domain (§14.11).

Lets a user log the courses, books, and certifications they are investing time
and money in, then ranks them by *expected career impact per unit of effort*.

Scoring is deliberately deterministic and grounded in the user's real signals —
the in-demand / gap skills derived from their market snapshot and target role —
rather than an opaque LLM guess, so every ranking ships with a plain-language
rationale the user can interrogate. Items whose skills align with what their
target market actually rewards rise to the top; expensive, time-heavy items with
weak alignment sink.
"""
