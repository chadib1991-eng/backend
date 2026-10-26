"""
Price authority for the backend.
The HTTP layer calls price_for() and ignores any client-supplied price.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Product

# Upsell priority: lotion first, hair mist second, foot roll third
UPSELL_PRIORITY = ["loshn-al-jism", "balasm-al-shaar", "roll-al-kaab"]


def price_for(product: "Product", offer_code: str) -> tuple[int, int]:
    """
    Returns (pieces, price_aed).
    offer_code: "1" | "2" | "3" | "upsell"
    Raises ValueError for unknown codes.
    """
    if offer_code == "1":
        return 1, product.price_1
    if offer_code == "2":
        return 2, product.price_2
    if offer_code == "3":
        return 3, product.price_3
    if offer_code == "upsell":
        return 1, product.upsell_price
    raise ValueError(f"Unknown offer_code: {offer_code!r}")


def choose_upsell(
    cart_slugs: list[str],
    all_slugs: list[str],
) -> str | None:
    """
    First match in UPSELL_PRIORITY that is not in the cart.
    Returns None if cart contains every product.
    """
    cart_set = set(cart_slugs)
    for slug in UPSELL_PRIORITY:
        if slug in all_slugs and slug not in cart_set:
            return slug
    return None
