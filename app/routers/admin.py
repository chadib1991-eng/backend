"""
Admin API. The dashboard logs in with ADMIN_USERNAME and ADMIN_PASSWORD.
X-Admin-Token still works for the orders list when ADMIN_TOKEN is set.

Login is not limited to UAE IPs. The numbers it returns are.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Order
from app.services.admin_auth import (
    COOKIE,
    clear_attempts,
    clear_session_cookie,
    cookie_secure,
    credentials_ok,
    issue_session,
    login_configured,
    read_session,
    record_failure,
    set_session_cookie,
    token_ok,
    too_many_attempts,
)
from app.services.admin_metrics import RangeError, build_report
from app.services.geo import extract_client_ip
from app.services.sheets import push_order
from app.settings import settings

router = APIRouter()

_UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "غير مصرح"}}


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


def _scheme(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    return forwarded or request.url.scheme


def _require_admin(
    request: Request,
    x_admin_token: Optional[str] = Header(default=None),
) -> None:
    if token_ok(x_admin_token):
        return
    if read_session(request.cookies.get(COOKIE, "")):
        return
    raise HTTPException(status_code=401, detail=_UNAUTHORIZED)


def _no_store(response: JSONResponse) -> JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/api/admin/login")
def admin_login(body: LoginBody, request: Request):
    ip = extract_client_ip(request.headers, request.client.host if request.client else "")
    if too_many_attempts(ip):
        return _no_store(JSONResponse(
            status_code=429,
            content={"error": {"code": "rate_limited", "message": "Too many attempts. Wait a few minutes."}},
        ))
    if not login_configured():
        return _no_store(JSONResponse(
            status_code=503,
            content={"error": {"code": "not_configured", "message": "Set ADMIN_USERNAME and ADMIN_PASSWORD on the API."}},
        ))
    if not credentials_ok(body.username, body.password):
        record_failure(ip)
        return _no_store(JSONResponse(
            status_code=401,
            content={"error": {"code": "unauthorized", "message": "Wrong username or password."}},
        ))

    clear_attempts(ip)
    response = JSONResponse({"ok": True})
    set_session_cookie(response, issue_session(settings.admin_username), cookie_secure(_scheme(request)))
    return _no_store(response)


@router.post("/api/admin/logout")
def admin_logout(request: Request):
    response = JSONResponse({"ok": True})
    clear_session_cookie(response, cookie_secure(_scheme(request)))
    return _no_store(response)


@router.get("/api/admin/session")
def admin_session(_: None = Depends(_require_admin)):
    return _no_store(JSONResponse({"ok": True}))


@router.get("/api/admin/metrics")
def admin_metrics(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
    preset: str = Query(default="7d", alias="range"),
    date_from: Optional[str] = Query(default=None, alias="from"),
    date_to: Optional[str] = Query(default=None, alias="to"),
):
    try:
        report = build_report(db, preset, date_from, date_to)
    except RangeError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "bad_range", "message": str(exc)}},
        ) from exc
    except ProgrammingError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "migration_required",
                    "message": "Run backend/migrations/20261027_admin_dashboard.sql on the database.",
                }
            },
        ) from exc
    return _no_store(JSONResponse(report))


@router.get("/api/admin/orders")
def admin_orders(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    orders = db.scalars(
        select(Order).order_by(Order.created_at.desc()).limit(50)
    ).all()
    return [
        {
            "public_id": o.public_id,
            "status": o.status,
            "customer_name": o.customer_name,
            "phone_e164": o.phone_e164,
            "phone_local": o.phone_local,
            "total_aed": o.total_aed,
            "merchandise_aed": o.merchandise_aed,
            "sheet_synced_at": o.sheet_synced_at.isoformat() if o.sheet_synced_at else None,
            "sheet_error": o.sheet_error,
            "capi_status": o.capi_status,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]


@router.post("/api/admin/orders/{public_id}/resync")
def resync_order(
    public_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    """Re-push a single order to the sheet without overwriting ops columns."""
    order = db.scalars(
        select(Order).where(Order.public_id == public_id)
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "ما لقينا الطلب"}})

    push_order(order)
    db.commit()
    return {
        "ok": True,
        "sheet_error": order.sheet_error,
        "sheet_synced_at": order.sheet_synced_at.isoformat() if order.sheet_synced_at else None,
    }
