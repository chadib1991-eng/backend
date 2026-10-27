"""
Remember ipapi.is verdicts so each public IP is looked up once per day.

Dashboard clicks, product views, and orders all use this. A private address,
a VPN, or a failed lookup is not qualified traffic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import IpVerdict
from app.services.geo import GeoVerdict, is_public_ip, lookup_ip_details

DEFINITE_TTL = timedelta(hours=24)
SOFT_TTL = timedelta(minutes=15)
SOFT_CODES = {"unavailable"}


@dataclass(frozen=True)
class QualifiedIP:
    allowed: bool
    code: str
    country_code: str


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def verdict_is_fresh(code: str, checked_at: datetime, now: datetime) -> bool:
    ttl = SOFT_TTL if code in SOFT_CODES else DEFINITE_TTL
    return _as_utc(now) - _as_utc(checked_at) < ttl


def qualify_ip(db: Session, ip: str, now: datetime | None = None) -> QualifiedIP:
    """UAE, non-VPN verdict. Uses the stored lookup when it is still fresh."""
    now = now or datetime.now(timezone.utc)
    if not is_public_ip(ip):
        return QualifiedIP(False, "unavailable", "")

    row = db.get(IpVerdict, ip)
    if row is not None and verdict_is_fresh(row.code, row.checked_at, now):
        return QualifiedIP(bool(row.allowed), row.code, row.country_code or "")

    verdict, country = lookup_ip_details(ip)
    _store(db, ip, verdict, country, now, row)
    return QualifiedIP(verdict.allowed, verdict.code, country)


def _store(
    db: Session,
    ip: str,
    verdict: GeoVerdict,
    country: str,
    now: datetime,
    row: IpVerdict | None,
) -> None:
    if row is not None:
        row.allowed = verdict.allowed
        row.code = verdict.code
        row.country_code = country
        row.checked_at = now
        return

    fresh = IpVerdict(
        ip=ip,
        allowed=verdict.allowed,
        code=verdict.code,
        country_code=country,
        checked_at=now,
    )
    try:
        with db.begin_nested():
            db.add(fresh)
            db.flush()
    except IntegrityError:
        winner = db.get(IpVerdict, ip)
        if winner is not None:
            winner.allowed = verdict.allowed
            winner.code = verdict.code
            winner.country_code = country
            winner.checked_at = now
