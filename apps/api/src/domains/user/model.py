"""User domain — Firestore document model."""
from dataclasses import dataclass, field
from datetime import datetime


def default_notification_preferences() -> dict[str, bool]:
    """Default notification opt-ins for a freshly provisioned user."""
    return {
        "weekly_digest": True,
        "milestone_alerts": True,
        "market_alerts": False,
    }


@dataclass
class User:
    """Represents a user document stored in Firestore at /users/{firebase_uid}."""

    id: str            # Firestore document ID = firebase_uid
    firebase_uid: str
    email: str
    provider: str
    email_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None
    photo_url: str | None = None
    notification_preferences: dict[str, bool] = field(
        default_factory=default_notification_preferences
    )
