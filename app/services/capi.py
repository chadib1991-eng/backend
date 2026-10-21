"""
Server-side CAPI forwarding for Meta, TikTok, and Snap.
send_purchase(order) is the only public entry point for Purchase events.
send_event(payload) handles ViewContent, AddToCart, InitiateCheckout.
Timeouts: 4 seconds. One retry on network error only, not on HTTP 400.
"""
from __future__ import annotations
import json
import time
import logging
from typing import Any, Optional, TYPE_CHECKING

import httpx

from app.settings import settings
from app.services.hashing import (
    hash_phone_meta_snap,
    hash_phone_tiktok,
    hash_name_token,
    hash_external_id,
    split_name,
)

if TYPE_CHECKING:
    from app.models import Order

logger = logging.getLogger(__name__)


def _post(client: httpx.Client, url: str, payload: dict) -> tuple[bool, str]:
    """POST with one network-error retry. Returns (ok, status_str)."""
    for attempt in range(2):
        try:
            r = client.post(url, json=payload, timeout=4.0)
            if r.status_code < 300:
                return True, "ok"
            return False, f"http_{r.status_code}"
        except httpx.NetworkError:
            if attempt == 0:
                continue
            return False, "network_error"
        except Exception as exc:
            return False, str(exc)[:60]
    return False, "failed"


def _meta_purchase_payload(order: "Order", event_time: int) -> Optional[dict]:
    if not settings.meta_pixel_id or not settings.meta_capi_token:
        return None

    phone = order.attribution.get("phone_e164", "") or ""
    digits = phone.lstrip("+") if phone.startswith("+") else phone  # remove + for Meta/Snap

    fn_raw, ln_raw = split_name(order.customer_name)
    user_data: dict[str, Any] = {
        "fn": [hash_name_token(fn_raw)],
        "external_id": [
            hash_external_id(order.attribution.get("saba_cid", "")),
            hash_external_id(order.public_id),
        ],
        "client_ip_address": order.client_ip,
        "client_user_agent": order.user_agent,
    }

    if digits:
        user_data["ph"] = [hash_phone_meta_snap(digits)]
    if ln_raw:
        user_data["ln"] = [hash_name_token(ln_raw)]

    attr = order.attribution or {}
    if attr.get("fbp"):
        user_data["fbp"] = attr["fbp"]
    if attr.get("fbc"):
        user_data["fbc"] = attr["fbc"]

    content_ids = [l["slug"] for l in order.lines]
    contents = [
        {
            "id": l["slug"],
            "quantity": l["pieces"],
            "item_price": round(l["unit_price_aed"] / l["pieces"], 2),
        }
        for l in order.lines
    ]
    num_items = sum(l["pieces"] for l in order.lines)

    event: dict[str, Any] = {
        "event_name": "Purchase",
        "event_time": event_time,
        "event_id": order.public_id,
        "action_source": "website",
        "event_source_url": f"{settings.public_site_url}/thank-you/{order.public_id}",
        "user_data": user_data,
        "custom_data": {
            "currency": "AED",
            "value": order.total_aed,
            "content_ids": content_ids,
            "content_type": "product",
            "contents": contents,
            "order_id": order.public_id,
            "num_items": num_items,
        },
    }

    payload: dict[str, Any] = {"data": [event]}
    if settings.meta_test_event_code:
        payload["test_event_code"] = settings.meta_test_event_code

    return payload


def _tiktok_purchase_payload(order: "Order", event_time: int) -> Optional[dict]:
    if not settings.tiktok_pixel_id or not settings.tiktok_access_token:
        return None

    phone_raw = order.attribution.get("phone_e164", "") or order.phone_e164
    # TikTok hashes from +9715... (e164)
    tiktok_phone = phone_raw if phone_raw.startswith("+") else f"+{phone_raw.lstrip('0')}"

    attr = order.attribution or {}
    saba_cid = attr.get("saba_cid", "")

    user: dict[str, Any] = {
        "phone": hash_phone_tiktok(tiktok_phone),
        "external_id": hash_external_id(order.public_id),
        "ip": order.client_ip,
        "user_agent": order.user_agent,
    }
    if attr.get("ttp"):
        user["ttp"] = attr["ttp"]
    if attr.get("ttclid"):
        user["ttclid"] = attr["ttclid"]

    contents = [
        {
            "content_id": l["slug"],
            "content_name": l.get("name_ar", l["slug"]),
            "quantity": l["pieces"],
            "price": round(l["unit_price_aed"] / l["pieces"], 2),
        }
        for l in order.lines
    ]

    event: dict[str, Any] = {
        "event": "CompletePayment",
        "event_time": event_time,
        "event_id": order.public_id,
        "user": user,
        "properties": {
            "currency": "AED",
            "value": order.total_aed,
            "content_type": "product",
            "contents": contents,
        },
        "page": {
            "url": f"{settings.public_site_url}/thank-you/{order.public_id}",
            "referrer": "",
        },
    }

    payload: dict[str, Any] = {
        "event_source": "web",
        "event_source_id": settings.tiktok_pixel_id,
        "data": [event],
    }
    if settings.tiktok_test_event_code:
        payload["test_event_code"] = settings.tiktok_test_event_code

    return payload


def _snap_purchase_payload(order: "Order", event_time: int) -> Optional[dict]:
    if not settings.snap_pixel_id or not settings.snap_capi_token:
        return None

    phone_raw = order.phone_e164  # e164 like +971501234567
    # Snap: digits with country code, no plus
    digits = phone_raw.lstrip("+") if phone_raw.startswith("+") else phone_raw

    fn_raw, ln_raw = split_name(order.customer_name)
    user_data: dict[str, Any] = {
        "ph": [hash_phone_meta_snap(digits)],
        "fn": [hash_name_token(fn_raw)],
        "client_ip_address": order.client_ip,
        "client_user_agent": order.user_agent,
    }

    attr = order.attribution or {}
    if attr.get("sc_click_id"):
        user_data["sc_click_id"] = attr["sc_click_id"]
    if attr.get("sc_cookie"):
        user_data["sc_cookie1"] = attr["sc_cookie"]

    content_ids = [l["slug"] for l in order.lines]
    num_items = sum(l["pieces"] for l in order.lines)

    # Snap v3 uses millisecond event_time
    event: dict[str, Any] = {
        "event_name": "PURCHASE",
        "event_time": event_time * 1000,
        "event_id": order.public_id,
        "action_source": "WEB",
        "event_source_url": f"{settings.public_site_url}/thank-you/{order.public_id}",
        "user_data": user_data,
        "custom_data": {
            "currency": "AED",
            "value": order.total_aed,
            "content_ids": content_ids,
            "content_type": "product",
            "num_items": str(num_items),
            "order_id": order.public_id,
        },
    }

    return {"data": [event]}


def send_purchase(order: "Order") -> dict[str, str]:
    """
    Send Purchase to all three networks concurrently (sequential httpx calls).
    Returns status dict: {"meta": "ok", "tiktok": "skip", "snap": "http_400"}.
    Failures are recorded but do not raise.
    """
    event_time = int(order.confirmed_at.timestamp()) if order.confirmed_at else int(time.time())
    status: dict[str, str] = {}

    with httpx.Client() as client:
        # Meta
        meta_payload = _meta_purchase_payload(order, event_time)
        if meta_payload is None:
            status["meta"] = "skip"
        else:
            url = (
                f"https://graph.facebook.com/{settings.meta_graph_version}"
                f"/{settings.meta_pixel_id}/events?access_token={settings.meta_capi_token}"
            )
            ok, s = _post(client, url, meta_payload)
            status["meta"] = s
            if not ok:
                logger.error("meta_capi_error order_id=%s status=%s", order.public_id, s)

        # TikTok
        tiktok_payload = _tiktok_purchase_payload(order, event_time)
        if tiktok_payload is None:
            status["tiktok"] = "skip"
        else:
            url = "https://business-api.tiktok.com/open_api/v1.3/event/track/"
            headers = {"Access-Token": settings.tiktok_access_token}
            for attempt in range(2):
                try:
                    r = client.post(url, json=tiktok_payload, headers=headers, timeout=4.0)
                    status["tiktok"] = "ok" if r.status_code < 300 else f"http_{r.status_code}"
                    break
                except httpx.NetworkError:
                    if attempt == 1:
                        status["tiktok"] = "network_error"

        # Snap
        snap_payload = _snap_purchase_payload(order, event_time)
        if snap_payload is None:
            status["snap"] = "skip"
        else:
            url = (
                f"https://tr.snapchat.com/v3/{settings.snap_pixel_id}"
                f"/events?access_token={settings.snap_capi_token}"
            )
            ok, s = _post(client, url, snap_payload)
            status["snap"] = s

    return status


def send_event(event_name: str, payload: dict) -> None:
    """
    Forward non-Purchase events (ViewContent, AddToCart, InitiateCheckout)
    to all configured networks. Errors are logged and swallowed.
    """
    event_time = payload.get("event_time", int(time.time()))
    source_url = payload.get("source_url", settings.public_site_url)
    value = payload.get("value", 0)
    currency = payload.get("currency", "AED")
    contents = payload.get("contents", [])
    attribution = payload.get("attribution", {})
    event_id = payload.get("event_id", "")
    client_ip = payload.get("client_ip", "")
    user_agent = payload.get("user_agent", "")
    saba_cid = attribution.get("saba_cid", "")

    with httpx.Client() as client:
        # Map event names per platform
        meta_event = event_name  # same
        tiktok_event = event_name  # same
        snap_event_map = {
            "ViewContent": "VIEW_CONTENT",
            "AddToCart": "ADD_CART",
            "InitiateCheckout": "START_CHECKOUT",
        }
        snap_event = snap_event_map.get(event_name, event_name)

        content_ids = [c.get("id", c.get("content_id", "")) for c in contents]

        if settings.meta_pixel_id and settings.meta_capi_token:
            user_data: dict[str, Any] = {
                "client_ip_address": client_ip,
                "client_user_agent": user_agent,
            }
            if saba_cid:
                user_data["external_id"] = [hash_external_id(saba_cid)]
            if attribution.get("fbp"):
                user_data["fbp"] = attribution["fbp"]
            if attribution.get("fbc"):
                user_data["fbc"] = attribution["fbc"]

            meta_evt: dict[str, Any] = {
                "event_name": meta_event,
                "event_time": event_time,
                "event_id": event_id,
                "action_source": "website",
                "event_source_url": source_url,
                "user_data": user_data,
                "custom_data": {
                    "currency": currency,
                    "value": value,
                    "content_ids": content_ids,
                    "content_type": "product",
                    "contents": contents,
                },
            }
            meta_p: dict[str, Any] = {"data": [meta_evt]}
            if settings.meta_test_event_code:
                meta_p["test_event_code"] = settings.meta_test_event_code

            url = (
                f"https://graph.facebook.com/{settings.meta_graph_version}"
                f"/{settings.meta_pixel_id}/events?access_token={settings.meta_capi_token}"
            )
            try:
                client.post(url, json=meta_p, timeout=4.0)
            except Exception as exc:
                logger.error("meta_event_error event=%s %s", event_name, exc)

        if settings.tiktok_pixel_id and settings.tiktok_access_token:
            tt_user: dict[str, Any] = {"ip": client_ip, "user_agent": user_agent}
            if saba_cid:
                tt_user["external_id"] = hash_external_id(saba_cid)
            if attribution.get("ttp"):
                tt_user["ttp"] = attribution["ttp"]

            tiktok_contents = [
                {
                    "content_id": c.get("id", c.get("content_id", "")),
                    "content_name": c.get("content_name", ""),
                    "quantity": c.get("quantity", 1),
                    "price": c.get("item_price", c.get("price", 0)),
                }
                for c in contents
            ]
            tt_p: dict[str, Any] = {
                "event_source": "web",
                "event_source_id": settings.tiktok_pixel_id,
                "data": [{
                    "event": tiktok_event,
                    "event_time": event_time,
                    "event_id": event_id,
                    "user": tt_user,
                    "properties": {
                        "currency": currency,
                        "value": value,
                        "content_type": "product",
                        "contents": tiktok_contents,
                    },
                    "page": {"url": source_url, "referrer": ""},
                }],
            }
            if settings.tiktok_test_event_code:
                tt_p["test_event_code"] = settings.tiktok_test_event_code

            headers = {"Access-Token": settings.tiktok_access_token}
            try:
                client.post(
                    "https://business-api.tiktok.com/open_api/v1.3/event/track/",
                    json=tt_p, headers=headers, timeout=4.0
                )
            except Exception as exc:
                logger.error("tiktok_event_error event=%s %s", event_name, exc)

        if settings.snap_pixel_id and settings.snap_capi_token:
            snap_user: dict[str, Any] = {
                "client_ip_address": client_ip,
                "client_user_agent": user_agent,
            }
            snap_p: dict[str, Any] = {
                "data": [{
                    "event_name": snap_event,
                    "event_time": event_time * 1000,
                    "event_id": event_id,
                    "action_source": "WEB",
                    "event_source_url": source_url,
                    "user_data": snap_user,
                    "custom_data": {
                        "currency": currency,
                        "value": value,
                        "content_ids": content_ids,
                        "content_type": "product",
                    },
                }]
            }
            url = (
                f"https://tr.snapchat.com/v3/{settings.snap_pixel_id}"
                f"/events?access_token={settings.snap_capi_token}"
            )
            try:
                client.post(url, json=snap_p, timeout=4.0)
            except Exception as exc:
                logger.error("snap_event_error event=%s %s", event_name, exc)
