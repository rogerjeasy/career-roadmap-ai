"""Autopilot domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

ProposalSeverity = Literal["info", "warn"]
ProposalStatus = Literal["open", "accepted", "dismissed"]


class AutopilotProposalOut(BaseModel):
    id: str
    kind: str
    title: str
    detail: str
    severity: ProposalSeverity
    action_label: str
    action_route: str
    status: ProposalStatus
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AutopilotProposalOut":
        severity = doc.get("severity", "info")
        status = doc.get("status", "open")
        return cls(
            id=doc.get("id", ""),
            kind=doc.get("kind", ""),
            title=doc.get("title", ""),
            detail=doc.get("detail", ""),
            severity=severity if severity in ("info", "warn") else "info",
            action_label=doc.get("action_label", ""),
            action_route=doc.get("action_route", ""),
            status=status if status in ("open", "accepted", "dismissed") else "open",
            created_at=doc.get("created_at"),
        )
