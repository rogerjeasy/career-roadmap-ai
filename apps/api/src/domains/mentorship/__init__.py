"""Mentor & Peer Matching / Insider Conversations domain (§14.13).

Three intertwined concerns:
  • Mentor profiles — a member opts in as a mentor with their expertise areas.
  • Matching & sessions — a mentee discovers mentors ranked by how well their
    expertise overlaps the mentee's target role/skills (a real session signal),
    then requests a session. Requests sit behind a human-approval gate: the
    mentor must accept before anything is confirmed (CLAUDE.md §9).
  • Insider conversations — a member-contributed case-study library of real
    role transitions (from-role → to-role, the steps taken, lessons learned),
    browsable by everyone. Authors may publish anonymously. No fabricated
    stories: the library only contains what members actually contribute.
"""
