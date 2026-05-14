"""Test configuration for the Calendar MCP server.

Adds both mcp-servers/ (for `shared`) and mcp-servers/calendar/
(for `clients`, `tools`, `models`, etc.) to sys.path so imports work
the same as in production.
"""
import os
import sys

import pytest

# mcp-servers/calendar/
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# mcp-servers/
_MCP_DIR = os.path.dirname(_SERVER_DIR)

for path in (_MCP_DIR, _SERVER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


def _make_calendar_event(title: str = "Test Event", provider_name: str = "google"):
    from models import CalendarEvent, CalendarProvider

    provider = CalendarProvider.GOOGLE if provider_name == "google" else CalendarProvider.OUTLOOK
    return CalendarEvent(
        id=f"{provider_name}_event_abc123",
        title=title,
        description="Test description",
        start=datetime(2026, 5, 11, 9, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc),
        provider=provider,
        html_link=f"https://calendar.example.com/event/abc123",
        reminder_minutes=[60, 10],
    )


@pytest.fixture()
def mock_google_client():
    from models import CalendarProvider

    client = MagicMock()
    client.provider = CalendarProvider.GOOGLE
    client.create_event = AsyncMock(return_value=_make_calendar_event("Test Event", "google"))
    client.create_events_batch = AsyncMock(
        return_value=([_make_calendar_event("Week Task", "google")], [])
    )
    client.list_upcoming = AsyncMock(
        return_value=[_make_calendar_event("Upcoming Event", "google")]
    )
    return client


@pytest.fixture()
def mock_outlook_client():
    from models import CalendarProvider

    client = MagicMock()
    client.provider = CalendarProvider.OUTLOOK
    client.create_event = AsyncMock(return_value=_make_calendar_event("Test Event", "outlook"))
    client.create_events_batch = AsyncMock(
        return_value=([_make_calendar_event("Week Task", "outlook")], [])
    )
    client.list_upcoming = AsyncMock(
        return_value=[_make_calendar_event("Upcoming Event", "outlook")]
    )
    return client


@pytest.fixture()
def mock_clients(mock_google_client, mock_outlook_client):
    return {
        "google": mock_google_client,
        "outlook": mock_outlook_client,
    }


@pytest.fixture()
def mock_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture()
def mock_rate_limiter():
    rl = MagicMock()
    rl.check = AsyncMock(return_value=True)
    return rl


@pytest.fixture()
def test_client(mock_clients, mock_cache, mock_rate_limiter):
    """FastAPI TestClient with mocked dependencies injected at module level."""
    import server

    server._clients = mock_clients
    server._cache = mock_cache
    server._rate_limiter = mock_rate_limiter

    from fastapi.testclient import TestClient as _TC

    with _TC(server.app) as client:
        yield client
