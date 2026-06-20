"""Web Push domain (§17 — notifications).

Stores per-device push subscriptions and sends Web Push notifications via VAPID.
The ``send_to_user`` helper is the integration point other features (daily Career
Twin check-in, cohort reminders, application follow-ups) call to nudge a user.

Sending is guarded: it only fires when VAPID keys are configured AND the optional
``pywebpush`` package is installed. Otherwise every send is a logged no-op, so the
platform runs unchanged until push is provisioned — at which point the same wired
path goes live with no code changes.
"""
