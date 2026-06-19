"""Accountability Cohorts domain (§14.12).

Small peer groups pursuing similar career goals who keep each other accountable
through lightweight weekly check-ins. A user can spin up a cohort, discover open
cohorts ranked by how well their focus matches the user's own target role/goals
(a real signal pulled from the session profile — never a random assignment), join
or leave, and post / read check-ins on a shared dashboard.

Access is membership-based rather than single-owner: the generic owner-scoped
CRUD base does not fit a shared resource, so this domain ships a dedicated
repository whose reads are gated on cohort membership.
"""
