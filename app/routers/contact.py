import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Contact
from app.services.phone import parse_uae_mobile
from app.services.sheets import push_contact

router = APIRouter()


class ContactRequest(BaseModel):
    name: str
    phone: str
    message: str

    model_config = {"extra": "ignore"}


@router.post("/api/contact")
def submit_contact(body: ContactRequest, db: Session = Depends(get_db)):
    name = body.name.strip()
    if len(name) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_name", "message": "اكتبي اسمج"}},
        )

    phone = parse_uae_mobile(body.phone)
    if phone is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_phone",
                    "message": "اكتبي رقم جوال إماراتي صحيح، مثل 0501234567",
                }
            },
        )

    message = body.message.strip()
    if len(message) < 10 or len(message) > 1000:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_message", "message": "الرسالة قصيرة أو طويلة جداً"}},
        )

    contact = Contact(
        id=uuid.uuid4(),
        name=name,
        phone_e164=phone.e164,
        message=message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(contact)
    db.commit()

    try:
        push_contact(name, phone.e164, phone.local, message)
    except Exception:
        pass

    return {"ok": True}
