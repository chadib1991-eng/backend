"""Dashboard math, date windows, and traffic classification. No database."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.services.admin_metrics import RangeError, assemble_kpis, fill_days, previous_window, rate, resolve_range
from app.services.ip_cache import QualifiedIP, qualify_ip, verdict_is_fresh
from app.services.traffic import channel_from_attribution, landing_path
from app.routers.events import EventPayload


NOW = datetime(2026, 10, 27, 15, tzinfo=timezone.utc)


def test_rates_and_order_value():
    kpis = assemble_kpis(
        clicks=100,
        visitors=80,
        product_views=120,
        product_view_people=70,
        add_to_cart=40,
        add_to_cart_people=30,
        checkouts=20,
        checkout_people=18,
        orders=10,
        pending_orders=2,
        revenue_aed=1990,
        units=14,
        upsells=3,
        repeat_orders=2,
    )
    assert kpis["conversion_rate"] == 0.1
    assert kpis["aov_aed"] == 199
    assert kpis["revenue_per_click_aed"] == 19.9
    assert kpis["new_orders"] == 8
    assert kpis["repeat_orders"] == 2
    assert kpis["upsell_rate"] == 0.3
    assert rate(1, 0) is None


def test_dubai_windows_are_inclusive():
    start, end, date_from, date_to, preset = resolve_range("today", None, None, now=NOW)
    assert preset == "today"
    assert date_from == date_to == date(2026, 10, 27)
    assert (end - start) == timedelta(days=1)
    assert start.utcoffset() == timedelta(hours=4)

    start, end, date_from, date_to, preset = resolve_range("7d", None, None, now=NOW)
    assert date_from == date(2026, 10, 21)
    assert date_to == date(2026, 10, 27)
    assert preset == "7d"

    start, end, date_from, date_to, preset = resolve_range("ignored", "2026-10-01", "2026-10-03", now=NOW)
    assert preset == "custom"
    assert (end - start) == timedelta(days=3)

    prev_start, prev_end, prev_from, prev_to = previous_window(date(2026, 10, 21), date(2026, 10, 27))
    assert prev_from == date(2026, 10, 14)
    assert prev_to == date(2026, 10, 20)
    assert (prev_end - prev_start) == timedelta(days=7)


def test_bad_ranges_are_rejected():
    with pytest.raises(RangeError):
        resolve_range("custom", "2026-10-05", "2026-10-01", now=NOW)
    with pytest.raises(RangeError):
        resolve_range("nope", None, None, now=NOW)
    with pytest.raises(RangeError):
        resolve_range("custom", "27-10-2026", "28-10-2026", now=NOW)


def test_missing_days_are_filled_with_zeros():
    rows = fill_days(date(2026, 10, 1), date(2026, 10, 3), {date(2026, 10, 2): {"clicks": 4, "orders": 1}})
    assert [row["clicks"] for row in rows] == [0, 4, 0]
    assert rows[1]["orders"] == 1
    assert len(rows) == 3


def test_channel_uses_click_ids_before_utm():
    assert channel_from_attribution({"fbclid": "abc", "utm_source": "tiktok"}) == "meta"
    assert channel_from_attribution({"ttclid": "abc"}) == "tiktok"
    assert channel_from_attribution({"sc_click_id": "abc"}) == "snap"
    assert channel_from_attribution({}, "https://sababreeze.com/?gclid=xyz") == "google"
    assert channel_from_attribution({"utm_source": "instagram"}) == "meta"
    assert channel_from_attribution({}) == "direct"
    assert landing_path("https://sababreeze.com/products/balasm-al-shaar?fbclid=1") == "/products/balasm-al-shaar"
    assert landing_path("") == "/"


def test_click_is_stored_and_purchase_is_rejected():
    event = EventPayload(event_name="Click", event_id="evt-1", event_time=1, source_url="https://sababreeze.com/")
    assert event.event_name == "Click"
    with pytest.raises(ValidationError):
        EventPayload(event_name="Purchase", event_id="SB-1", event_time=1)


def _no_network(ip):
    raise AssertionError("network")


def test_ip_cache_keeps_a_fresh_uae_verdict(monkeypatch):
    monkeypatch.setattr("app.services.ip_cache.lookup_ip_details", _no_network)
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    row = type("Row", (), {})()
    row.allowed = True
    row.code = "ok"
    row.country_code = "AE"
    row.checked_at = now - timedelta(hours=2)

    class DB:
        def get(self, model, ip):
            assert ip == "94.200.1.10"
            return row

    found = qualify_ip(DB(), "94.200.1.10", now=now)
    assert found == QualifiedIP(True, "ok", "AE")


def test_private_ip_is_not_qualified_and_does_not_call_ipapi(monkeypatch):
    monkeypatch.setattr("app.services.ip_cache.lookup_ip_details", _no_network)

    class DB:
        def get(self, model, ip):
            raise AssertionError("private addresses are not cached")

    found = qualify_ip(DB(), "127.0.0.1")
    assert found.allowed is False
    assert found.code == "unavailable"


def test_stale_vpn_verdict_is_refreshed(monkeypatch):
    from app.services.geo import GeoVerdict

    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    row = type("Row", (), {})()
    row.allowed = False
    row.code = "vpn"
    row.country_code = "AE"
    row.checked_at = now - timedelta(days=2)
    monkeypatch.setattr(
        "app.services.ip_cache.lookup_ip_details",
        lambda ip: (GeoVerdict(True, "ok", ""), "AE"),
    )

    class DB:
        def get(self, model, ip):
            return row

    found = qualify_ip(DB(), "94.200.1.10", now=now)
    assert found.allowed is True
    assert row.code == "ok"
    assert verdict_is_fresh("ok", now, now) is True
    assert verdict_is_fresh("unavailable", now - timedelta(minutes=20), now) is False
