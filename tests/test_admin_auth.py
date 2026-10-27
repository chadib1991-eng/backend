"""Dashboard login. No database and no network."""
from datetime import datetime, timedelta, timezone

from app.settings import settings
from app.services.admin_auth import credentials_ok, issue_session, read_session, too_many_attempts, record_failure


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "saba")
    monkeypatch.setattr(settings, "admin_password", "correct horse battery")


def test_session_roundtrip(monkeypatch):
    _configure(monkeypatch)
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    token = issue_session("saba", now=now)
    assert read_session(token, now=now) == "saba"


def test_expired_session_is_rejected(monkeypatch):
    _configure(monkeypatch)
    issued = datetime(2026, 10, 1, tzinfo=timezone.utc)
    token = issue_session("saba", now=issued)
    later = issued + timedelta(days=8)
    assert read_session(token, now=later) is None


def test_tampered_session_is_rejected(monkeypatch):
    _configure(monkeypatch)
    token = issue_session("saba")
    assert read_session(token[:-1] + ("a" if token[-1] != "a" else "b")) is None


def test_wrong_password_is_rejected(monkeypatch):
    _configure(monkeypatch)
    assert credentials_ok("saba", "wrong") is False
    assert credentials_ok("other", "correct horse battery") is False
    assert credentials_ok("saba", "correct horse battery") is True


def test_blank_env_cannot_log_in(monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "")
    monkeypatch.setattr(settings, "admin_password", "")
    assert credentials_ok("saba", "correct horse battery") is False
    assert read_session("anything") is None


def test_password_change_invalidates_the_cookie(monkeypatch):
    _configure(monkeypatch)
    token = issue_session("saba")
    monkeypatch.setattr(settings, "admin_password", "a different password")
    assert read_session(token) is None


def test_login_attempts_are_limited():
    ip = "203.0.113.10"
    now = 1_700_000_000.0
    assert too_many_attempts(ip, now) is False
    for offset in range(10):
        record_failure(ip, now + offset)
    assert too_many_attempts(ip, now + 10) is True
    assert too_many_attempts(ip, now + 16 * 60) is False
