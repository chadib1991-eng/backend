"""
Pricing tests. Does not require a database.
"""
import pytest
from unittest.mock import MagicMock

from app.services.pricing import price_for, choose_upsell


def make_product(slug="razaz-al-shaar", price_1=199, price_2=279, price_3=349, upsell=99):
    p = MagicMock()
    p.slug = slug
    p.price_1 = price_1
    p.price_2 = price_2
    p.price_3 = price_3
    p.upsell_price = upsell
    return p


def test_price_for_1():
    p = make_product()
    pieces, price = price_for(p, "1")
    assert pieces == 1
    assert price == 199


def test_price_for_2():
    p = make_product()
    pieces, price = price_for(p, "2")
    assert pieces == 2
    assert price == 279


def test_price_for_3():
    p = make_product()
    pieces, price = price_for(p, "3")
    assert pieces == 3
    assert price == 349


def test_price_for_upsell():
    p = make_product()
    pieces, price = price_for(p, "upsell")
    assert pieces == 1
    assert price == 99


def test_price_for_unknown():
    p = make_product()
    with pytest.raises(ValueError):
        price_for(p, "4")


def test_upsell_picker_cream_first():
    """Cream is offered first when mist is in the cart."""
    all_slugs = ["razaz-al-shaar", "kareem-al-intiash", "qalam-al-kaab"]
    upsell = choose_upsell(["razaz-al-shaar"], all_slugs)
    assert upsell == "kareem-al-intiash"


def test_upsell_picker_mist_second():
    """Mist is offered when cream and heel are in the cart."""
    all_slugs = ["razaz-al-shaar", "kareem-al-intiash", "qalam-al-kaab"]
    upsell = choose_upsell(["kareem-al-intiash", "qalam-al-kaab"], all_slugs)
    assert upsell == "razaz-al-shaar"


def test_upsell_picker_heel_last():
    """Heel is offered last when only heel is missing."""
    all_slugs = ["razaz-al-shaar", "kareem-al-intiash", "qalam-al-kaab"]
    upsell = choose_upsell(["razaz-al-shaar", "kareem-al-intiash"], all_slugs)
    assert upsell == "qalam-al-kaab"


def test_upsell_picker_none_when_full():
    """No upsell when all three products are in the cart."""
    all_slugs = ["razaz-al-shaar", "kareem-al-intiash", "qalam-al-kaab"]
    upsell = choose_upsell(all_slugs, all_slugs)
    assert upsell is None


def test_upsell_99_only():
    """The upsell offer code returns price 99, not 199/279/349."""
    p = make_product(upsell=99)
    _, price = price_for(p, "upsell")
    assert price == 99
    assert price != 199
