"""
Dashboard session cookies. The password never leaves the server.

The cookie is an HMAC of the username and expiry, keyed by the password.
Changing ADMIN_PASSWORD signs every open session out.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.settings import settings

COOKIE = "saba_admin"
SESSION_DAYS = 7
_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 10
_failures: dict[str, list[float]] = {}


def login_configured() -> bool:
    return bool(settings.admin_username and settings.admin_password)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _signing_key() -> bytes:
    return hashlib.sha256(b"saba-admin-session-v1\0" + settings.admin_password.encode("utf-8")).digest()


def credentials_ok(username: str, password: str) -> bool:
    if not login_configured():
        return False
    user_ok = hmac.compare_digest(_digest(username or ""), _digest(settings.admin_username))
    pass_ok = hmac.compare_digest(_digest(password or ""), _digest(settings.admin_password))
    return user_ok and pass_ok


def token_ok(token: str | None) -> bool:
    expected = settings.admin_token
    if not expected or not token:
        return False
    return hmac.compare_digest(_digest(token), _digest(expected))


def issue_session(username: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    exp = int((now + timedelta(days=SESSION_DAYS)).timestamp())
    payload = json.dumps({"u": username, "exp": exp}, separators=(",", ":")).encode()
    sig = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{body}.{sig}"


def read_session(token: str, now: datetime | None = None) -> str | None:
    if not login_configured() or not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if len(sig) != 64:
        return None
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        expected = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(payload.decode())
        username = str(data["u"])
        exp = int(data["exp"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    now = now or datetime.now(timezone.utc)
    if exp < int(now.timestamp()):
        return None
    if username != settings.admin_username:
        return None
    return username


def too_many_attempts(ip: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    hits = [stamp for stamp in _failures.get(ip, []) if now - stamp < _WINDOW_SECONDS]
    _failures[ip] = hits
    return len(hits) >= _MAX_FAILURES


def record_failure(ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    hits = [stamp for stamp in _failures.get(ip, []) if now - stamp < _WINDOW_SECONDS]
    hits.append(now)
    _failures[ip] = hits


def clear_attempts(ip: str) -> None:
    _failures.pop(ip, None)


def cookie_secure(scheme: str) -> bool:
    return (scheme or "").split(",")[0].strip().lower() == "https"


def set_session_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        key=COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(key=COOKIE, path="/", samesite="lax", secure=secure)
