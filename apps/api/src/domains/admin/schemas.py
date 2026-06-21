"""Admin domain — Pydantic request/response schemas.

Fields are snake_case; ``CaseConversionMiddleware`` translates them to/from
camelCase at the HTTP boundary, so the web client sees ``displayName`` etc.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Roles an admin may assign through the directory. ``superadmin`` is included so
# a superadmin can promote a peer, but assigning it is gated server-side.
AssignableRole = Literal["user", "admin", "superadmin"]

# Lifecycle status shared by the feedback and contact inboxes.
InboxStatus = Literal["new", "in_progress", "resolved", "archived"]

BroadcastAudience = Literal["all", "active", "admins"]
BroadcastTone = Literal["info", "success", "warn"]


# ── Users ──────────────────────────────────────────────────────────────────────


class AdminUserItem(BaseModel):
    """A single row in the admin user directory."""

    uid: str
    email: str
    display_name: str | None = None
    photo_url: str | None = None
    provider: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    """Page-based pagination — matches the web app's PaginatedResponse<T>."""

    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class AdminUserDetail(AdminUserItem):
    """A user's directory row enriched with their cross-domain activity counts."""

    roadmap_count: int = 0
    feedback_count: int = 0
    notification_count: int = 0
    last_roadmap_at: datetime | None = None


class UserRoleUpdate(BaseModel):
    role: AssignableRole


class UserStatusUpdate(BaseModel):
    is_active: bool


# ── Overview ───────────────────────────────────────────────────────────────────


class TimeseriesPoint(BaseModel):
    date: str   # ISO date (YYYY-MM-DD)
    count: int


class AdminOverview(BaseModel):
    """Platform-wide counts and trends, all derived from live Firestore data."""

    total_users: int
    active_users: int
    admin_users: int
    new_users_7d: int
    new_users_30d: int
    verified_users: int

    total_roadmaps: int
    roadmaps_7d: int

    total_feedback: int
    open_feedback: int
    total_contact_requests: int
    open_contact_requests: int
    newsletter_subscribers: int

    role_breakdown: dict[str, int] = Field(default_factory=dict)
    provider_breakdown: dict[str, int] = Field(default_factory=dict)
    signups_last_14_days: list[TimeseriesPoint] = Field(default_factory=list)
    recent_users: list[AdminUserItem] = Field(default_factory=list)
    generated_at: datetime


# ── Inbox (feedback + contact) ──────────────────────────────────────────────────


class AdminFeedbackItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    category: str
    subject: str
    message: str
    rating: int | None = None
    status: InboxStatus = "new"
    created_at: datetime


class AdminContactItem(BaseModel):
    id: str
    name: str
    email: str
    company: str = ""
    topic: str
    message: str
    status: InboxStatus = "new"
    created_at: datetime


class InboxStatusUpdate(BaseModel):
    status: InboxStatus


# ── Newsletter ──────────────────────────────────────────────────────────────────


class NewsletterSubscriberItem(BaseModel):
    user_id: str
    email: str | None = None
    display_name: str | None = None
    frequency: str
    topics: list[str] = Field(default_factory=list)
    subscribed: bool
    updated_at: datetime | None = None


# ── Broadcast ───────────────────────────────────────────────────────────────────


class BroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=1000)
    tone: BroadcastTone = "info"
    link: str | None = Field(default=None, max_length=500)
    audience: BroadcastAudience = "all"


class BroadcastResult(BaseModel):
    delivered: int
    audience: BroadcastAudience
    title: str


# ── Audit ───────────────────────────────────────────────────────────────────────


class AdminAuditItem(BaseModel):
    id: str
    action: str
    actor_uid: str
    actor_email: str | None = None
    target_uid: str | None = None
    target_label: str | None = None
    detail: str = ""
    created_at: datetime


# ── System health ───────────────────────────────────────────────────────────────


class HealthComponent(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down", "disabled"]
    detail: str = ""


class SystemHealth(BaseModel):
    status: Literal["ok", "degraded", "down"]
    environment: str
    components: list[HealthComponent]
    generated_at: datetime
