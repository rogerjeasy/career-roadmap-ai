"""Public API Keys domain (§21 — public API).

A first concrete slice of the §21 platform vision: let users mint personal API
keys and read their own data programmatically. Keys are shown in full exactly
once at creation; only a SHA-256 hash (plus a display prefix and last-4) is
stored, so a leaked database never exposes usable keys. A presented key is
authenticated by hashing it and looking up the hash, which also stamps
``last_used_at`` for auditability.
"""
