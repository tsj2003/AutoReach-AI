"""
Runtime control + HITL approval routes.

    POST /engagements/{eng}/tick    plan + execute one batch
    POST /engagements/{eng}/drain   run until quiescent
    POST /jobs/{id}/approve         HITL approve
    POST /jobs/{id}/reject          HITL reject
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.post("/engagements/{engagement_id}/tick")
def tick(request: Request, engagement_id: str):
    runtime = request.app.state.runtime
    runtime.tick()
    return RedirectResponse(url=f"/engagements/{engagement_id}", status_code=303)


@router.post("/engagements/{engagement_id}/drain")
def drain(request: Request, engagement_id: str):
    runtime = request.app.state.runtime
    runtime.run_once(max_iters=20)
    return RedirectResponse(url=f"/engagements/{engagement_id}", status_code=303)


@router.post("/engagements/{engagement_id}/poll-replies")
def poll_replies(request: Request, engagement_id: str):
    """
    Trigger a Gmail reply-detection pass on this Engagement.
    Only available when the cockpit is wired with a real Gmail adapter.
    """
    detector = getattr(request.app.state, "reply_detector", None)
    if detector is None:
        raise HTTPException(
            400,
            "reply detector not configured. Set AUTOREACH_GMAIL_TOKEN_PATH + AUTOREACH_GMAIL_SENDER + GEMINI_API_KEY.",
        )
    result = detector.poll(engagement_id)
    request.app.state.last_poll_result = {
        "engagement_id": engagement_id,
        "prospects_scanned": result.prospects_scanned,
        "threads_polled": result.threads_polled,
        "replies_recorded": result.replies_recorded,
        "auto_responders": result.auto_responders,
        "duplicates_skipped": result.duplicates_skipped,
        "fell_back_to_default": result.fell_back_to_default,
        "llm_cost_cents": result.llm_cost_cents,
        "token_invalid": result.token_invalid,
        "errors": result.errors[:5],
    }
    return RedirectResponse(url=f"/engagements/{engagement_id}/replies", status_code=303)


@router.post("/jobs/{job_id}/approve")
def approve(request: Request, job_id: str):
    runtime = request.app.state.runtime
    job = request.app.state.store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    runtime.approve_job(job_id)
    return RedirectResponse(url=f"/engagements/{job.engagement_id}", status_code=303)


@router.post("/jobs/{job_id}/reject")
def reject(
    request: Request,
    job_id: str,
    reason: str = Form(""),
):
    runtime = request.app.state.runtime
    job = request.app.state.store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    runtime.reject_job(job_id, reason=reason)
    return RedirectResponse(url=f"/engagements/{job.engagement_id}", status_code=303)
