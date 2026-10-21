"""
Push orders and contacts to the Google Apps Script webhook.
Failure is recorded on the order row and never fails the HTTP response.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from app.settings import settings

if TYPE_CHECKING:
    from app.models import Order

logger = logging.getLogger(__name__)

_DUBAI_TZ_OFFSET = 4  # UTC+4, no DST


def _dubai_format(dt: datetime) -> str:
    """Format a UTC datetime as YYYY-MM-DD HH:mm in Asia/Dubai (UTC+4)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = dt.timestamp() + _DUBAI_TZ_OFFSET * 3600
    d = datetime.utcfromtimestamp(ts)
    return d.strftime("%Y-%m-%d %H:%M")


def _items_ar(lines: list[dict]) -> str:
    """
    Human-readable Arabic summary of the order lines.
    Example: رذاذ ماء الإمارات × قطعتين (279) + كريم الانتعاش × قطعة عرض (99)
    """
    pieces_ar = {1: "قطعة", 2: "قطعتين", 3: "٣ قطع"}
    parts = []
    for line in lines:
        name = line.get("name_ar", line["slug"])
        pieces = line["pieces"]
        price = line["unit_price_aed"]
        if line.get("is_upsell"):
            parts.append(f"{name} × قطعة عرض ({price})")
        else:
            label = pieces_ar.get(pieces, f"{pieces} قطع")
            parts.append(f"{name} × {label} ({price})")
    return " + ".join(parts)


def push_order(order: "Order") -> None:
    """POST the order row to the sheet webhook. Sets sheet_synced_at or sheet_error."""
    if not settings.sheets_webhook_url:
        return

    attr = order.attribution or {}
    body = {
        "record_type": "order",
        "secret": settings.sheets_webhook_secret,
        "order_id": order.public_id,
        "created_at_dubai": _dubai_format(order.created_at),
        "status": order.status,
        "customer_name": order.customer_name,
        "phone_e164": order.phone_e164,
        "phone_local": order.phone_local,
        "items_ar": _items_ar(order.lines),
        "lines_json": str(order.lines),
        "upsell_accepted": order.upsell_accepted or False,
        "upsell_product_slug": order.upsell_slug or "",
        "upsell_price_aed": 99 if order.upsell_accepted else "",
        "merchandise_aed": order.merchandise_aed,
        "total_aed": order.total_aed,
        "currency": "AED",
        "payment_method": "COD",
        "event_id": order.event_id,
        "landing_url": order.landing_url or "",
        "utm_source": attr.get("utm_source", ""),
        "utm_medium": attr.get("utm_medium", ""),
        "utm_campaign": attr.get("utm_campaign", ""),
        "utm_content": attr.get("utm_content", ""),
        "utm_term": attr.get("utm_term", ""),
        "fbclid": attr.get("fbclid", ""),
        "fbp": attr.get("fbp", ""),
        "fbc": attr.get("fbc", ""),
        "ttclid": attr.get("ttclid", ""),
        "ttp": attr.get("ttp", ""),
        "sc_click_id": attr.get("sc_click_id", ""),
        "sc_cookie": attr.get("sc_cookie", ""),
        "client_ip": order.client_ip or "",
        "user_agent": order.user_agent or "",
    }

    headers = {
        "Content-Type": "application/json",
        "X-Saba-Secret": settings.sheets_webhook_secret,
    }

    for attempt in range(2):
        try:
            with httpx.Client(follow_redirects=True) as client:
                r = client.post(settings.sheets_webhook_url, json=body, headers=headers, timeout=10.0)
            text = r.text or ""
            if '"ok":true' in text or '"ok": true' in text:
                order.sheet_synced_at = datetime.now(timezone.utc)
                order.sheet_error = None
                return
            if "html" in text.lower() and "login" in text.lower():
                order.sheet_error = "auth"
                logger.error("sheets_auth_error order_id=%s", order.public_id)
                return
            order.sheet_error = f"bad_response:{r.status_code}"
            return
        except httpx.NetworkError:
            if attempt == 0:
                time.sleep(2)
                continue
            order.sheet_error = "network_error"
            logger.error("sheets_network_error order_id=%s", order.public_id)
            return
        except Exception as exc:
            order.sheet_error = str(exc)[:100]
            logger.error("sheets_error order_id=%s %s", order.public_id, exc)
            return


def push_contact(name: str, phone_e164: str, phone_local: str, message: str) -> None:
    """Push a contact form message to the sheet."""
    if not settings.sheets_webhook_url:
        return
    body = {
        "record_type": "contact",
        "secret": settings.sheets_webhook_secret,
        "customer_name": name,
        "name": name,
        "phone_e164": phone_e164,
        "phone_local": phone_local,
        "message": message,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Saba-Secret": settings.sheets_webhook_secret,
    }
    try:
        with httpx.Client(follow_redirects=True) as client:
            client.post(settings.sheets_webhook_url, json=body, headers=headers, timeout=10.0)
    except Exception as exc:
        logger.error("sheets_contact_error %s", exc)
