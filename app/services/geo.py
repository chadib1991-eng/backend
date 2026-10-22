"""
ipapi.is gate for checkout.

An order is allowed only when the client IP is in the UAE and is not a VPN,
proxy, Tor exit, datacenter, or known abuser. One test phone can skip the check.

The free plan is 1,000 lookups a day and includes commercial use. A key is
required: keyless responses omit the VPN and proxy flags.
https://ipapi.is/developers.html
"""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Mapping

import httpx

from app.settings import settings
from app.services.phone import parse_uae_mobile

logger = logging.getLogger(__name__)

_LOOKUP_URL = "https://api.ipapi.is"

MSG_OUTSIDE = "الطلب متاح داخل الإمارات فقط"
MSG_VPN = "طفي الـ VPN وجربي مرة ثانية. الطلب داخل الإمارات بس"
MSG_SUSPICIOUS = "ما نقدر نأكد الطلب من هذا الاتصال. جربي بيانات الجوال أو واي فاي البيت"
MSG_UNAVAILABLE = "ما قدرنا نتأكد من الاتصال. جربي بعد شوي"

_SUSPICIOUS_FLAGS = ("is_proxy", "is_tor", "is_datacenter", "is_abuser")


@dataclass(frozen=True)
class GeoVerdict:
    allowed: bool
    code: str
    message: str


def _parse_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    text = (raw or "").strip().strip("[]")
    if "%" in text:
        text = text.split("%", 1)[0]
    if not text:
        return None
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def is_public_ip(raw: str) -> bool:
    addr = _parse_ip(raw)
    return bool(addr and addr.is_global)


def extract_client_ip(headers: Mapping[str, str], peer: str = "") -> str:
    """
    Prefer the address the nearest proxy actually saw.

    EasyPanel's proxy appends that address as the last X-Forwarded-For hop.
    A public TCP peer is used as-is, so a direct connection cannot spoof a header.
    """
    peer = (peer or "").strip()
    if is_public_ip(peer):
        return peer

    forwarded = headers.get("x-forwarded-for", "") or ""
    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if hops:
        return hops[-1]

    real = (headers.get("x-real-ip") or "").strip()
    if real:
        return real
    return peer


def is_bypass_phone(e164: str) -> bool:
    allowed: set[str] = set()
    for raw in settings.checkout_bypass_phones.split(","):
        parsed = parse_uae_mobile(raw.strip())
        if parsed:
            allowed.add(parsed.e164)
    return e164 in allowed


def _on(value: object) -> bool:
    """ipapi.is says is_vpn can be truthy without being JSON true."""
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "null"}
    return bool(value)


def assess_lookup(data: dict) -> GeoVerdict:
    if data.get("error") or data.get("error_code"):
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)
    if data.get("is_bogon"):
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)
    # Keyless responses have a country and no detection flags. Do not treat that as clean.
    if "is_vpn" not in data or "is_proxy" not in data:
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    location = data.get("location") if isinstance(data.get("location"), dict) else {}
    iso = str(location.get("country_code") or "").upper()
    if iso != "AE":
        return GeoVerdict(False, "outside_uae", MSG_OUTSIDE)

    if _on(data.get("is_vpn")):
        return GeoVerdict(False, "vpn", MSG_VPN)

    if any(_on(data.get(flag)) for flag in _SUSPICIOUS_FLAGS):
        return GeoVerdict(False, "suspicious", MSG_SUSPICIOUS)

    return GeoVerdict(True, "ok", "")


def check_order_ip(ip: str) -> GeoVerdict:
    """Call ipapi.is. Any failure blocks the order."""
    if not settings.ipapi_key:
        logger.error("IPAPI_KEY is missing; blocking checkout")
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    if not is_public_ip(ip):
        logger.warning("Checkout IP is not a public address: %s", ip or "(empty)")
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    try:
        response = httpx.post(
            _LOOKUP_URL,
            json={"q": ip, "key": settings.ipapi_key},
            headers={"Accept": "application/json"},
            timeout=4.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("ipapi.is request failed for %s: %s", ip, exc)
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    try:
        payload = response.json()
    except ValueError:
        logger.warning("ipapi.is returned non-JSON for %s (HTTP %s)", ip, response.status_code)
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    if response.status_code != 200 or not isinstance(payload, dict):
        logger.warning(
            "ipapi.is HTTP %s for %s: %s",
            response.status_code,
            ip,
            str(payload)[:200],
        )
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    verdict = assess_lookup(payload)
    if not verdict.allowed:
        logger.info("Checkout blocked ip=%s code=%s", ip, verdict.code)
    return verdict
