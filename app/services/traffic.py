"""
Channel and landing-path helpers shared by checkout, events, and the dashboard.
Click ids win over utm_source. A missing source is direct.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

_SOURCE_CHANNELS = {
    "meta": "meta",
    "facebook": "meta",
    "fb": "meta",
    "instagram": "meta",
    "ig": "meta",
    "tiktok": "tiktok",
    "tt": "tiktok",
    "snap": "snap",
    "snapchat": "snap",
    "google": "google",
    "gads": "google",
    "youtube": "google",
}


def clip(value: object, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


def landing_path(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "/"
    try:
        path = urlparse(raw).path or "/"
    except ValueError:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return path[:180] or "/"


def _query(url: str) -> dict[str, str]:
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return {}
    found = parse_qs(parsed.query)
    return {key: values[0] for key, values in found.items() if values and values[0]}


def merged_attribution(attr: dict | None, source_url: str = "") -> dict[str, str]:
    """Fill blank click ids and UTMs from the landing URL."""
    data = {str(key): "" if value is None else str(value) for key, value in (attr or {}).items()}
    query = _query(source_url)
    for key in ("fbclid", "ttclid", "gclid", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
        if not data.get(key, "").strip() and query.get(key):
            data[key] = query[key]
    snap = query.get("ScCid") or query.get("sccid") or ""
    if not data.get("sc_click_id", "").strip() and snap:
        data["sc_click_id"] = snap
    return data


def channel_from_attribution(attr: dict | None, source_url: str = "") -> str:
    data = merged_attribution(attr, source_url)
    if clip(data.get("fbclid"), 1) or clip(data.get("fbc"), 1):
        return "meta"
    if clip(data.get("ttclid"), 1) or clip(data.get("ttp"), 1):
        return "tiktok"
    if clip(data.get("sc_click_id"), 1) or clip(data.get("sc_cookie"), 1):
        return "snap"
    if clip(data.get("gclid"), 1):
        return "google"

    source = clip(data.get("utm_source"), 80).lower()
    if not source:
        return "direct"
    if source in _SOURCE_CHANNELS:
        return _SOURCE_CHANNELS[source]
    for key, name in _SOURCE_CHANNELS.items():
        if key in source:
            return name
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in source)
    return (cleaned or "other")[:40]
