"""
POST /api/events — browser-side non-Purchase events forwarded to CAPI.
Purchase is rejected (400). Idempotent on (event_name, event_id).

Click is stored for the dashboard and is not forwarded to the ad networks.
A row is geo_qualified only when the IP is a public UAE address and not a
VPN, proxy, Tor exit, or datacenter. The same check checkout already uses.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.models import AnalyticsEvent
from app.services.capi import send_event
from app.services.geo import extract_client_ip
from app.services.ip_cache import qualify_ip
from app.services.traffic import channel_from_attribution, clip, landing_path, merged_attribution

router = APIRouter()

PIXEL_EVENTS = {"ViewContent", "AddToCart", "InitiateCheckout"}
ALLOWED_EVENTS = PIXEL_EVENTS | {"Click"}


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
    gclid: str = ""
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
    peer = request.client.host if request.client else ""
    client_ip = extract_client_ip(request.headers, peer)
    user_agent = request.headers.get("user-agent", "")
    qualified = qualify_ip(db, client_ip)
    db.commit()

    attr = merged_attribution(body.attribution.model_dump(), body.source_url)
    payload_dict = body.model_dump()
    payload_dict["attribution"] = attr
    payload_dict["client_ip"] = client_ip
    payload_dict["user_agent"] = user_agent

    try:
        evt = AnalyticsEvent(
            id=uuid.uuid4(),
            event_name=body.event_name,
            event_id=body.event_id,
            order_public_id=None,
            payload=payload_dict,
            client_ip=clip(client_ip, 64),
            geo_qualified=qualified.allowed,
            geo_code=clip(qualified.code, 40),
            country_code=clip(qualified.country_code, 8),
            visitor_id=clip(attr.get("saba_cid"), 80),
            channel=channel_from_attribution(attr, body.source_url),
            utm_source=clip(attr.get("utm_source"), 120),
            utm_medium=clip(attr.get("utm_medium"), 120),
            utm_campaign=clip(attr.get("utm_campaign"), 120),
            utm_content=clip(attr.get("utm_content"), 120),
            landing_path=landing_path(body.source_url),
            created_at=datetime.now(timezone.utc),
        )
        db.add(evt)
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}

    if body.event_name in PIXEL_EVENTS:
        try:
            send_event(body.event_name, payload_dict)
        except Exception:
            pass

    return {"ok": True}
