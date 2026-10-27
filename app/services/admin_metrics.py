"""
Dashboard numbers for the COD store.

Every figure except the excluded panel counts only rows marked geo_qualified:
a public UAE IP that ipapi.is said was not a VPN, proxy, Tor exit, or datacenter.
Dates are Dubai calendar days.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

DUBAI = ZoneInfo("Asia/Dubai")
_CHANNEL_ORDER = ("meta", "tiktok", "snap", "google", "direct")
_OFFER_ORDER = {"1": 0, "2": 1, "3": 2, "upsell": 3}


class RangeError(ValueError):
    pass


def rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except (AttributeError, ValueError) as exc:
        raise RangeError("Use dates like 2026-10-27.") from exc


def resolve_range(
    preset: str,
    raw_from: str | None,
    raw_to: str | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, date, date, str]:
    """Inclusive Dubai dates. The returned end instant is exclusive."""
    now = now or datetime.now(DUBAI)
    now = now.astimezone(DUBAI) if now.tzinfo else now.replace(tzinfo=DUBAI)
    today = now.date()
    chosen = (preset or "7d").strip().lower()

    if raw_from and raw_to:
        date_from = _parse_date(raw_from)
        date_to = _parse_date(raw_to)
        chosen = "custom"
    elif chosen == "today":
        date_from = date_to = today
    elif chosen == "yesterday":
        date_from = date_to = today - timedelta(days=1)
    elif chosen == "7d":
        date_from, date_to = today - timedelta(days=6), today
    elif chosen == "30d":
        date_from, date_to = today - timedelta(days=29), today
    elif chosen == "month":
        date_from, date_to = today.replace(day=1), today
    else:
        raise RangeError("Unknown range.")

    if date_to < date_from:
        raise RangeError("The end date is before the start date.")
    if (date_to - date_from).days > 365:
        raise RangeError("Choose 366 days or fewer.")

    start = datetime.combine(date_from, time.min, tzinfo=DUBAI)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=DUBAI)
    return start, end, date_from, date_to, chosen


def previous_window(date_from: date, date_to: date) -> tuple[datetime, datetime, date, date]:
    span_days = (date_to - date_from).days
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span_days)
    start = datetime.combine(prev_from, time.min, tzinfo=DUBAI)
    end = datetime.combine(prev_to + timedelta(days=1), time.min, tzinfo=DUBAI)
    return start, end, prev_from, prev_to


def assemble_kpis(
    *,
    clicks: int,
    visitors: int,
    product_views: int,
    product_view_people: int,
    add_to_cart: int,
    add_to_cart_people: int,
    checkouts: int,
    checkout_people: int,
    orders: int,
    pending_orders: int,
    revenue_aed: int,
    units: int = 0,
    upsells: int = 0,
    repeat_orders: int = 0,
) -> dict[str, Any]:
    repeat_orders = min(max(repeat_orders, 0), orders)
    return {
        "clicks": clicks,
        "visitors": visitors,
        "product_views": product_views,
        "product_view_people": product_view_people,
        "add_to_cart": add_to_cart,
        "add_to_cart_people": add_to_cart_people,
        "checkouts": checkouts,
        "checkout_people": checkout_people,
        "orders": orders,
        "pending_orders": pending_orders,
        "revenue_aed": revenue_aed,
        "units": units,
        "aov_aed": round(revenue_aed / orders) if orders else None,
        "conversion_rate": rate(orders, clicks),
        "visitor_conversion_rate": rate(orders, visitors),
        "revenue_per_click_aed": round(revenue_aed / clicks, 2) if clicks else None,
        "view_rate": rate(product_view_people, visitors),
        "atc_rate": rate(add_to_cart_people, product_view_people),
        "checkout_rate": rate(checkout_people, add_to_cart_people),
        "order_rate": rate(orders, checkout_people),
        "upsell_rate": rate(upsells, orders),
        "new_orders": orders - repeat_orders,
        "repeat_orders": repeat_orders,
    }


def fill_days(date_from: date, date_to: date, by_day: dict[date, dict[str, int]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = date_from
    while day <= date_to:
        found = by_day.get(day, {})
        rows.append({
            "date": day.isoformat(),
            "clicks": int(found.get("clicks") or 0),
            "visitors": int(found.get("visitors") or 0),
            "orders": int(found.get("orders") or 0),
            "revenue_aed": int(found.get("revenue_aed") or 0),
        })
        day += timedelta(days=1)
    return rows


def _int(value: object) -> int:
    if value is None:
        return 0
    return int(value)


def _day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _params(start: datetime, end: datetime) -> dict[str, datetime]:
    return {"start": start, "end": end}


def _event_counts(db: Session, start: datetime, end: datetime) -> dict[str, tuple[int, int]]:
    rows = db.execute(
        text(
            """
            SELECT event_name,
                   COUNT(*) AS events,
                   COUNT(DISTINCT COALESCE(NULLIF(visitor_id, ''), NULLIF(client_ip, ''))) AS people
            FROM analytics_events
            WHERE geo_qualified
              AND created_at >= :start
              AND created_at < :end
            GROUP BY event_name
            """
        ),
        _params(start, end),
    ).mappings()
    return {row["event_name"]: (_int(row["events"]), _int(row["people"])) for row in rows}


def _order_headline(db: Session, start: datetime, end: datetime) -> dict[str, int]:
    row = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'confirmed') AS orders,
              COUNT(*) FILTER (WHERE status = 'pending_upsell') AS pending_orders,
              COALESCE(SUM(COALESCE(total_aed, merchandise_aed)) FILTER (WHERE status = 'confirmed'), 0) AS revenue_aed,
              COUNT(*) FILTER (WHERE status = 'confirmed' AND upsell_accepted IS TRUE) AS upsells,
              COUNT(*) FILTER (
                WHERE status = 'confirmed' AND sheet_error IS NOT NULL AND sheet_synced_at IS NULL
              ) AS sheet_failed,
              COUNT(*) FILTER (
                WHERE status = 'confirmed' AND capi_error IS NOT NULL AND capi_sent_at IS NULL
              ) AS capi_failed
            FROM orders
            WHERE geo_qualified
              AND created_at >= :start
              AND created_at < :end
            """
        ),
        _params(start, end),
    ).mappings().one()
    return {key: _int(row[key]) for key in row.keys()}


def _repeat_orders(db: Session, start: datetime, end: datetime) -> int:
    value = db.execute(
        text(
            """
            SELECT COUNT(*) AS repeat_orders
            FROM orders o
            WHERE o.geo_qualified
              AND o.status = 'confirmed'
              AND o.created_at >= :start
              AND o.created_at < :end
              AND EXISTS (
                SELECT 1 FROM orders prev
                WHERE prev.phone_e164 = o.phone_e164
                  AND prev.geo_qualified
                  AND prev.status = 'confirmed'
                  AND prev.created_at < o.created_at
              )
            """
        ),
        _params(start, end),
    ).scalar_one()
    return _int(value)


def headline_kpis(db: Session, start: datetime, end: datetime, *, full: bool) -> dict[str, Any]:
    events = _event_counts(db, start, end)
    orders = _order_headline(db, start, end)
    clicks, visitors = events.get("Click", (0, 0))
    views, view_people = events.get("ViewContent", (0, 0))
    atc, atc_people = events.get("AddToCart", (0, 0))
    checks, check_people = events.get("InitiateCheckout", (0, 0))
    return assemble_kpis(
        clicks=clicks,
        visitors=visitors,
        product_views=views,
        product_view_people=view_people,
        add_to_cart=atc,
        add_to_cart_people=atc_people,
        checkouts=checks,
        checkout_people=check_people,
        orders=orders["orders"],
        pending_orders=orders["pending_orders"],
        revenue_aed=orders["revenue_aed"],
        units=0,
        upsells=orders["upsells"] if full else 0,
        repeat_orders=_repeat_orders(db, start, end) if full else 0,
    ) | ({"sheet_failed": orders["sheet_failed"], "capi_failed": orders["capi_failed"]} if full else {})


def _series(db: Session, date_from: date, date_to: date, start: datetime, end: datetime) -> list[dict[str, Any]]:
    by_day: dict[date, dict[str, int]] = {}
    event_rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Dubai')::date AS day,
                   COUNT(*) FILTER (WHERE event_name = 'Click') AS clicks,
                   COUNT(DISTINCT COALESCE(NULLIF(visitor_id, ''), NULLIF(client_ip, '')))
                     FILTER (WHERE event_name = 'Click') AS visitors
            FROM analytics_events
            WHERE geo_qualified
              AND created_at >= :start
              AND created_at < :end
            GROUP BY 1
            """
        ),
        _params(start, end),
    ).mappings()
    for row in event_rows:
        by_day[_day(row["day"])] = {"clicks": _int(row["clicks"]), "visitors": _int(row["visitors"])}

    order_rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Dubai')::date AS day,
                   COUNT(*) FILTER (WHERE status = 'confirmed') AS orders,
                   COALESCE(SUM(COALESCE(total_aed, merchandise_aed)) FILTER (WHERE status = 'confirmed'), 0) AS revenue_aed
            FROM orders
            WHERE geo_qualified
              AND created_at >= :start
              AND created_at < :end
            GROUP BY 1
            """
        ),
        _params(start, end),
    ).mappings()
    for row in order_rows:
        slot = by_day.setdefault(_day(row["day"]), {})
        slot["orders"] = _int(row["orders"])
        slot["revenue_aed"] = _int(row["revenue_aed"])
    return fill_days(date_from, date_to, by_day)


def _sort_channels(names: set[str]) -> list[str]:
    def key(name: str) -> tuple[int, int | str]:
        if name in _CHANNEL_ORDER:
            return (0, _CHANNEL_ORDER.index(name))
        return (1, name)

    return sorted(names, key=key)


def _channels(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    clicks: dict[str, int] = {}
    for row in db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(channel, ''), 'direct') AS channel, COUNT(*) AS clicks
            FROM analytics_events
            WHERE geo_qualified AND event_name = 'Click'
              AND created_at >= :start AND created_at < :end
            GROUP BY 1
            """
        ),
        _params(start, end),
    ).mappings():
        clicks[row["channel"]] = _int(row["clicks"])

    orders: dict[str, tuple[int, int]] = {}
    for row in db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(channel, ''), 'direct') AS channel,
                   COUNT(*) FILTER (WHERE status = 'confirmed') AS orders,
                   COALESCE(SUM(COALESCE(total_aed, merchandise_aed)) FILTER (WHERE status = 'confirmed'), 0) AS revenue_aed
            FROM orders
            WHERE geo_qualified
              AND created_at >= :start AND created_at < :end
            GROUP BY 1
            """
        ),
        _params(start, end),
    ).mappings():
        orders[row["channel"]] = (_int(row["orders"]), _int(row["revenue_aed"]))

    rows = []
    for name in _sort_channels(set(clicks) | set(orders)):
        order_count, revenue = orders.get(name, (0, 0))
        click_count = clicks.get(name, 0)
        if click_count == 0 and order_count == 0 and revenue == 0:
            continue
        rows.append({
            "channel": name,
            "clicks": click_count,
            "orders": order_count,
            "revenue_aed": revenue,
            "conversion_rate": rate(order_count, click_count),
        })
    return rows


def _campaigns(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    clicks: dict[tuple[str, str], int] = {}
    for row in db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(channel, ''), 'direct') AS channel,
                   utm_campaign AS campaign,
                   COUNT(*) AS clicks
            FROM analytics_events
            WHERE geo_qualified AND event_name = 'Click' AND utm_campaign <> ''
              AND created_at >= :start AND created_at < :end
            GROUP BY 1, 2
            """
        ),
        _params(start, end),
    ).mappings():
        clicks[(row["channel"], row["campaign"])] = _int(row["clicks"])

    orders: dict[tuple[str, str], tuple[int, int]] = {}
    for row in db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(channel, ''), 'direct') AS channel,
                   COALESCE(attribution->>'utm_campaign', '') AS campaign,
                   COUNT(*) FILTER (WHERE status = 'confirmed') AS orders,
                   COALESCE(SUM(COALESCE(total_aed, merchandise_aed)) FILTER (WHERE status = 'confirmed'), 0) AS revenue_aed
            FROM orders
            WHERE geo_qualified
              AND created_at >= :start AND created_at < :end
              AND COALESCE(attribution->>'utm_campaign', '') <> ''
            GROUP BY 1, 2
            """
        ),
        _params(start, end),
    ).mappings():
        orders[(row["channel"], row["campaign"])] = (_int(row["orders"]), _int(row["revenue_aed"]))

    merged = []
    for key in set(clicks) | set(orders):
        channel, campaign = key
        order_count, revenue = orders.get(key, (0, 0))
        click_count = clicks.get(key, 0)
        merged.append({
            "channel": channel,
            "campaign": campaign,
            "clicks": click_count,
            "orders": order_count,
            "revenue_aed": revenue,
            "conversion_rate": rate(order_count, click_count),
        })
    merged.sort(key=lambda row: (row["orders"], row["clicks"], row["revenue_aed"]), reverse=True)
    return merged[:20]


def _line_rows(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT COALESCE(line->>'slug', '') AS slug,
                   COALESCE(line->>'name_ar', '') AS name_ar,
                   COALESCE(line->>'offer_code', '') AS offer_code,
                   COALESCE(SUM(
                     CASE WHEN (line->>'pieces') ~ '^[0-9]+$' THEN (line->>'pieces')::int ELSE 0 END
                   ), 0) AS units,
                   COALESCE(SUM(
                     CASE WHEN (line->>'unit_price_aed') ~ '^[0-9]+$' THEN (line->>'unit_price_aed')::int ELSE 0 END
                   ), 0) AS revenue_aed,
                   COUNT(DISTINCT o.id) AS orders
            FROM orders o
            CROSS JOIN LATERAL jsonb_array_elements(
              CASE WHEN jsonb_typeof(o.lines) = 'array' THEN o.lines ELSE '[]'::jsonb END
            ) AS line
            WHERE o.geo_qualified
              AND o.status = 'confirmed'
              AND o.created_at >= :start
              AND o.created_at < :end
              AND jsonb_typeof(line) = 'object'
            GROUP BY 1, 2, 3
            """
        ),
        _params(start, end),
    ).mappings()
    return [dict(row) for row in rows]


def _products_and_offers(line_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    products: dict[str, dict[str, Any]] = {}
    offers: dict[str, dict[str, Any]] = {}
    units = 0
    for row in line_rows:
        slug = row["slug"] or "unknown"
        slot = products.setdefault(slug, {
            "slug": slug,
            "name_ar": row["name_ar"] or slug,
            "orders": 0,
            "units": 0,
            "revenue_aed": 0,
        })
        if row["name_ar"]:
            slot["name_ar"] = row["name_ar"]
        slot["orders"] += _int(row["orders"])
        slot["units"] += _int(row["units"])
        slot["revenue_aed"] += _int(row["revenue_aed"])
        units += _int(row["units"])

        code = row["offer_code"] or "unknown"
        offer = offers.setdefault(code, {"offer_code": code, "orders": 0, "units": 0, "revenue_aed": 0})
        offer["orders"] += _int(row["orders"])
        offer["units"] += _int(row["units"])
        offer["revenue_aed"] += _int(row["revenue_aed"])

    product_rows = sorted(products.values(), key=lambda item: (item["revenue_aed"], item["orders"]), reverse=True)
    offer_rows = sorted(offers.values(), key=lambda item: (_OFFER_ORDER.get(item["offer_code"], 9), item["offer_code"]))
    return product_rows, offer_rows, units


def _pages(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(landing_path, ''), '/') AS path, COUNT(*) AS clicks
            FROM analytics_events
            WHERE geo_qualified AND event_name = 'Click'
              AND created_at >= :start AND created_at < :end
            GROUP BY 1
            ORDER BY clicks DESC
            LIMIT 8
            """
        ),
        _params(start, end),
    ).mappings()
    return [{"path": row["path"], "clicks": _int(row["clicks"])} for row in rows]


def _excluded(db: Session, start: datetime, end: datetime) -> dict[str, Any]:
    def grouped(sql: str) -> dict[str, int]:
        found: dict[str, int] = {}
        for row in db.execute(text(sql), _params(start, end)).mappings():
            found[row["code"]] = _int(row["n"])
        return found

    events = grouped(
        """
        SELECT geo_code AS code, COUNT(*) AS n
        FROM analytics_events
        WHERE NOT geo_qualified AND geo_code <> ''
          AND created_at >= :start AND created_at < :end
        GROUP BY 1
        """
    )
    orders = grouped(
        """
        SELECT geo_code AS code, COUNT(*) AS n
        FROM orders
        WHERE NOT geo_qualified AND geo_code <> ''
          AND created_at >= :start AND created_at < :end
        GROUP BY 1
        """
    )
    unclassified_events = _int(db.execute(
        text(
            """
            SELECT COUNT(*) FROM analytics_events
            WHERE NOT geo_qualified AND geo_code = ''
              AND created_at >= :start AND created_at < :end
            """
        ),
        _params(start, end),
    ).scalar_one())
    codes = sorted(set(events) | set(orders))
    return {
        "events": sum(events.values()),
        "orders": sum(orders.values()),
        "unclassified_events": unclassified_events,
        "by_code": [
            {"code": code, "events": events.get(code, 0), "orders": orders.get(code, 0)}
            for code in codes
            if events.get(code, 0) or orders.get(code, 0)
        ],
    }


def _stock(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT slug, name_ar, stock, active, scarcity_threshold
            FROM products
            ORDER BY sort, slug
            """
        )
    ).mappings()
    return [
        {
            "slug": row["slug"],
            "name_ar": row["name_ar"],
            "stock": _int(row["stock"]),
            "active": bool(row["active"]),
            "low": bool(row["active"]) and _int(row["stock"]) <= _int(row["scarcity_threshold"]),
        }
        for row in rows
    ]


def _item_label(lines: object) -> str:
    if not isinstance(lines, list):
        return ""
    parts: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        name = str(line.get("name_ar") or line.get("slug") or "").strip()
        pieces = line.get("pieces") or 1
        if name:
            parts.append(f"{name} ×{pieces}")
    return " · ".join(parts)


def _recent_orders(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT public_id, status, customer_name, phone_local, total_aed, merchandise_aed,
                   channel, upsell_accepted, lines, attribution, created_at,
                   sheet_synced_at, sheet_error, capi_error, capi_sent_at
            FROM orders
            WHERE geo_qualified
              AND created_at >= :start AND created_at < :end
            ORDER BY created_at DESC
            LIMIT 40
            """
        ),
        _params(start, end),
    ).mappings()
    result = []
    for row in rows:
        attribution = row["attribution"] if isinstance(row["attribution"], dict) else {}
        result.append({
            "public_id": row["public_id"],
            "status": row["status"],
            "customer_name": row["customer_name"],
            "phone_local": row["phone_local"],
            "total_aed": row["total_aed"] if row["total_aed"] is not None else row["merchandise_aed"],
            "channel": row["channel"] or "direct",
            "campaign": str(attribution.get("utm_campaign") or ""),
            "items": _item_label(row["lines"]),
            "upsell_accepted": row["upsell_accepted"],
            "created_at": _iso(row["created_at"]),
            "sheet_synced_at": _iso(row["sheet_synced_at"]),
            "sheet_error": row["sheet_error"],
            "capi_error": None if row["capi_sent_at"] else row["capi_error"],
        })
    return result


def build_report(
    db: Session,
    preset: str,
    raw_from: str | None,
    raw_to: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    start, end, date_from, date_to, chosen = resolve_range(preset, raw_from, raw_to, now)
    prev_start, prev_end, prev_from, prev_to = previous_window(date_from, date_to)
    current = headline_kpis(db, start, end, full=True)
    previous = headline_kpis(db, prev_start, prev_end, full=False)
    line_rows = _line_rows(db, start, end)
    products, offers, units = _products_and_offers(line_rows)
    current["units"] = units
    return {
        "range": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "preset": chosen,
            "timezone": "Asia/Dubai",
        },
        "comparison": {"from": prev_from.isoformat(), "to": prev_to.isoformat()},
        "filter": {
            "qualified_only": True,
            "rule": "Public UAE IPs that are not a VPN, proxy, Tor exit, or datacenter.",
        },
        "kpis": current,
        "previous": previous,
        "series": _series(db, date_from, date_to, start, end),
        "channels": _channels(db, start, end),
        "campaigns": _campaigns(db, start, end),
        "products": products,
        "offers": offers,
        "pages": _pages(db, start, end),
        "stock": _stock(db),
        "orders": _recent_orders(db, start, end),
        "excluded": _excluded(db, start, end),
        "ops": {
            "sheet_failed": current.pop("sheet_failed"),
            "capi_failed": current.pop("capi_failed"),
            "pending_orders": current["pending_orders"],
        },
    }
