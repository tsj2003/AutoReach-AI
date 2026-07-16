"""Fast onboarding — the '3-minute setup'.

POST /api/onboarding/analyze-website  → read the user's site, draft a campaign
scaffold (offer, ICP, client cure, signal matrix, first email) for review.

JWT-scoped and rate-limited (it fetches an external URL, so it's both auth-gated
and throttled against abuse).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cockpit.api.deps import get_current_user
from cockpit.api.ratelimit import rate_limit
from engine.auth import CurrentUser
from engine.llm.website_intake import analyze_website

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class AnalyzeWebsiteRequest(BaseModel):
    url: str


@router.post(
    "/analyze-website",
    dependencies=[Depends(rate_limit("onboarding-website", limit=20, window_seconds=3600))],
)
def analyze_website_endpoint(
    body: AnalyzeWebsiteRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Draft a campaign scaffold from the user's website (for their review/edit)."""
    return analyze_website(body.url).as_dict()
