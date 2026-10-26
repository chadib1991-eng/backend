from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.sheets import order_sheet_row


def _order():
    # 22:30 UTC is 02:30 the next day in Dubai.
    return SimpleNamespace(
        public_id="SB-100241",
        created_at=datetime(2026, 4, 1, 22, 30, tzinfo=timezone.utc),
        customer_name="ميثة",
        phone_e164="+971501234567",
        total_aed=478,
        merchandise_aed=279,
        lines=[
            {"slug": "balasm-al-shaar", "name_ar": "رذاذ بلسم الشعر الخفيف", "sku": "SABA-LEAVEIN", "pieces": 2},
            {"slug": "loshn-al-jism", "name_ar": "لوشن ترطيب الجسم", "sku": "SABA-LOTION", "pieces": 2},
            {"slug": "roll-al-kaab", "name_ar": "رول الكعب باليوريا 20%", "pieces": 1},
        ],
    )


def test_sheet_row_matches_orders_columns():
    row = order_sheet_row(_order())
    assert row == {
        "date": "02/04/2026",
        "orderid": "saba100241",
        "country": "uae",
        "name": "ميثة",
        "phone": "+971501234567",
        "product": "رذاذ بلسم الشعر الخفيف/لوشن ترطيب الجسم/رول الكعب باليوريا 20%",
        "sku": "SABA-LEAVEIN/SABA-LOTION/SABA-FOOTROLL",
        "quantity": "2/2/1",
        "totalprice": 478,
        "currency": "AED",
        "status": "",
    }
