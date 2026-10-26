"""
Checkout routes: start and complete.
POST /api/checkout/start  → creates a pending_upsell order
POST /api/checkout/complete → confirms the order, fires CAPI + sheet
GET  /api/orders/{public_id} → public order status
"""
from __future__ import annotations
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.catalog_seed import resolve_cart_lines
from app.db import SessionLocal, get_db
from app.models import Order, Product
from app.services.phone import parse_uae_mobile
from app.services.pricing import price_for, choose_upsell
from app.services.geo import extract_client_ip, is_bypass_phone, check_order_ip
from app.services.orders import find_duplicate, create_order, complete_order, build_line
from app.services.capi import send_purchase
from app.services.sheets import push_order

router = APIRouter()
logger = logging.getLogger(__name__)


def _send_order_downstream(public_id: str) -> None:
    """CAPI and the sheet webhook. Runs after the response so the thank-you page is not blocked."""
    db = SessionLocal()
    try:
        order = db.scalars(select(Order).where(Order.public_id == public_id)).first()
        if not order:
            return
        try:
            order.capi_status = send_purchase(order)
            order.capi_sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            order.capi_error = str(exc)[:100]
            logger.exception("capi_failed public_id=%s", public_id)
        try:
            push_order(order)
        except Exception as exc:
            order.sheet_error = str(exc)[:100]
            logger.exception("sheet_failed public_id=%s", public_id)
        db.commit()
    except Exception:
        logger.exception("order_downstream_failed public_id=%s", public_id)
        db.rollback()
    finally:
        db.close()


# ---------- Request models ----------

class CartLine(BaseModel):
    slug: str
    offer_code: str

    model_config = {"extra": "ignore"}


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

    model_config = {"extra": "ignore"}


class CheckoutStartRequest(BaseModel):
    name: str
    phone: str
    lines: list[CartLine]
    landing_url: str = ""
    attribution: Attribution = Attribution()

    model_config = {"extra": "ignore"}


class CheckoutCompleteRequest(BaseModel):
    public_id: str
    accepted: bool

    model_config = {"extra": "ignore"}


# ---------- Helpers ----------

def _error(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


def _order_public_fields(order: Order) -> dict[str, Any]:
    return {
        "public_id": order.public_id,
        "customer_name": order.customer_name.split()[0] if order.customer_name else "",
        "phone_local": order.phone_local,
        "lines": order.lines,
        "total_aed": order.total_aed,
        "merchandise_aed": order.merchandise_aed,
        "status": order.status,
    }


# ---------- Routes ----------

@router.post("/api/checkout/start", status_code=201)
def checkout_start(body: CheckoutStartRequest, request: Request, db: Session = Depends(get_db)):
    # Validate name
    name = body.name.strip()
    if len(name) < 2 or len(name) > 80:
        return _error("invalid_name", "اكتبي اسمج")

    # Validate phone
    phone = parse_uae_mobile(body.phone)
    if phone is None:
        return _error("invalid_phone", "اكتبي رقم جوال إماراتي صحيح، مثل 0501234567")

    resolved_lines = resolve_cart_lines([(line.slug, line.offer_code) for line in body.lines])
    if not resolved_lines:
        return _error("invalid_line", "السلة فاضية")

    peer = request.client.host if request.client else ""
    client_ip = extract_client_ip(request.headers, peer)
    user_agent = request.headers.get("user-agent", "")

    # Build lines from the products table (backend is price authority)
    built_lines: list[dict] = []
    slugs_in_cart: list[str] = []

    for slug, offer_code in resolved_lines:
        product = db.get(Product, slug)
        if not product or not product.active:
            label = product.name_ar if product else ""
            message = (
                f"غير متوفر الحين: {label}"
                if label
                else "منتج بالسلة ما عاد متوفر. حدّثي الصفحة وحاولي مرة ثانية."
            )
            return _error("invalid_line", message)
        if product.stock <= 0:
            return _error("sold_out", f"غير متوفر الحين: {product.name_ar}")

        try:
            line = build_line(product, offer_code)
        except ValueError:
            return _error("invalid_line", f"كود العرض غير صحيح: {offer_code}")

        built_lines.append(line)
        slugs_in_cart.append(slug)

    # UAE, non-VPN, low-risk IP. The test phone skips this.
    if not is_bypass_phone(phone.e164):
        verdict = check_order_ip(client_ip)
        if not verdict.allowed:
            return _error(verdict.code, verdict.message, 403)

    merchandise_aed = sum(l["unit_price_aed"] for l in built_lines)

    # Duplicate window check
    existing = find_duplicate(db, phone.e164, slugs_in_cart)
    if existing:
        # Return the existing order and let the client follow the upsell path
        upsell_info = None
        if existing.upsell_slug and existing.status == "pending_upsell":
            upsell_product = db.get(Product, existing.upsell_slug)
            if upsell_product:
                upsell_info = {
                    "slug": upsell_product.slug,
                    "name_ar": upsell_product.name_ar,
                    "price_aed": upsell_product.upsell_price,
                    "image": upsell_product.images[0] if upsell_product.images else None,
                }
        return JSONResponse(
            status_code=200,
            content={
                "public_id": existing.public_id,
                "merchandise_aed": existing.merchandise_aed,
                "duplicate": True,
                "upsell": upsell_info,
            },
        )

    # Choose upsell
    all_slugs = [p.slug for p in db.scalars(select(Product).where(Product.active == True)).all()]
    upsell_slug = choose_upsell(slugs_in_cart, all_slugs)

    upsell_info = None
    if upsell_slug:
        upsell_product = db.get(Product, upsell_slug)
        if upsell_product and upsell_product.stock > 0:
            upsell_info = {
                "slug": upsell_product.slug,
                "name_ar": upsell_product.name_ar,
                "price_aed": upsell_product.upsell_price,
                "image": upsell_product.images[0] if upsell_product.images else None,
            }
        else:
            upsell_slug = None  # product out of stock

    # Store phone in attribution for CAPI
    attr = body.attribution.model_dump()
    attr["phone_e164"] = phone.e164

    order = create_order(
        db,
        customer_name=name,
        phone_e164=phone.e164,
        phone_local=phone.local,
        lines=built_lines,
        upsell_slug=upsell_slug,
        merchandise_aed=merchandise_aed,
        landing_url=body.landing_url,
        attribution=attr,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return JSONResponse(
        status_code=201,
        content={
            "public_id": order.public_id,
            "merchandise_aed": merchandise_aed,
            "duplicate": False,
            "upsell": upsell_info,
        },
    )


@router.post("/api/checkout/complete")
async def checkout_complete(request: Request, db: Session = Depends(get_db)):
    """
    Accepts application/json and text/plain (for sendBeacon).
    """
    content_type = request.headers.get("content-type", "")
    try:
        raw = await request.body()
        body_dict = json.loads(raw)
    except Exception:
        return _error("invalid_body", "طلب غير صحيح")

    try:
        body = CheckoutCompleteRequest.model_validate(body_dict)
    except Exception:
        return _error("invalid_body", "طلب غير صحيح")

    order = db.scalars(
        select(Order).where(Order.public_id == body.public_id)
    ).first()

    if not order:
        return _error("not_found", "ما لقينا الطلب", 404)

    # Idempotent: if already confirmed, return current state
    if order.status == "confirmed":
        return _order_public_fields(order)

    upsell_product = None
    if order.upsell_slug:
        upsell_product = db.get(Product, order.upsell_slug)

    complete_order(db, order, accepted=body.accepted, upsell_product=upsell_product)
    public_id = order.public_id
    db.commit()

    # Pixels and the sheet can take many seconds. The order is already confirmed.
    threading.Thread(
        target=_send_order_downstream,
        args=(public_id,),
        daemon=True,
    ).start()

    return _order_public_fields(order)


@router.get("/api/orders/{public_id}")
def get_order(public_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Public order status. Rate limiting is enforced at the proxy / EasyPanel level in production.
    In v1 there is no in-process rate limiter; the frontend polls at most every 500ms for 10s.
    """
    order = db.scalars(
        select(Order).where(Order.public_id == public_id)
    ).first()
    if not order:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "ما لقينا الطلب"}},
        )

    return {
        "public_id": order.public_id,
        "customer_name": order.customer_name.split()[0] if order.customer_name else "",
        "phone_local": order.phone_local,
        "lines": order.lines,
        "total_aed": order.total_aed,
        "merchandise_aed": order.merchandise_aed,
        "status": order.status,
    }
