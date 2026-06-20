"""Webhooks domain (§21 — public platform).

Lets a user register HTTPS endpoints to be notified when events happen on their
account (e.g. an application's status changes, a credential is issued). Each
delivery is a POST signed with the webhook's secret (HMAC-SHA256 over the body,
in an ``X-CRA-Signature`` header) so the receiver can verify authenticity. The
``dispatch`` helper is the reuse point event sources call; a ``ping`` endpoint
lets the user test their endpoint immediately.
"""
