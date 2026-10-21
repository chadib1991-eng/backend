"""
Sweeper: finalize pending_upsell orders older than 2 minutes as declined.
Runs every 60 seconds from the FastAPI lifespan.
Same code path as the HTTP complete handler.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def finalize_stale_orders() -> None:
    """
    Called from the async loop. Uses a sync session (sync SQLAlchemy is the design choice).
    """
    from app.db import SessionLocal
    from app.models import Order, Product
    from app.services.orders import complete_order
    from app.services.capi import send_purchase
    from app.services.sheets import push_order

    db: Session = SessionLocal()
    try:
        stmt = (
            select(Order)
            .where(Order.status == "pending_upsell")
            .where(
                Order.created_at <= text("NOW() - INTERVAL '2 minutes'")
            )
            .with_for_update(skip_locked=True)
        )
        orders = db.scalars(stmt).all()

        for order in orders:
            try:
                upsell_product = None
                if order.upsell_slug:
                    upsell_product = db.get(Product, order.upsell_slug)

                complete_order(db, order, accepted=False, upsell_product=upsell_product)
                db.commit()
                logger.info("sweeper_confirmed public_id=%s", order.public_id)

                # After commit: CAPI + sheet
                capi_status = send_purchase(order)
                order.capi_status = capi_status
                order.capi_sent_at = datetime.now(timezone.utc)
                push_order(order)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error("sweeper_error public_id=%s %s", order.public_id, exc)
    finally:
        db.close()


async def sweep_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
        if stop.is_set():
            break
        try:
            # Run the sync function in the default executor (thread pool)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, finalize_stale_orders)
        except Exception as exc:
            logger.error("sweep_loop_error %s", exc)
