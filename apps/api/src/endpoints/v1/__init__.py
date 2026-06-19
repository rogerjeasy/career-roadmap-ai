"""API v1 router — aggregates all v1 controllers."""
from fastapi import APIRouter

from src.endpoints.v1.admin_kb_controller import router as admin_kb_router
from src.endpoints.v1.auth_controller import router as auth_router
from src.endpoints.v1.autopilot_controller import router as autopilot_router
from src.endpoints.v1.billing_controller import router as billing_router
from src.endpoints.v1.books_controller import router as books_router
from src.endpoints.v1.coach_controller import router as coach_router
from src.endpoints.v1.cohorts_controller import router as cohorts_router
from src.endpoints.v1.contact_controller import router as contact_router
from src.endpoints.v1.credentials_controller import router as credentials_router
from src.endpoints.v1.cv_controller import router as cv_router
from src.endpoints.v1.discovery_controller import router as discovery_router
from src.endpoints.v1.evidence_controller import router as evidence_router
from src.endpoints.v1.feedback_controller import router as feedback_router
from src.endpoints.v1.intake_controller import router as intake_router
from src.endpoints.v1.learning_roi_controller import router as learning_roi_router
from src.endpoints.v1.integrations_controller import router as integrations_router
from src.endpoints.v1.localisation_controller import router as localisation_router
from src.endpoints.v1.market_controller import router as market_router
from src.endpoints.v1.mentorship_controller import router as mentorship_router
from src.endpoints.v1.monthly_plan_controller import router as monthly_plan_router
from src.endpoints.v1.negotiation_controller import router as negotiation_router
from src.endpoints.v1.networking_controller import router as networking_router
from src.endpoints.v1.newsletter_controller import router as newsletter_router
from src.endpoints.v1.notification_controller import router as notification_router
from src.endpoints.v1.opportunity_controller import router as opportunity_router
from src.endpoints.v1.orchestrator_controller import router as orchestrator_router
from src.endpoints.v1.oss_controller import router as oss_router
from src.endpoints.v1.portfolio_controller import router as portfolio_router
from src.endpoints.v1.progress_controller import router as progress_router
from src.endpoints.v1.roadmap_controller import router as roadmap_router
from src.endpoints.v1.schedule_controller import router as schedule_router
from src.endpoints.v1.session_controller import router as session_router
from src.endpoints.v1.storytelling_controller import router as storytelling_router
from src.endpoints.v1.stream_controller import router as stream_router
from src.endpoints.v1.user_controller import router as user_router
from src.endpoints.v1.wellness_controller import router as wellness_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(session_router)
router.include_router(orchestrator_router)
router.include_router(stream_router)
router.include_router(coach_router)
router.include_router(cv_router)
router.include_router(discovery_router)
router.include_router(intake_router)
router.include_router(opportunity_router)
router.include_router(roadmap_router)
router.include_router(admin_kb_router)
router.include_router(market_router)
router.include_router(networking_router)
router.include_router(progress_router)
router.include_router(schedule_router)
router.include_router(monthly_plan_router)
router.include_router(books_router)
router.include_router(notification_router)
router.include_router(integrations_router)
router.include_router(localisation_router)
router.include_router(evidence_router)
router.include_router(portfolio_router)
router.include_router(feedback_router)
router.include_router(newsletter_router)
router.include_router(autopilot_router)
router.include_router(contact_router)
router.include_router(billing_router)
router.include_router(credentials_router)
router.include_router(learning_roi_router)
router.include_router(cohorts_router)
router.include_router(mentorship_router)
router.include_router(negotiation_router)
router.include_router(wellness_router)
router.include_router(oss_router)
router.include_router(storytelling_router)
