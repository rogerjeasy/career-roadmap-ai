"""Plan Version Snapshots / Undo domain (§11.2, §11.4).

Captures point-in-time copies of a roadmap so a user can experiment freely and
roll back. Restoring a snapshot first auto-captures the *current* state (so the
restore itself is undoable), then overwrites the live roadmap in place — clearing
any stale phases/habits the snapshot predates. Snapshots are full, self-contained
copies of the roadmap document, owner-scoped like every other user resource.
"""
