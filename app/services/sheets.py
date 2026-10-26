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


# Stable catalog SKUs. Lines saved before sku was stored still resolve.
_SKU_BY_SLUG = {
    "razaz-al-shaar": "SABA-MIST",
    "kareem-al-intiash": "SABA-CREAM",
    "qalam-al-kaab": "SABA-HEEL",
}


def _dubai_parts(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = dt.timestamp() + _DUBAI_TZ_OFFSET * 3600
    return datetime.utcfromtimestamp(ts)


def _dubai_date(dt: datetime) -> str:
    """Sheet date column: 01/04/2026, Dubai calendar day."""
    return _dubai_parts(dt).strftime("%d/%m/%Y")


def _sheet_order_id(public_id: str) -> str:
    """SB-100241 becomes saba100241. Already-prefixed ids are kept."""
    text = (public_id or "").strip()
    if text.lower().startswith("saba"):
        return "saba" + text[4:]
    digits = ""
    for char in reversed(text):
        if char.isdigit():
            digits = char + digits
        elif digits:
            break
    return f"saba{digits}" if digits else f"saba{text}"


def _sheet_phone(phone_e164: str) -> str:
    raw = (phone_e164 or "").strip().replace(" ", "")
    if raw.startswith("+"):
        return raw
    if raw.startswith("971"):
        return f"+{raw}"
    if raw.startswith("0") and len(raw) == 10:
        return f"+971{raw[1:]}"
    return raw


def _line_sku(line: dict) -> str:
    sku = (line.get("sku") or "").strip()
    if sku:
        return sku
    return _SKU_BY_SLUG.get(line.get("slug") or "", line.get("slug") or "")


def order_sheet_row(order: "Order") -> dict:
    """
    One row for the orders sheet.

    date, orderid, country, name, phone, product, sku, quantity,
    totalprice, currency are filled. status is always empty.
    Several products are joined with slashes: name/name and 2/2/2.
    """
    lines = list(order.lines or [])
    total = order.total_aed if order.total_aed is not None else order.merchandise_aed
    return {
        "date": _dubai_date(order.created_at),
        "orderid": _sheet_order_id(order.public_id),
        "country": "uae",
        "name": order.customer_name,
        "phone": _sheet_phone(order.phone_e164),
        "product": "/".join((line.get("name_ar") or line.get("slug") or "") for line in lines),
        "sku": "/".join(_line_sku(line) for line in lines),
        "quantity": "/".join(str(line.get("pieces") or 1) for line in lines),
        "totalprice": total,
        "currency": "AED",
        "status": "",
    }


def push_order(order: "Order") -> None:
    """POST the order row to the sheet webhook. Sets sheet_synced_at or sheet_error."""
    if not settings.sheets_webhook_url:
        return

    body = {
        "record_type": "order",
        **order_sheet_row(order),
    }

    headers = {"Content-Type": "application/json"}

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
        "customer_name": name,
        "name": name,
        "phone_e164": phone_e164,
        "phone_local": phone_local,
        "message": message,
    }
    headers = {"Content-Type": "application/json"}
    try:
        with httpx.Client(follow_redirects=True) as client:
            client.post(settings.sheets_webhook_url, json=body, headers=headers, timeout=10.0)
    except Exception as exc:
        logger.error("sheets_contact_error %s", exc)
