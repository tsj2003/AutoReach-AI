"""
Prospect routes.

    GET  /engagements/{eng}/prospects        list
    POST /engagements/{eng}/prospects        add one
    POST /engagements/{eng}/prospects/upload CSV upload
"""

from __future__ import annotations

import io

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get(
    "/engagements/{engagement_id}/prospects",
    response_class=HTMLResponse,
)
def list_prospects(request: Request, engagement_id: str):
    store = request.app.state.store
    ops = request.app.state.ops
    eng = store.get_engagement(engagement_id)
    if eng is None:
        raise HTTPException(404, "engagement not found")
    prospects = list(ops.list_prospects(engagement_id, limit=500))
    return request.app.state.templates.TemplateResponse(
        request,
        "prospects/list.html",
        {
            "engagement": eng,
            "prospects": prospects,
            "ingest_result": None,
        },
    )


@router.post("/engagements/{engagement_id}/prospects")
def add_prospect(
    request: Request,
    engagement_id: str,
    email: str = Form(...),
    full_name: str = Form(""),
    company: str = Form(""),
    title: str = Form(""),
):
    request.app.state.ops.add_prospect(
        engagement_id=engagement_id,
        email=email.strip().lower(),
        full_name=full_name.strip() or None,
        company=company.strip() or None,
        title=title.strip() or None,
    )
    return RedirectResponse(
        url=f"/engagements/{engagement_id}/prospects", status_code=303
    )


@router.post("/engagements/{engagement_id}/prospects/upload")
async def upload_csv(
    request: Request,
    engagement_id: str,
    file: UploadFile = File(...),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    result = request.app.state.csv_ingest.ingest_text(
        engagement_id=engagement_id,
        text=text,
    )

    store = request.app.state.store
    eng = store.get_engagement(engagement_id)
    prospects = list(request.app.state.ops.list_prospects(engagement_id, limit=500))
    return request.app.state.templates.TemplateResponse(
        request,
        "prospects/list.html",
        {
            "engagement": eng,
            "prospects": prospects,
            "ingest_result": result,
        },
    )
