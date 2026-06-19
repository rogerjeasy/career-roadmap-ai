"""Verifiable Skill Credentials domain (§14.8).

Lets a user mint a signed, shareable credential that attests to a skill at a
stated level and embeds snapshots of the real evidence (from the Evidence Vault)
that backs the claim. Each credential carries an HMAC signature over its
canonical payload and a public share token, so anyone holding the link can
verify — without authenticating — that the platform issued it, that it has not
been tampered with, and whether it is still active or has been revoked.

The platform never invents accomplishments: a credential can only reference
evidence the user actually owns, and the verifier always re-derives the
signature from the stored facts rather than trusting a cached flag.
"""
