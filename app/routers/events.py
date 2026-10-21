"""
POST /api/events — browser-side non-Purchase events forwarded to CAPI.
Purchase is rejected (400). Idempotent on (event_name, event_id).
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.models import AnalyticsEvent
from app.services.capi import send_event

router = APIRouter()

ALLOWED_EVENTS = {"ViewContent", "AddToCart", "InitiateCheckout"}


class Attribution(BaseModel):
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""
    fbclid: str = ""
    fbp: str = ""
    fbc: str = ""
    ttclid: str = ""
    ttp: str = ""
    sc_click_id: str = ""
    sc_cookie: str = ""
    saba_cid: str = ""


class EventPayload(BaseModel):
    event_name: str
    event_id: str
    event_time: int
    source_url: str = ""
    value: float = 0
    currency: str = "AED"
    contents: list[dict[str, Any]] = []
    attribution: Attribution = Attribution()
    name: Optional[str] = None
    phone: Optional[str] = None

    @model_validator(mode="after")
    def reject_purchase(self) -> "EventPayload":
        if self.event_name == "Purchase":
            raise ValueError("Purchase is not accepted here")
        if self.event_name not in ALLOWED_EVENTS:
            raise ValueError(f"Unknown event: {self.event_name}")
        return self


@router.post("/api/events", status_code=200)
def track_event(body: EventPayload, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")

    # Store in analytics_events (idempotent)
    payload_dict = body.model_dump()
    payload_dict["client_ip"] = client_ip
    payload_dict["user_agent"] = user_agent

    try:
        evt = AnalyticsEvent(
            id=uuid.uuid4(),
            event_name=body.event_name,
            event_id=body.event_id,
            order_public_id=None,
            payload=payload_dict,
            created_at=datetime.now(timezone.utc),
        )
        db.add(evt)
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}

    # Forward to CAPI (non-blocking — failures are swallowed)
    try:
        send_event(body.event_name, {
            **payload_dict,
            "attribution": body.attribution.model_dump(),
        })
    except Exception:
        pass

    return {"ok": True}
