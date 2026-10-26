"""Retired product slugs still resolve to the live catalog."""
from app.catalog_seed import canonical_slug, resolve_cart_lines


def test_retired_lotion_slug():
    assert canonical_slug("kareem-al-intiash") == "loshn-al-jism"
    assert canonical_slug("kareem al intiash") == "loshn-al-jism"


def test_other_retired_slugs():
    assert canonical_slug("razaz-al-shaar") == "balasm-al-shaar"
    assert canonical_slug("qalam-al-kaab") == "roll-al-kaab"


def test_live_slug_unchanged():
    assert canonical_slug("loshn-al-jism") == "loshn-al-jism"


def test_cart_keeps_live_offer_when_both_names_are_present():
    resolved = resolve_cart_lines(
        [
            ("kareem-al-intiash", "1"),
            ("balasm-al-shaar", "3"),
            ("loshn-al-jism", "2"),
        ]
    )
    assert resolved == [
        ("loshn-al-jism", "2"),
        ("balasm-al-shaar", "3"),
    ]


def test_old_slug_alone_checks_out_as_the_lotion():
    assert resolve_cart_lines([("kareem al intiash", "3")]) == [("loshn-al-jism", "3")]
