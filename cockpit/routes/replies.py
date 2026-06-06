"""
Reply triage routes — the operator's daily inbox.

    GET  /engagements/{eng}/replies                 list pending
    POST /engagements/{eng}/replies                 record one (manual entry; also used by tests)
    POST /replies/{id}/draft                        save edited draft
    POST /replies/{id}/send                         mark as sent
    POST /replies/{id}/discard                      discard
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get(
    "/engagements/{engagement_id}/replies",
    response_class=HTMLResponse,
)
def list_replies(request: Request, engagement_id: str, status: str | None = None):
    store = request.app.state.store
    ops = request.app.state.ops
    eng = store.get_engagement(engagement_id)
    if eng is None:
        raise HTTPException(404, "engagement not found")
    replies = list(ops.list_replies(engagement_id, status=status, limit=200))
    # Hydrate prospect for each reply for the UI.
    enriched = []
    for r in replies:
        p = store.get_prospect(r.prospect_id)
        enriched.append({"reply": r, "prospect": p})
    return request.app.state.templates.TemplateResponse(
        request,
        "replies/list.html",
        {
            "engagement": eng,
            "replies": enriched,
            "filter_status": status,
        },
    )


@router.post("/engagements/{engagement_id}/replies")
def record_reply(
    request: Request,
    engagement_id: str,
    prospect_id: str = Form(...),
    snippet: str = Form(...),
    classification: str = Form("objection"),
    suggested_reply: str = Form(""),
    external_message_id: str = Form(""),
):
    request.app.state.ops.record_reply(
        engagement_id=engagement_id,
        prospect_id=prospect_id.strip(),
        snippet=snippet.strip(),
        classification=classification.strip().lower(),
        suggested_reply=suggested_reply.strip(),
        external_message_id=external_message_id.strip() or None,
    )
    return RedirectResponse(
        url=f"/engagements/{engagement_id}/replies", status_code=303
    )


@router.post("/replies/{reply_id}/draft")
def update_draft(
    request: Request,
    reply_id: str,
    suggested_reply: str = Form(...),
):
    reply = request.app.state.ops.update_reply_draft(
        reply_id, suggested_reply=suggested_reply.strip()
    )
    if reply is None:
        raise HTTPException(404, "reply not found")
    return RedirectResponse(
        url=f"/engagements/{reply.engagement_id}/replies", status_code=303
    )


@router.post("/replies/{reply_id}/send")
def mark_sent(request: Request, reply_id: str):
    ops = request.app.state.ops
    reply = request.app.state.store.get_reply(reply_id)
    if reply is None:
        raise HTTPException(404, "reply not found")
    if not ops.mark_reply_sent(reply_id):
        raise HTTPException(400, "reply could not be marked sent")
    return RedirectResponse(
        url=f"/engagements/{reply.engagement_id}/replies", status_code=303
    )


@router.post("/replies/{reply_id}/discard")
def discard(request: Request, reply_id: str):
    ops = request.app.state.ops
    reply = request.app.state.store.get_reply(reply_id)
    if reply is None:
        raise HTTPException(404, "reply not found")
    ops.discard_reply(reply_id)
    return RedirectResponse(
        url=f"/engagements/{reply.engagement_id}/replies", status_code=303
    )
