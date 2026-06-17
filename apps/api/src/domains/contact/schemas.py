"""Contact domain — Pydantic schemas for public sales/support enquiries.

These come from the unauthenticated marketing ``/contact`` page, so the payload
is self-describing (name + email) rather than tied to an authenticated user.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContactTopic = Literal["sales", "support", "partnership", "general"]


class ContactRequestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    company: str = Field(default="", max_length=200)
    topic: ContactTopic = "general"
    message: str = Field(min_length=1, max_length=4000)


class ContactRequestAck(BaseModel):
    received: bool = True
    message: str = "Thanks — your message is in. We'll be in touch shortly."
