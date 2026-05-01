"""Firestore async client — available after Firebase Admin SDK is initialized."""
from firebase_admin import firestore_async
from google.cloud.firestore_v1.async_client import AsyncClient


def get_firestore_client() -> AsyncClient:
    """Return the Firestore async client. Requires firebase_admin.initialize_app() first."""
    return firestore_async.client()
