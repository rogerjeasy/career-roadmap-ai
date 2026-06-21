"""Admin domain — business logic.

All reads aggregate live Firestore collections; all writes are audited. The
service is constructed per-request with the Firestore async client and the
shared Redis client (for the health probe). Firebase Auth custom claims remain
the source of truth for authorization — role/status mutations update the claim
first, then mirror to the Firestore profile so the directory stays accurate.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends
from firebase_admin import auth as firebase_auth
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter
from redis.asyncio import Redis

from src.config import settings
from src.core.auth import AuthenticatedUser
from src.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.redis import get_redis
from src.domains.admin.schemas import (
    AdminAuditItem,
    AdminContactItem,
    AdminFeedbackItem,
    AdminOverview,
    AdminUserDetail,
    AdminUserItem,
    AdminUserListResponse,
    BroadcastRequest,
    BroadcastResult,
    HealthComponent,
    NewsletterSubscriberItem,
    SystemHealth,
    TimeseriesPoint,
)
from src.domains.user.firestore_repository import FirestoreUserRepository
from src.domains.user.model import User

logger = get_logger(__name__)

_COL_USERS = "users"
_COL_ROADMAPS = "roadmaps"
_COL_FEEDBACK = "feedback"
_COL_CONTACT = "contact_requests"
_COL_NEWSLETTER = "newsletter_prefs"
_COL_NOTIFICATIONS = "notifications"
_COL_AUDIT = "admin_audit"

# Hard scan caps so a runaway collection can never blow up an admin request.
_SCAN_CAP = 20000
_OPEN_STATUSES = ("new", "in_progress")
_ADMIN_ROLES = ("admin", "superadmin")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Any) -> datetime | None:
    """Coerce a Firestore timestamp to a timezone-aware UTC datetime."""
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class AdminService:
    def __init__(self, db: AsyncClient, redis: Redis | None = None) -> None:
        self._db = db
        self._redis = redis
        self._users = FirestoreUserRepository(db)

    # ── Internal helpers ────────────────────────────────────────────────────────

    async def _scan(self, collection: str, limit: int = _SCAN_CAP) -> list[dict[str, Any]]:
        """Read up to ``limit`` documents from a collection as plain dicts."""
        out: list[dict[str, Any]] = []
        async for snap in self._db.collection(collection).limit(limit).stream():
            data = snap.to_dict() or {}
            out.append({"id": snap.id, **data})
        return out

    async def _email_map(self) -> dict[str, str]:
        """uid → email lookup for enriching inbox / subscriber rows."""
        users = await self._users.list_all()
        return {u.firebase_uid: u.email for u in users}

    async def _write_audit(
        self,
        *,
        action: str,
        actor: AuthenticatedUser,
        target_uid: str | None = None,
        target_label: str | None = None,
        detail: str = "",
    ) -> None:
        doc_id = uuid4().hex
        await self._db.collection(_COL_AUDIT).document(doc_id).set(
            {
                "action": action,
                "actor_uid": actor.uid,
                "actor_email": actor.email,
                "target_uid": target_uid,
                "target_label": target_label,
                "detail": detail,
                "created_at": _utcnow(),
            }
        )
        logger.info(
            "admin.audit",
            action=action,
            actor_uid=actor.uid,
            target_uid=target_uid,
            detail=detail,
        )

    # ── Overview ────────────────────────────────────────────────────────────────

    async def get_overview(self) -> AdminOverview:
        users = await self._users.list_all()
        roadmaps = await self._scan(_COL_ROADMAPS)
        feedback = await self._scan(_COL_FEEDBACK)
        contact = await self._scan(_COL_CONTACT)
        newsletter = await self._scan(_COL_NEWSLETTER)

        now = _utcnow()
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)

        role_breakdown: dict[str, int] = {}
        provider_breakdown: dict[str, int] = {}
        new_7d = new_30d = active = admins = verified = 0
        day_counts: dict[str, int] = {}

        for u in users:
            role_breakdown[u.role] = role_breakdown.get(u.role, 0) + 1
            provider_breakdown[u.provider] = provider_breakdown.get(u.provider, 0) + 1
            if u.is_active:
                active += 1
            if u.role in _ADMIN_ROLES:
                admins += 1
            if u.email_verified:
                verified += 1
            created = _as_utc(u.created_at)
            if created:
                if created >= cutoff_7d:
                    new_7d += 1
                if created >= cutoff_30d:
                    new_30d += 1
                key = created.date().isoformat()
                day_counts[key] = day_counts.get(key, 0) + 1

        # 14-day signup timeseries (dense — zero-filled so charts don't skip days).
        signups: list[TimeseriesPoint] = []
        for offset in range(13, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            signups.append(TimeseriesPoint(date=day, count=day_counts.get(day, 0)))

        live_roadmaps = [r for r in roadmaps if r.get("deleted_at") is None]
        roadmaps_7d = sum(
            1
            for r in live_roadmaps
            if (c := _as_utc(r.get("created_at"))) is not None and c >= cutoff_7d
        )

        open_feedback = sum(
            1 for f in feedback if f.get("status", "new") in _OPEN_STATUSES
        )
        open_contact = sum(
            1 for c in contact if c.get("status", "new") in _OPEN_STATUSES
        )
        subscribers = sum(1 for n in newsletter if n.get("subscribed"))

        recent = sorted(
            users,
            key=lambda u: _as_utc(u.created_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:8]

        return AdminOverview(
            total_users=len(users),
            active_users=active,
            admin_users=admins,
            new_users_7d=new_7d,
            new_users_30d=new_30d,
            verified_users=verified,
            total_roadmaps=len(live_roadmaps),
            roadmaps_7d=roadmaps_7d,
            total_feedback=len(feedback),
            open_feedback=open_feedback,
            total_contact_requests=len(contact),
            open_contact_requests=open_contact,
            newsletter_subscribers=subscribers,
            role_breakdown=role_breakdown,
            provider_breakdown=provider_breakdown,
            signups_last_14_days=signups,
            recent_users=[_to_item(u) for u in recent],
            generated_at=now,
        )

    # ── User directory ──────────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> AdminUserListResponse:
        users = await self._users.list_all()

        if search:
            needle = search.strip().lower()
            users = [
                u
                for u in users
                if needle in u.email.lower()
                or (u.display_name or "").lower().find(needle) >= 0
                or needle in u.firebase_uid.lower()
            ]
        if role and role != "all":
            users = [u for u in users if u.role == role]
        if status == "active":
            users = [u for u in users if u.is_active]
        elif status == "inactive":
            users = [u for u in users if not u.is_active]

        users.sort(
            key=lambda u: _as_utc(u.created_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        total = len(users)
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        start = (page - 1) * page_size
        window = users[start : start + page_size]

        return AdminUserListResponse(
            items=[_to_item(u) for u in window],
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        )

    async def get_user_detail(self, uid: str) -> AdminUserDetail:
        user = await self._users.get_by_firebase_uid(uid)
        if user is None:
            raise NotFoundError(f"User '{uid}' was not found")

        roadmap_count = 0
        last_roadmap_at: datetime | None = None
        async for snap in (
            self._db.collection(_COL_ROADMAPS)
            .where(filter=FieldFilter("user_id", "==", uid))
            .stream()
        ):
            data = snap.to_dict() or {}
            if data.get("deleted_at") is not None:
                continue
            roadmap_count += 1
            created = _as_utc(data.get("created_at"))
            if created and (last_roadmap_at is None or created > last_roadmap_at):
                last_roadmap_at = created

        feedback_count = await self._count_where(_COL_FEEDBACK, uid)
        notification_count = await self._count_where(_COL_NOTIFICATIONS, uid)

        return AdminUserDetail(
            **_to_item(user).model_dump(),
            roadmap_count=roadmap_count,
            feedback_count=feedback_count,
            notification_count=notification_count,
            last_roadmap_at=last_roadmap_at,
        )

    async def _count_where(self, collection: str, uid: str, cap: int = 5000) -> int:
        count = 0
        async for _ in (
            self._db.collection(collection)
            .where(filter=FieldFilter("user_id", "==", uid))
            .limit(cap)
            .stream()
        ):
            count += 1
        return count

    # ── Role / status / deletion ────────────────────────────────────────────────

    def _current_role(self, uid: str) -> str:
        try:
            record = firebase_auth.get_user(uid)
        except firebase_auth.UserNotFoundError as exc:
            raise NotFoundError(f"User '{uid}' was not found") from exc
        claims = record.custom_claims or {}
        role = claims.get("role", "user")
        return role if role in ("user", *_ADMIN_ROLES) else "user"

    async def update_user_role(
        self, actor: AuthenticatedUser, uid: str, new_role: str
    ) -> AdminUserDetail:
        if uid == actor.uid:
            raise ValidationError("You cannot change your own role.")

        current = self._current_role(uid)
        # Superadmin is required to grant superadmin, or to alter another admin.
        touches_privileged = (
            new_role == "superadmin"
            or current in _ADMIN_ROLES
        )
        if touches_privileged and not actor.is_superadmin:
            raise AuthorizationError(
                "Only a superadmin can assign or modify administrator roles."
            )

        record = firebase_auth.get_user(uid)
        claims = dict(record.custom_claims or {})
        if new_role == "user":
            claims.pop("role", None)
        else:
            claims["role"] = new_role
        firebase_auth.set_custom_user_claims(uid, claims or None)
        # Force the next request to mint a fresh token carrying the new claim.
        firebase_auth.revoke_refresh_tokens(uid)
        await self._users.set_role(uid, new_role)

        await self._write_audit(
            action="user.role_changed",
            actor=actor,
            target_uid=uid,
            target_label=record.email,
            detail=f"{current} → {new_role}",
        )
        return await self.get_user_detail(uid)

    async def update_user_status(
        self, actor: AuthenticatedUser, uid: str, is_active: bool
    ) -> AdminUserDetail:
        if uid == actor.uid:
            raise ValidationError("You cannot change your own account status.")
        if self._current_role(uid) in _ADMIN_ROLES and not actor.is_superadmin:
            raise AuthorizationError(
                "Only a superadmin can disable an administrator account."
            )

        firebase_auth.update_user(uid, disabled=not is_active)
        if not is_active:
            firebase_auth.revoke_refresh_tokens(uid)
        await self._users.set_active(uid, is_active)

        await self._write_audit(
            action="user.status_changed",
            actor=actor,
            target_uid=uid,
            detail="activated" if is_active else "deactivated",
        )
        return await self.get_user_detail(uid)

    async def delete_user(self, actor: AuthenticatedUser, uid: str) -> None:
        if uid == actor.uid:
            raise ValidationError("You cannot delete your own account from here.")
        if self._current_role(uid) in _ADMIN_ROLES and not actor.is_superadmin:
            raise AuthorizationError(
                "Only a superadmin can delete an administrator account."
            )

        target_email: str | None = None
        try:
            target_email = firebase_auth.get_user(uid).email
        except firebase_auth.UserNotFoundError:
            target_email = None

        await self._users.delete(uid)
        try:
            firebase_auth.revoke_refresh_tokens(uid)
            firebase_auth.delete_user(uid)
        except firebase_auth.UserNotFoundError:
            logger.warning("admin.delete_firebase_missing", uid=uid)

        await self._write_audit(
            action="user.deleted",
            actor=actor,
            target_uid=uid,
            target_label=target_email,
        )

    # ── Inbox: feedback ─────────────────────────────────────────────────────────

    async def list_feedback(
        self, *, status: str | None = None, limit: int = 200
    ) -> list[AdminFeedbackItem]:
        docs = await self._scan(_COL_FEEDBACK, limit=max(limit, _SCAN_CAP))
        emails = await self._email_map()
        items = [
            AdminFeedbackItem(
                id=d["id"],
                user_id=d.get("user_id", ""),
                user_email=emails.get(d.get("user_id", "")),
                category=d.get("category", "other"),
                subject=d.get("subject", ""),
                message=d.get("message", ""),
                rating=d.get("rating"),
                status=_norm_status(d.get("status")),
                created_at=_as_utc(d.get("created_at")) or _utcnow(),
            )
            for d in docs
        ]
        if status and status != "all":
            items = [i for i in items if i.status == status]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    async def update_feedback_status(
        self, actor: AuthenticatedUser, feedback_id: str, status: str
    ) -> AdminFeedbackItem:
        ref = self._db.collection(_COL_FEEDBACK).document(feedback_id)
        snap = await ref.get()
        if not snap.exists:
            raise NotFoundError(f"Feedback '{feedback_id}' was not found")
        await ref.update({"status": status, "updated_at": _utcnow()})
        await self._write_audit(
            action="feedback.status_changed",
            actor=actor,
            target_uid=feedback_id,
            detail=status,
        )
        data = {**(snap.to_dict() or {}), "status": status, "id": feedback_id}
        emails = await self._email_map()
        return AdminFeedbackItem(
            id=feedback_id,
            user_id=data.get("user_id", ""),
            user_email=emails.get(data.get("user_id", "")),
            category=data.get("category", "other"),
            subject=data.get("subject", ""),
            message=data.get("message", ""),
            rating=data.get("rating"),
            status=_norm_status(status),
            created_at=_as_utc(data.get("created_at")) or _utcnow(),
        )

    # ── Inbox: contact ──────────────────────────────────────────────────────────

    async def list_contact(
        self, *, status: str | None = None, limit: int = 200
    ) -> list[AdminContactItem]:
        docs = await self._scan(_COL_CONTACT, limit=max(limit, _SCAN_CAP))
        items = [
            AdminContactItem(
                id=d["id"],
                name=d.get("name", ""),
                email=d.get("email", ""),
                company=d.get("company", "") or "",
                topic=d.get("topic", "general"),
                message=d.get("message", ""),
                status=_norm_status(d.get("status")),
                created_at=_as_utc(d.get("created_at")) or _utcnow(),
            )
            for d in docs
        ]
        if status and status != "all":
            items = [i for i in items if i.status == status]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    async def update_contact_status(
        self, actor: AuthenticatedUser, contact_id: str, status: str
    ) -> AdminContactItem:
        ref = self._db.collection(_COL_CONTACT).document(contact_id)
        snap = await ref.get()
        if not snap.exists:
            raise NotFoundError(f"Contact request '{contact_id}' was not found")
        await ref.update({"status": status, "updated_at": _utcnow()})
        await self._write_audit(
            action="contact.status_changed",
            actor=actor,
            target_uid=contact_id,
            detail=status,
        )
        data = {**(snap.to_dict() or {}), "status": status}
        return AdminContactItem(
            id=contact_id,
            name=data.get("name", ""),
            email=data.get("email", ""),
            company=data.get("company", "") or "",
            topic=data.get("topic", "general"),
            message=data.get("message", ""),
            status=_norm_status(status),
            created_at=_as_utc(data.get("created_at")) or _utcnow(),
        )

    # ── Newsletter subscribers ──────────────────────────────────────────────────

    async def list_subscribers(self) -> list[NewsletterSubscriberItem]:
        docs = await self._scan(_COL_NEWSLETTER)
        emails = await self._email_map()
        users = {u.firebase_uid: u for u in await self._users.list_all()}
        items: list[NewsletterSubscriberItem] = []
        for d in docs:
            if not d.get("subscribed"):
                continue
            uid = d.get("user_id", d["id"])
            user = users.get(uid)
            items.append(
                NewsletterSubscriberItem(
                    user_id=uid,
                    email=emails.get(uid),
                    display_name=user.display_name if user else None,
                    frequency=d.get("frequency", "weekly"),
                    topics=list(d.get("topics", [])),
                    subscribed=True,
                    updated_at=_as_utc(d.get("updated_at")),
                )
            )
        items.sort(
            key=lambda i: i.updated_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items

    # ── Broadcast ───────────────────────────────────────────────────────────────

    async def broadcast(
        self, actor: AuthenticatedUser, payload: BroadcastRequest
    ) -> BroadcastResult:
        users = await self._users.list_all()
        if payload.audience == "active":
            targets = [u for u in users if u.is_active]
        elif payload.audience == "admins":
            targets = [u for u in users if u.role in _ADMIN_ROLES]
        else:
            targets = users

        if not targets:
            raise ValidationError("No recipients match the selected audience.")

        now = _utcnow()
        delivered = 0
        # Firestore batches are capped at 500 writes.
        for chunk_start in range(0, len(targets), 450):
            batch = self._db.batch()
            for u in targets[chunk_start : chunk_start + 450]:
                ref = self._db.collection(_COL_NOTIFICATIONS).document(uuid4().hex)
                batch.set(
                    ref,
                    {
                        "user_id": u.firebase_uid,
                        "title": payload.title,
                        "body": payload.body,
                        "tone": payload.tone,
                        "link": payload.link,
                        "read": False,
                        "created_at": now,
                        "updated_at": now,
                        "deleted_at": None,
                    },
                )
                delivered += 1
            await batch.commit()

        await self._write_audit(
            action="broadcast.sent",
            actor=actor,
            detail=f"{payload.audience}: '{payload.title}' → {delivered} recipient(s)",
        )
        return BroadcastResult(
            delivered=delivered, audience=payload.audience, title=payload.title
        )

    # ── Audit log ───────────────────────────────────────────────────────────────

    async def list_audit(self, limit: int = 100) -> list[AdminAuditItem]:
        docs = await self._scan(_COL_AUDIT)
        items = [
            AdminAuditItem(
                id=d["id"],
                action=d.get("action", ""),
                actor_uid=d.get("actor_uid", ""),
                actor_email=d.get("actor_email"),
                target_uid=d.get("target_uid"),
                target_label=d.get("target_label"),
                detail=d.get("detail", ""),
                created_at=_as_utc(d.get("created_at")) or _utcnow(),
            )
            for d in docs
        ]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    # ── System health ───────────────────────────────────────────────────────────

    async def get_system_health(self) -> SystemHealth:
        components: list[HealthComponent] = []

        # Firestore — a 1-doc read proves connectivity + credentials.
        try:
            await self._db.collection(_COL_USERS).limit(1).get()
            components.append(HealthComponent(name="Firestore", status="ok"))
        except Exception as exc:  # noqa: BLE001
            components.append(
                HealthComponent(name="Firestore", status="down", detail=str(exc)[:200])
            )

        # Redis — ping.
        if self._redis is not None:
            try:
                await self._redis.ping()
                components.append(HealthComponent(name="Redis", status="ok"))
            except Exception as exc:  # noqa: BLE001
                components.append(
                    HealthComponent(name="Redis", status="down", detail=str(exc)[:200])
                )
        else:
            components.append(
                HealthComponent(name="Redis", status="disabled", detail="Client unavailable")
            )

        # Celery workers — a short broadcast ping (best-effort, non-blocking).
        components.append(await self._celery_health())

        # Provider configuration (presence checks — never expose the secrets).
        components.append(
            HealthComponent(
                name="Anthropic LLM",
                status="ok" if settings.anthropic_api_key else "disabled",
                detail="API key configured" if settings.anthropic_api_key else "Not configured",
            )
        )
        components.append(
            HealthComponent(
                name="OpenAI (fallback)",
                status="ok" if settings.openai_api_key else "disabled",
            )
        )
        components.append(
            HealthComponent(
                name="Sentry",
                status="ok" if settings.sentry_dsn else "disabled",
            )
        )
        components.append(
            HealthComponent(
                name="Stripe billing",
                status="ok" if settings.stripe_secret_key else "disabled",
            )
        )

        statuses = {c.status for c in components}
        if "down" in statuses:
            overall = "down"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "ok"

        return SystemHealth(
            status=overall,
            environment=settings.environment,
            components=components,
            generated_at=_utcnow(),
        )

    async def _celery_health(self) -> HealthComponent:
        try:
            from agents.bus.celery_app import celery_app  # noqa: PLC0415

            def _ping() -> list[Any]:
                return celery_app.control.ping(timeout=1.0)

            replies = await asyncio.wait_for(asyncio.to_thread(_ping), timeout=3.0)
            worker_count = len(replies or [])
            if worker_count:
                return HealthComponent(
                    name="Celery workers",
                    status="ok",
                    detail=f"{worker_count} worker(s) online",
                )
            return HealthComponent(
                name="Celery workers",
                status="degraded",
                detail="No workers responded to ping",
            )
        except Exception as exc:  # noqa: BLE001
            return HealthComponent(
                name="Celery workers", status="degraded", detail=str(exc)[:200]
            )


# ── Pure mappers ────────────────────────────────────────────────────────────────


def _to_item(user: User) -> AdminUserItem:
    return AdminUserItem(
        uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        provider=user.provider,
        role=user.role,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _norm_status(value: Any) -> str:
    return value if value in ("new", "in_progress", "resolved", "archived") else "new"


# ── FastAPI dependency ──────────────────────────────────────────────────────────


async def get_admin_service(
    db: AsyncClient = Depends(get_firestore_client),
    redis: Redis = Depends(get_redis),
) -> AdminService:
    return AdminService(db=db, redis=redis)
