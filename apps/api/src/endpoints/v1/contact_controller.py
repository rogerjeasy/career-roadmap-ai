"""Contact — public sales/support enquiry intake.

Unauthenticated by design (it backs the marketing site's contact form). The
global per-IP rate limiter still applies via middleware.

Route:
  POST /api/v1/contact   — file an enquiry
"""
from fastapi import APIRouter, Depends, status

from src.domains.contact.schemas import ContactRequestAck, ContactRequestCreate
from src.domains.contact.service import ContactService, get_contact_service

router = APIRouter(prefix="/contact", tags=["contact"])


@router.post(
    "",
    response_model=ContactRequestAck,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact enquiry",
)
async def submit_contact(
    body: ContactRequestCreate,
    service: ContactService = Depends(get_contact_service),
) -> ContactRequestAck:
    return await service.submit(body)
