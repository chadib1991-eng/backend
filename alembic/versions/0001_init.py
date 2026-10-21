"""init

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json
from datetime import datetime, timezone

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sequence for order public ids
    op.execute("CREATE SEQUENCE IF NOT EXISTS order_public_seq START 100241")

    # products
    op.create_table(
        "products",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("sku", sa.Text(), unique=True, nullable=False),
        sa.Column("nav_ar", sa.Text(), nullable=False),
        sa.Column("name_ar", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("price_1", sa.Integer(), nullable=False),
        sa.Column("price_2", sa.Integer(), nullable=False),
        sa.Column("price_3", sa.Integer(), nullable=False),
        sa.Column("upsell_price", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("scarcity_threshold", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingredients", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("images", postgresql.JSONB(), nullable=False, server_default="[]"),
    )

    # reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("product_slug", sa.Text(), sa.ForeignKey("products.slug"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("poster", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # orders
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.Text(), unique=True, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_upsell"),
        sa.Column("customer_name", sa.Text(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("phone_local", sa.Text(), nullable=False),
        sa.Column("lines", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("upsell_slug", sa.Text(), nullable=True),
        sa.Column("upsell_accepted", sa.Boolean(), nullable=True),
        sa.Column("merchandise_aed", sa.Integer(), nullable=False),
        sa.Column("total_aed", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="AED"),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("landing_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("attribution", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("client_ip", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("sheet_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sheet_error", sa.Text(), nullable=True),
        sa.Column("capi_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capi_error", sa.Text(), nullable=True),
        sa.Column("capi_status", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_phone_created", "orders", ["phone_e164", "created_at"])
    op.create_index("ix_orders_status_created", "orders", ["status", "created_at"])

    # contacts
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # analytics_events
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("order_public_id", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_analytics_event_dedup", "analytics_events", ["event_name", "event_id"]
    )

    # Seed products and reviews
    _seed_data()


def _seed_data() -> None:
    from app.catalog_seed import PRODUCTS, REVIEWS

    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    for p in PRODUCTS:
        conn.execute(
            sa.text(
                """
                INSERT INTO products
                  (slug, sku, nav_ar, name_ar, category, price_1, price_2, price_3,
                   upsell_price, stock, scarcity_threshold, active, sort, ingredients, images)
                VALUES
                  (:slug, :sku, :nav_ar, :name_ar, :category, :price_1, :price_2, :price_3,
                   :upsell_price, :stock, :scarcity_threshold, :active, :sort,
                   cast(:ingredients as jsonb), cast(:images as jsonb))
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "slug": p["slug"],
                "sku": p["sku"],
                "nav_ar": p["nav_ar"],
                "name_ar": p["name_ar"],
                "category": p["category"],
                "price_1": p["price_1"],
                "price_2": p["price_2"],
                "price_3": p["price_3"],
                "upsell_price": p["upsell_price"],
                "stock": p["stock"],
                "scarcity_threshold": p["scarcity_threshold"],
                "active": p["active"],
                "sort": p["sort"],
                "ingredients": json.dumps(p["ingredients"], ensure_ascii=False),
                "images": json.dumps(p["images"], ensure_ascii=False),
            },
        )

    for r in REVIEWS:
        conn.execute(
            sa.text(
                """
                INSERT INTO reviews (id, product_slug, source, name, body, video_url, poster, created_at)
                VALUES (:id, :product_slug, :source, :name, :body, :video_url, :poster, :created_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": r["id"],
                "product_slug": r["product_slug"],
                "source": r["source"],
                "name": r["name"],
                "body": r["body"],
                "video_url": r.get("video_url"),
                "poster": r.get("poster"),
                "created_at": now,
            },
        )


def downgrade() -> None:
    op.drop_table("analytics_events")
    op.drop_table("contacts")
    op.drop_index("ix_orders_status_created", "orders")
    op.drop_index("ix_orders_phone_created", "orders")
    op.drop_table("orders")
    op.drop_table("reviews")
    op.drop_table("products")
    op.execute("DROP SEQUENCE IF EXISTS order_public_seq")
