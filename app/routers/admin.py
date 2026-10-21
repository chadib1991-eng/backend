from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional

from app.db import get_db
from app.models import Order
from app.settings import settings
from app.services.sheets import push_order

router = APIRouter()


def _require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthorized", "message": "غير مصرح"}})


@router.get("/api/admin/orders")
def admin_orders(
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    orders = db.scalars(
        select(Order).order_by(Order.created_at.desc()).limit(50)
    ).all()
    return [
        {
            "public_id": o.public_id,
            "status": o.status,
            "customer_name": o.customer_name,
            "phone_e164": o.phone_e164,
            "phone_local": o.phone_local,
            "total_aed": o.total_aed,
            "merchandise_aed": o.merchandise_aed,
            "sheet_synced_at": o.sheet_synced_at.isoformat() if o.sheet_synced_at else None,
            "sheet_error": o.sheet_error,
            "capi_status": o.capi_status,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]


@router.post("/api/admin/orders/{public_id}/resync")
def resync_order(
    public_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    """Re-push a single order to the sheet without overwriting ops columns."""
    order = db.scalars(
        select(Order).where(Order.public_id == public_id)
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "ما لقينا الطلب"}})

    push_order(order)
    db.commit()
    return {"ok": True, "sheet_error": order.sheet_error, "sheet_synced_at": order.sheet_synced_at.isoformat() if order.sheet_synced_at else None}
