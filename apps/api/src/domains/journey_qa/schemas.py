"""Ask-My-Journey domain — Pydantic schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[AskMessage] = Field(default_factory=list, max_length=20)


class AskReply(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
