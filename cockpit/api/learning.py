"""Learning / weekly insight API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from cockpit.api.deps import get_current_user, get_events, get_store
from engine.auth import CurrentUser
from engine.learning.measurement import LearningMeasurementService
from engine.signals.feature_flags import is_learning_enabled

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/weekly")
def weekly_learning_report(
    days: int = Query(default=7, ge=1, le=90),
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    events=Depends(get_events),
):
    if not is_learning_enabled():
        raise HTTPException(
            503,
            "Learning measurement is disabled (set AUTOREACH_LEARNING_ENABLED=1 to enable)",
        )
    svc = LearningMeasurementService(store=store, events=events)
    report = svc.weekly_report(tenant_id=current_user.tenant_id, days=days)
    return report.as_dict()
