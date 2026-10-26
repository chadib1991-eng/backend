"""
Catalog source of truth for the three products on the shelf.

1. Weightless leave-in conditioning hair mist, 100 ml
2. Moisturizing body lotion, 160 g — niacinamide, PDRN, hyaluronic acid, shea, ocean breeze
3. 20% urea foot roll-on, 50 ml — vitamin E and olive oil

Upsell priority: lotion first, hair mist second, foot roll third.
Sort order for menus: hair mist 1, lotion 2, foot roll 3.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select

logger = logging.getLogger(__name__)

HAIR = "balasm-al-shaar"
LOTION = "loshn-al-jism"
FOOT = "roll-al-kaab"

# Carts saved before the rename. Keep in sync with frontend/lib/slugs.ts and next.config.ts.
SLUG_ALIASES = {
    "razaz-al-shaar": HAIR,
    "kareem-al-intiash": LOTION,
    "qalam-al-kaab": FOOT,
}


def canonical_slug(slug: str) -> str:
    text = re.sub(r"\s+", "-", (slug or "").strip().lower())
    return SLUG_ALIASES.get(text, text)


def resolve_cart_lines(lines: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    (slug, offer_code) pairs.
    A retired slug becomes the live product.
    If both are in the cart, the live line's offer wins.
    """
    order: list[str] = []
    chosen: dict[str, tuple[str, str]] = {}
    for slug, offer_code in lines:
        raw = re.sub(r"\s+", "-", (slug or "").strip().lower())
        canonical = SLUG_ALIASES.get(raw, raw)
        if not canonical:
            continue
        if canonical not in chosen:
            order.append(canonical)
            chosen[canonical] = (canonical, offer_code)
        elif raw == canonical:
            chosen[canonical] = (canonical, offer_code)
    return [chosen[key] for key in order]


HAIR_INGREDIENTS = [
    {"name": "بلسم بدون شطف", "detail": "رذاذ يُترك على الشعر. 100 مل. ما يحتاج شطف."},
    {"name": "ترطيب", "detail": "مكتوب على العبوة. يرطّب الشعر من غير ما يثقله."},
    {"name": "ضد الهيشان", "detail": "يهدّي مظهر الشعر الهايش بعد الحر والمكيف."},
    {"name": "فك التشابك", "detail": "يساعد المشط يمشي على الشعر بسهولة."},
]

LOTION_INGREDIENTS = [
    {"name": "نياسيناميد", "detail": "مكتوب على العبوة. مكوّن معروف بدعم مظهر البشرة مع الاستخدام المنتظم."},
    {"name": "PDRN", "detail": "مكتوب على العبوة مع الهيالورون. مكوّن ترطيب في عناية الجسم."},
    {"name": "حمض الهيالورونيك", "detail": "يمسك الرطوبة على البشرة."},
    {"name": "زبدة الشيا", "detail": "تغذية ناعمة. اللوشن غير دهني."},
    {"name": "نسيم البحر", "detail": "ريحة العبوة. خفيفة، مو عطر ثقيل."},
]

FOOT_INGREDIENTS = [
    {"name": "يوريا 20%", "detail": "المكوّن المكتوب على العبوة لترطيب الكعب الجاف والخشن."},
    {"name": "فيتامين E", "detail": "مع اليوريا في التركيبة."},
    {"name": "زيت الزيتون", "detail": "انزلاق الرول وترطيب الموضع."},
    {"name": "خالي من البارابين", "detail": "مكتوب على العبوة."},
]

PRODUCTS = [
    {
        "slug": HAIR,
        "sku": "SABA-LEAVEIN",
        "nav_ar": "بلسم الشعر",
        "name_ar": "رذاذ بلسم الشعر الخفيف",
        "category": "hair",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 1,
        "ingredients": HAIR_INGREDIENTS,
        "images": ["/images/hair-mist.png"],
    },
    {
        "slug": LOTION,
        "sku": "SABA-LOTION",
        "nav_ar": "لوشن الجسم",
        "name_ar": "لوشن ترطيب الجسم",
        "category": "body",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 2,
        "ingredients": LOTION_INGREDIENTS,
        "images": ["/images/body-lotion.png"],
    },
    {
        "slug": FOOT,
        "sku": "SABA-FOOTROLL",
        "nav_ar": "رول الكعب",
        "name_ar": "رول الكعب باليوريا 20%",
        "category": "heel",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 3,
        "ingredients": FOOT_INGREDIENTS,
        "images": ["/images/foot-roll.png"],
    },
]

# Sample cards. source="sample" always shows the نموذج ribbon.
REVIEWS = [
    {
        "id": "sample-mist-1",
        "product_slug": HAIR,
        "source": "sample",
        "name": "ميثة",
        "body": "أرشه في الشنطة. الرشة الثانية بعد الدوام تهدّي الهيشان.",
    },
    {
        "id": "sample-mist-2",
        "product_slug": HAIR,
        "source": "sample",
        "name": "نورة",
        "body": "خفيف على الشعر. ما يثقله ولا يخلّيه مبلول.",
    },
    {
        "id": "sample-mist-3",
        "product_slug": HAIR,
        "source": "sample",
        "name": "عائشة",
        "body": "أرشه وأمشط وأطلع. ما يحتاج شطف.",
    },
    {
        "id": "sample-cream-1",
        "product_slug": LOTION,
        "source": "sample",
        "name": "موزه",
        "body": "ينشرب وما يدهن، وهذا كان طلبي.",
    },
    {
        "id": "sample-cream-2",
        "product_slug": LOTION,
        "source": "sample",
        "name": "فاطمة",
        "body": "ريحة نسيم البحر خفيفة، مو عطر ثقيل.",
    },
    {
        "id": "sample-cream-3",
        "product_slug": LOTION,
        "source": "sample",
        "name": "مريم",
        "body": "صار بعد الشاور مباشرة. كمية صغيرة تكفي.",
    },
    {
        "id": "sample-heel-1",
        "product_slug": FOOT,
        "source": "sample",
        "name": "ميثة",
        "body": "أسهل من الجرة، لأني أمرر الرول على الكعب بس.",
    },
    {
        "id": "sample-heel-2",
        "product_slug": FOOT,
        "source": "sample",
        "name": "نورة",
        "body": "حطيته بالليل كم يوم، الكعب صار أهدى للمس.",
    },
    {
        "id": "sample-heel-3",
        "product_slug": FOOT,
        "source": "sample",
        "name": "عائشة",
        "body": "صغير في الشنطة قبل الطلعة.",
    },
]


def sync_catalog() -> None:
    """
    Upsert the three live products and hide anything else.
    Stock and prices stay as they are on an existing row.
    A new slug gets the seed prices and stock.
    """
    from app.db import SessionLocal
    from app.models import Product, Review

    db = SessionLocal()
    try:
        keep = {row["slug"] for row in PRODUCTS}
        for row in PRODUCTS:
            product = db.get(Product, row["slug"])
            created = product is None
            if created:
                product = Product(slug=row["slug"])
                db.add(product)
            for key in ("sku", "nav_ar", "name_ar", "category", "ingredients", "images", "active", "sort"):
                setattr(product, key, row[key])
            if created:
                for key in (
                    "price_1",
                    "price_2",
                    "price_3",
                    "upsell_price",
                    "stock",
                    "scarcity_threshold",
                ):
                    setattr(product, key, row[key])
        db.flush()

        for rev in REVIEWS:
            review = db.get(Review, rev["id"])
            if review is None:
                review = Review(id=rev["id"])
                db.add(review)
            review.product_slug = rev["product_slug"]
            review.source = rev["source"]
            review.name = rev["name"]
            review.body = rev["body"]

        for product in db.scalars(select(Product)).all():
            if product.slug not in keep:
                product.active = False

        db.commit()
        logger.info("catalog synced: %s", ", ".join(sorted(keep)))
    except Exception:
        db.rollback()
        logger.exception("catalog sync failed")
    finally:
        db.close()
