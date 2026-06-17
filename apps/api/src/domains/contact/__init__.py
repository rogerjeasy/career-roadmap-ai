"""Contact domain — public surface."""
from src.domains.contact.schemas import ContactRequestAck, ContactRequestCreate
from src.domains.contact.service import ContactService, get_contact_service

__all__ = [
    "ContactRequestAck",
    "ContactRequestCreate",
    "ContactService",
    "get_contact_service",
]
