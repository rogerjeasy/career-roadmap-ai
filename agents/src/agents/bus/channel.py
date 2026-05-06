"""Centralised Redis pub/sub channel naming conventions.

All channel names are constructed here — no magic strings anywhere else.
Changing the naming scheme is a one-file edit.
"""


def channel_for_session(user_id: str, session_id: str) -> str:
    """Per-session event channel — the API subscribes here to forward SSE."""
    return f"agent_events:{user_id}:{session_id}"


def channel_for_request(correlation_id: str) -> str:
    """Per-request channel — useful for tracking a single generation run."""
    return f"agent_events:req:{correlation_id}"
