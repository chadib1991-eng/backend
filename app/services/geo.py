"""
MaxMind GeoIP Insights gate for checkout.

An order is allowed only when the client IP is in the UAE, is not a VPN,
proxy, Tor exit, or hosting network, and its IP risk snapshot is under the
configured threshold. One test phone can skip the check.
"""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote

import httpx

from app.settings import settings
from app.services.phone import parse_uae_mobile

logger = logging.getLogger(__name__)

_INSIGHTS_URL = "https://geoip.maxmind.com/geoip/v2.1/insights/{ip}"

MSG_OUTSIDE = "الطلب متاح داخل الإمارات فقط"
MSG_VPN = "طفي الـ VPN وجربي مرة ثانية. الطلب داخل الإمارات بس"
MSG_SUSPICIOUS = "ما نقدر نأكد الطلب من هذا الاتصال. جربي بيانات الجوال أو واي فاي البيت"
MSG_UNAVAILABLE = "ما قدرنا نتأكد من الاتصال. جربي بعد شوي"


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


def _flag(data: dict, key: str) -> bool:
    for section in ("anonymizer", "traits"):
        block = data.get(section)
        if isinstance(block, dict) and block.get(key):
            return True
    return False


def assess_insights(data: dict, risk_threshold: float) -> GeoVerdict:
    country = data.get("country") if isinstance(data.get("country"), dict) else {}
    iso = str(country.get("iso_code") or "").upper()
    if iso != "AE":
        return GeoVerdict(False, "outside_uae", MSG_OUTSIDE)

    if _flag(data, "is_anonymous_vpn"):
        return GeoVerdict(False, "vpn", MSG_VPN)

    suspicious_flags = (
        "is_anonymous",
        "is_public_proxy",
        "is_residential_proxy",
        "is_tor_exit_node",
        "is_hosting_provider",
    )
    if any(_flag(data, key) for key in suspicious_flags):
        return GeoVerdict(False, "suspicious", MSG_SUSPICIOUS)

    traits = data.get("traits") if isinstance(data.get("traits"), dict) else {}
    raw_score = traits.get("ip_risk_snapshot")
    if raw_score is not None:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = None
        if score is not None and score >= risk_threshold:
            return GeoVerdict(False, "suspicious", MSG_SUSPICIOUS)

    return GeoVerdict(True, "ok", "")


def check_order_ip(ip: str) -> GeoVerdict:
    """Call MaxMind. Any failure blocks the order."""
    if not settings.maxmind_account_id or not settings.maxmind_license_key:
        logger.error("MaxMind credentials are missing; blocking checkout")
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    if not is_public_ip(ip):
        logger.warning("Checkout IP is not a public address: %s", ip or "(empty)")
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    url = _INSIGHTS_URL.format(ip=quote(ip, safe=":"))
    try:
        response = httpx.get(
            url,
            auth=(settings.maxmind_account_id, settings.maxmind_license_key),
            headers={"Accept": "application/json"},
            timeout=4.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("MaxMind request failed for %s: %s", ip, exc)
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    if response.status_code != 200:
        logger.warning(
            "MaxMind HTTP %s for %s: %s",
            response.status_code,
            ip,
            response.text[:200],
        )
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    try:
        payload = response.json()
    except ValueError:
        logger.warning("MaxMind returned non-JSON for %s", ip)
        return GeoVerdict(False, "unavailable", MSG_UNAVAILABLE)

    verdict = assess_insights(payload, settings.maxmind_risk_threshold)
    if not verdict.allowed:
        logger.info("Checkout blocked ip=%s code=%s", ip, verdict.code)
    return verdict
