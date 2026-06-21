"""Grant or revoke an admin role for a user (Firebase custom claims).

Roles live in a Firebase Auth custom claim (``role``) so they are signed into
the user's ID token and verified on every request without a DB round-trip. This
script is the bootstrap path for designating the very first administrator, and
a break-glass tool thereafter. It also mirrors the role onto the Firestore user
document so the admin user directory can list/filter by role.

Usage (from apps/api/, with the API's .env populated):

    poetry run python -m scripts.set_admin_role --email someone@example.com --role admin
    poetry run python -m scripts.set_admin_role --uid <firebase_uid> --role superadmin
    poetry run python -m scripts.set_admin_role --email someone@example.com --role user   # revoke

After the claim changes, the user must obtain a fresh ID token (sign out/in, or
the app force-refreshes within ~1 hour) for the new role to take effect.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import auth as firebase_auth

from src.core.auth import _VALID_ROLES, init_firebase_app
from src.db.firestore import get_firestore_client


def _resolve_uid(*, email: str | None, uid: str | None) -> str:
    if uid:
        return uid
    if not email:
        raise SystemExit("Provide either --uid or --email.")
    try:
        record = firebase_auth.get_user_by_email(email)
    except firebase_auth.UserNotFoundError as exc:  # pragma: no cover - CLI path
        raise SystemExit(f"No Firebase user found for email {email!r}.") from exc
    return record.uid


def main() -> int:
    parser = argparse.ArgumentParser(description="Set a user's admin role via Firebase custom claims.")
    parser.add_argument("--email", help="Email of the target user (looked up in Firebase Auth).")
    parser.add_argument("--uid", help="Firebase UID of the target user.")
    parser.add_argument(
        "--role",
        required=True,
        choices=_VALID_ROLES,
        help="Role to assign. Use 'user' to revoke admin access.",
    )
    args = parser.parse_args()

    init_firebase_app()
    uid = _resolve_uid(email=args.email, uid=args.uid)

    # Merge so we never clobber unrelated custom claims the app may rely on.
    record = firebase_auth.get_user(uid)
    claims = dict(record.custom_claims or {})
    if args.role == "user":
        claims.pop("role", None)
    else:
        claims["role"] = args.role
    firebase_auth.set_custom_user_claims(uid, claims or None)
    # Revoke existing refresh tokens so a stale token can't keep elevated access
    # (or, on a grant, so the new claim is picked up sooner).
    firebase_auth.revoke_refresh_tokens(uid)

    # Mirror onto the Firestore profile (best-effort; authz uses the claim).
    async def _mirror() -> None:
        db = get_firestore_client()
        await db.collection("users").document(uid).update(
            {"role": args.role, "updated_at": datetime.now(timezone.utc)}
        )

    try:
        asyncio.run(_mirror())
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"  (warning: could not mirror role to Firestore: {exc})", file=sys.stderr)

    print(f"OK — set role={args.role!r} for uid={uid} ({args.email or 'by uid'}).")
    print("The user must sign out/in (or wait for token refresh) for it to take effect.")
    return 0


if __name__ == "__main__":
    if not firebase_admin._apps:
        init_firebase_app()
    raise SystemExit(main())
