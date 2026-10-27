"""
Order creation and completion logic.
The checkout router owns the HTTP layer; this module owns the business logic.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Order, Product
from app.services.pricing import price_for, choose_upsell
from app.services.traffic import channel_from_attribution


def next_public_id(db: Session) -> str:
    n = db.execute(text("SELECT nextval('order_public_seq')")).scalar_one()
    return f"SB-{n}"


def build_line(product: Product, offer_code: str, is_upsell: bool = False) -> dict:
    pieces, price_aed = price_for(product, offer_code)
    return {
        "slug": product.slug,
        "sku": product.sku,
        "name_ar": product.name_ar,
        "offer_code": offer_code,
        "pieces": pieces,
        "unit_price_aed": price_aed,
        "is_upsell": is_upsell,
    }


def find_duplicate(
    db: Session,
    phone_e164: str,
    line_slugs: list[str],
    window_minutes: int = 10,
) -> Optional[Order]:
    """
    Return a pending or confirmed order in the last 10 min for the same phone
    and same product set (ignoring upsell lines). Returns None if none found.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    # Use interval in SQL for cross-db compat
    stmt = (
        select(Order)
        .where(Order.phone_e164 == phone_e164)
        .where(Order.status.in_(["pending_upsell", "confirmed"]))
        .where(
            Order.created_at
            >= text(f"NOW() - INTERVAL '{window_minutes} minutes'")
        )
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    orders = db.scalars(stmt).all()
    for order in orders:
        existing_slugs = sorted(
            [l["slug"] for l in order.lines if not l.get("is_upsell")]
        )
        if existing_slugs == sorted(line_slugs):
            return order
    return None


def create_order(
    db: Session,
    *,
    customer_name: str,
    phone_e164: str,
    phone_local: str,
    lines: list[dict],  # already built with build_line()
    upsell_slug: Optional[str],
    merchandise_aed: int,
    landing_url: str,
    attribution: dict,
    client_ip: str,
    user_agent: str,
    geo_qualified: bool = False,
    geo_code: str = "",
    country_code: str = "",
) -> Order:
    public_id = next_public_id(db)
    order = Order(
        id=uuid.uuid4(),
        public_id=public_id,
        status="pending_upsell",
        customer_name=customer_name,
        phone_e164=phone_e164,
        phone_local=phone_local,
        lines=lines,
        upsell_slug=upsell_slug,
        upsell_accepted=None,
        merchandise_aed=merchandise_aed,
        total_aed=None,  # set on complete
        event_id=public_id,  # event_id equals public_id
        landing_url=landing_url,
        attribution=attribution,
        client_ip=client_ip,
        user_agent=user_agent,
        geo_qualified=geo_qualified,
        geo_code=geo_code,
        country_code=country_code,
        channel=channel_from_attribution(attribution, landing_url),
        created_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.flush()  # get the id without committing
    return order


def complete_order(
    db: Session,
    order: Order,
    accepted: bool,
    upsell_product: Optional[Product] = None,
) -> Order:
    """
    Finalize the order. Appends upsell line if accepted and stock allows.
    Decrements stock. Caller must commit.
    """
    if order.status == "confirmed":
        return order  # idempotent

    lines = list(order.lines)
    total = order.merchandise_aed

    if accepted and order.upsell_slug and upsell_product and upsell_product.stock > 0:
        upsell_line = build_line(upsell_product, "upsell", is_upsell=True)
        lines.append(upsell_line)
        total += upsell_product.upsell_price
        order.upsell_accepted = True
        # Decrement upsell stock
        upsell_product.stock = upsell_product.stock - 1
    else:
        order.upsell_accepted = False

    # Decrement stock for main lines
    # We need the slugs and pieces from the main lines
    for line in lines:
        if not line.get("is_upsell"):
            product = db.get(Product, line["slug"])
            if product:
                product.stock = product.stock - line["pieces"]

    order.lines = lines
    order.total_aed = total
    order.status = "confirmed"
    order.confirmed_at = datetime.now(timezone.utc)
    return order
