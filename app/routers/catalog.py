from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Any

from app.db import get_db
from app.models import Product, Review

router = APIRouter()


def _product_to_dict(p: Product, reviews: list[Review]) -> dict[str, Any]:
    # Compute review stats for real reviews only
    real_reviews = [r for r in reviews if r.source == "real"]
    sample_reviews = [r for r in reviews if r.source == "sample"]

    # Stars only when >= 5 real reviews (spec 06, 18)
    stars = None
    if len(real_reviews) >= 5:
        # No rating column yet; stars are computed from real review rows
        # In v1, star field not stored per review - just show real reviews
        pass

    # Show samples only if no real reviews for this product
    visible_reviews = real_reviews if real_reviews else sample_reviews

    return {
        "slug": p.slug,
        "sku": p.sku,
        "nav_ar": p.nav_ar,
        "name_ar": p.name_ar,
        "category": p.category,
        "prices": {
            "1": p.price_1,
            "2": p.price_2,
            "3": p.price_3,
        },
        "upsell_price": p.upsell_price,
        "stock": p.stock,
        "scarcity_threshold": p.scarcity_threshold,
        "active": p.active,
        "sort": p.sort,
        "ingredients": p.ingredients,
        "images": p.images,
        "offers": [
            {"code": "1", "pieces": 1, "price_aed": p.price_1, "badge": None},
            {"code": "2", "pieces": 2, "price_aed": p.price_2, "badge": "most_chosen"},
            {"code": "3", "pieces": 3, "price_aed": p.price_3, "badge": "best_value"},
        ],
        "default_offer": "2",
        "upsell_price_aed": p.upsell_price,
        "reviews": [
            {
                "id": r.id,
                "product_slug": r.product_slug,
                "source": r.source,
                "name": r.name,
                "body": r.body,
                "video_url": r.video_url,
                "poster": r.poster,
            }
            for r in visible_reviews
        ],
        "stars": stars,
        "real_review_count": len(real_reviews),
    }


@router.get("/api/catalog")
def get_catalog(db: Session = Depends(get_db)):
    products = db.scalars(
        select(Product).where(Product.active == True).order_by(Product.sort)
    ).all()
    reviews = db.scalars(select(Review)).all()
    reviews_by_slug: dict[str, list[Review]] = {}
    for r in reviews:
        reviews_by_slug.setdefault(r.product_slug, []).append(r)

    return [_product_to_dict(p, reviews_by_slug.get(p.slug, [])) for p in products]


@router.get("/api/products/{slug}")
def get_product(slug: str, db: Session = Depends(get_db)):
    product = db.get(Product, slug)
    if not product or not product.active:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "ما لقينا المنتج"}},
        )
    reviews = db.scalars(
        select(Review).where(Review.product_slug == slug)
    ).all()
    return _product_to_dict(product, list(reviews))
