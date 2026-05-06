"""agents.bus — Celery + Redis pub/sub transport layer.

Exposes the public surface for task dispatch and event streaming.
The API imports ``TaskPublisher`` and ``channel_for_session`` from here.
"""
from agents.bus.celery_app import celery_app
from agents.bus.channel import channel_for_session, channel_for_request
from agents.bus.publisher import EventPublisher, TaskPublisher
from agents.bus.subscriber import subscribe_to_session

__all__ = [
    "celery_app",
    "channel_for_session",
    "channel_for_request",
    "EventPublisher",
    "TaskPublisher",
    "subscribe_to_session",
]
