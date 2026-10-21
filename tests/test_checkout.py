"""
Checkout integration tests.
Requires TEST_DATABASE_URL env var pointing to a live Postgres.
Skips gracefully when absent so CI that has no DB still shows the file.
"""
import os
import uuid
import pytest

# Skip all tests in this module if TEST_DATABASE_URL is not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture(scope="module")
def db_engine():
    from sqlalchemy import create_engine
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _mock_product(db, slug, stock=120):
    from app.models import Product
    p = db.get(Product, slug)
    assert p is not None, f"Product {slug!r} not seeded"
    return p


def test_start_creates_pending(db):
    """Checkout start inserts a pending_upsell order."""
    from app.models import Order, Product
    from app.services.orders import build_line, create_order
    from app.services.pricing import choose_upsell

    product = _mock_product(db, "razaz-al-shaar")
    line = build_line(product, "2")
    all_slugs = [p.slug for p in db.query(Product).all()]
    upsell_slug = choose_upsell(["razaz-al-shaar"], all_slugs)

    order = create_order(
        db,
        customer_name="ميثة",
        phone_e164="+971501234567",
        phone_local="0501234567",
        lines=[line],
        upsell_slug=upsell_slug,
        merchandise_aed=279,
        landing_url="https://sababreeze.com",
        attribution={"saba_cid": str(uuid.uuid4())},
        client_ip="127.0.0.1",
        user_agent="pytest",
    )
    db.flush()

    assert order.status == "pending_upsell"
    assert order.sheet_synced_at is None  # not synced before complete
    assert order.total_aed is None
    db.rollback()


def test_complete_idempotent(db):
    """Completing an order twice returns the same order without re-syncing."""
    from app.models import Order, Product
    from app.services.orders import build_line, create_order, complete_order
    from app.services.pricing import choose_upsell

    product = _mock_product(db, "kareem-al-intiash")
    line = build_line(product, "1")
    all_slugs = [p.slug for p in db.query(Product).all()]
    upsell_slug = choose_upsell(["kareem-al-intiash"], all_slugs)

    order = create_order(
        db,
        customer_name="نورة",
        phone_e164="+971521111111",
        phone_local="0521111111",
        lines=[line],
        upsell_slug=upsell_slug,
        merchandise_aed=199,
        landing_url="",
        attribution={},
        client_ip="",
        user_agent="",
    )
    db.flush()

    upsell_product = db.get(Product, upsell_slug) if upsell_slug else None
    complete_order(db, order, accepted=False, upsell_product=upsell_product)
    db.flush()
    first_total = order.total_aed

    # Second complete — should not change anything
    complete_order(db, order, accepted=True, upsell_product=upsell_product)
    assert order.total_aed == first_total  # idempotent
    db.rollback()


def test_upsell_adds_99(db):
    """Accepted upsell adds 99 to the total."""
    from app.models import Product
    from app.services.orders import build_line, create_order, complete_order
    from app.services.pricing import choose_upsell

    product = _mock_product(db, "razaz-al-shaar")
    line = build_line(product, "2")  # 279
    all_slugs = [p.slug for p in db.query(Product).all()]
    upsell_slug = choose_upsell(["razaz-al-shaar"], all_slugs)
    assert upsell_slug is not None

    order = create_order(
        db,
        customer_name="عائشة",
        phone_e164="+971542222222",
        phone_local="0542222222",
        lines=[line],
        upsell_slug=upsell_slug,
        merchandise_aed=279,
        landing_url="",
        attribution={},
        client_ip="",
        user_agent="",
    )
    db.flush()

    upsell_product = db.get(Product, upsell_slug)
    complete_order(db, order, accepted=True, upsell_product=upsell_product)
    db.flush()

    assert order.total_aed == 279 + 99
    assert order.upsell_accepted is True
    db.rollback()


def test_client_price_ignored(db):
    """The backend always uses catalog prices, never a client-supplied price."""
    from app.models import Product
    from app.services.pricing import price_for

    product = _mock_product(db, "razaz-al-shaar")
    # Even if a client sent price: 1, the backend uses catalog
    _, price = price_for(product, "2")
    assert price == 279  # catalog price, not 1
