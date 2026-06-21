"""Admin domain — platform administration surface (role-gated).

Aggregates real data from the existing Firestore collections (users, roadmaps,
feedback, contact_requests, newsletter_prefs, notifications) and exposes the
operations an administrator needs: a platform overview, a user directory with
role/status controls, a feedback & contact inbox, newsletter subscribers, a
broadcast tool, an audit trail and a system health view. Authorization is
enforced upstream by ``require_admin`` (Firebase custom claim).
"""
