"""Feedback domain — public surface."""
from src.domains.feedback.schemas import FeedbackCreate, FeedbackOut
from src.domains.feedback.service import FeedbackService, get_feedback_service

__all__ = [
    "FeedbackCreate",
    "FeedbackOut",
    "FeedbackService",
    "get_feedback_service",
]
