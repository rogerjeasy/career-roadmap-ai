"""Wellness & Sustainability Monitor domain (§14.15).

Career growth is a multi-year effort; this module guards the pace. The user logs
lightweight wellness check-ins (energy, stress, hours worked, sleep, motivation),
and a deterministic engine reads the recent trend to estimate burnout risk, name
the specific drivers, and recommend a recovery week before momentum collapses.

Scoring is transparent and computed only from the user's own check-ins — no
hidden model, no inference of health conditions or any protected attribute.
"""
