"""Newsletter domain — public surface."""
from src.domains.newsletter.schemas import NewsletterPrefsOut, NewsletterPrefsUpdate
from src.domains.newsletter.service import NewsletterService, get_newsletter_service

__all__ = [
    "NewsletterPrefsOut",
    "NewsletterPrefsUpdate",
    "NewsletterService",
    "get_newsletter_service",
]
