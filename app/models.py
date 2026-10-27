"""
SQLAlchemy models for صَبا (Saba).
All timestamps are UTC timestamptz. Public ids use the SB- sequence.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, Text, ForeignKey,
    UniqueConstraint, Index, Sequence
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# Sequence for order public ids, starts at 100241 so first order is SB-100241
order_public_seq = Sequence("order_public_seq", start=100241)


class Product(Base):
    __tablename__ = "products"

    slug = Column(Text, primary_key=True)
    sku = Column(Text, unique=True, nullable=False)
    nav_ar = Column(Text, nullable=False)
    name_ar = Column(Text, nullable=False)
    category = Column(Text, nullable=False)  # hair | body | heel
    price_1 = Column(Integer, nullable=False, default=199)
    price_2 = Column(Integer, nullable=False, default=279)
    price_3 = Column(Integer, nullable=False, default=349)
    upsell_price = Column(Integer, nullable=False, default=99)
    stock = Column(Integer, nullable=False, default=120)
    scarcity_threshold = Column(Integer, nullable=False, default=25)
    active = Column(Boolean, nullable=False, default=True)
    sort = Column(Integer, nullable=False, default=0)
    ingredients = Column(JSONB, nullable=False, default=list)
    images = Column(JSONB, nullable=False, default=list)

    reviews = relationship("Review", back_populates="product")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_slug = Column(Text, ForeignKey("products.slug"), nullable=False)
    source = Column(Text, nullable=False)  # sample | real
    name = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    video_url = Column(Text, nullable=True)
    poster = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    product = relationship("Product", back_populates="reviews")


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(Text, unique=True, nullable=False)
    status = Column(Text, nullable=False, default="pending_upsell")
    customer_name = Column(Text, nullable=False)
    phone_e164 = Column(Text, nullable=False)
    phone_local = Column(Text, nullable=False)
    lines = Column(JSONB, nullable=False, default=list)
    upsell_slug = Column(Text, nullable=True)
    upsell_accepted = Column(Boolean, nullable=True)
    merchandise_aed = Column(Integer, nullable=False)
    total_aed = Column(Integer, nullable=True)
    currency = Column(Text, nullable=False, default="AED")
    event_id = Column(Text, nullable=False)
    landing_url = Column(Text, nullable=False, default="")
    attribution = Column(JSONB, nullable=False, default=dict)
    client_ip = Column(Text, nullable=False, default="")
    user_agent = Column(Text, nullable=False, default="")
    # Set from the same UAE / VPN check used at checkout. Dashboard counts only allowed rows.
    geo_qualified = Column(Boolean, nullable=False, default=False)
    geo_code = Column(Text, nullable=False, default="")
    country_code = Column(Text, nullable=False, default="")
    channel = Column(Text, nullable=False, default="")
    sheet_synced_at = Column(DateTime(timezone=True), nullable=True)
    sheet_error = Column(Text, nullable=True)
    capi_sent_at = Column(DateTime(timezone=True), nullable=True)
    capi_error = Column(Text, nullable=True)
    capi_status = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_orders_phone_created", "phone_e164", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    phone_e164 = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name = Column(Text, nullable=False)
    event_id = Column(Text, nullable=False)
    order_public_id = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    client_ip = Column(Text, nullable=False, default="")
    geo_qualified = Column(Boolean, nullable=False, default=False)
    geo_code = Column(Text, nullable=False, default="")
    country_code = Column(Text, nullable=False, default="")
    visitor_id = Column(Text, nullable=False, default="")
    channel = Column(Text, nullable=False, default="")
    utm_source = Column(Text, nullable=False, default="")
    utm_medium = Column(Text, nullable=False, default="")
    utm_campaign = Column(Text, nullable=False, default="")
    utm_content = Column(Text, nullable=False, default="")
    landing_path = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("event_name", "event_id", name="uq_analytics_event_dedup"),
    )


class IpVerdict(Base):
    """One ipapi.is result per address, so dashboard traffic does not re-check the same IP."""

    __tablename__ = "ip_verdicts"

    ip = Column(Text, primary_key=True)
    allowed = Column(Boolean, nullable=False)
    code = Column(Text, nullable=False)
    country_code = Column(Text, nullable=False, default="")
    checked_at = Column(DateTime(timezone=True), nullable=False)
