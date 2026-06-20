"""Privacy domain — data export + complete account deletion (Responsible AI).

Gives users real control over their data, as the platform's privacy rules
require. ``export`` gathers every owner-scoped record into one downloadable
bundle. ``delete_account`` purges that same data across all feature collections
*and then* removes the Firebase Auth user — closing the gap left by the profile-
only deletion, which previously orphaned per-user feature data.

Only collections that store a ``user_id`` field (the generic CRUD-backed ones)
are handled generically; shared/multi-party resources (e.g. cohorts, mentor
sessions) are intentionally excluded so one member can't delete another's data.
"""
