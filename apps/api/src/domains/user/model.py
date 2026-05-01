"""User domain — Firestore document model."""
from dataclasses import dataclass
from datetime import datetime


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
