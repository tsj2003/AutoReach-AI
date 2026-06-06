"""Shared FastAPI dependencies for the /api/* routes."""

from __future__ import annotations

from fastapi import Depends, Request

from engine.auth import CurrentUser
from engine.auth.jwt_bearer import get_current_user_dep
from engine.services import OperationsService, PnLService


def get_current_user(user: CurrentUser = Depends(get_current_user_dep)) -> CurrentUser:
    return user


def get_store(request: Request):
    return request.app.state.store


def get_ops(request: Request) -> OperationsService:
    return request.app.state.ops


def get_pnl(request: Request) -> PnLService:
    return request.app.state.pnl


def get_events(request: Request):
    return request.app.state.events


def get_ledger(request: Request):
    return request.app.state.ledger


def get_runtime(request: Request):
    return request.app.state.runtime


def get_csv_ingest(request: Request):
    return request.app.state.csv_ingest


def get_reply_detector(request: Request):
    return getattr(request.app.state, "reply_detector", None)
