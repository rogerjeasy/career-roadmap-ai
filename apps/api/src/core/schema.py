"""Base Pydantic schema.

All request/response schemas inherit from BaseSchema.
camelCase ↔ snake_case translation is handled by CaseConversionMiddleware at
the HTTP boundary — schemas use plain snake_case field names as normal Python.
"""
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
