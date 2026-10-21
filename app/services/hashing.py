"""
Hashing for CAPI payloads. SHA-256, UTF-8, hex lowercase. No salt.
Lives only here. Do not hash elsewhere.

Meta & Snap: digits with country code, no plus (9715xxxxxxxx)
TikTok:      E.164 with plus (+9715xxxxxxxx)
"""
from __future__ import annotations
import hashlib


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_phone_meta_snap(digits: str) -> str:
    """digits = '971501234567' (no plus)"""
    return sha256(digits)


def hash_phone_tiktok(tiktok: str) -> str:
    """tiktok = '+971501234567' (with plus)"""
    return sha256(tiktok)


def hash_name_token(token: str) -> str:
    """Lowercase trimmed token."""
    return sha256(token.strip().lower())


def hash_external_id(value: str) -> str:
    return sha256(value)


def split_name(full_name: str) -> tuple[str, str | None]:
    """Returns (fn, ln_or_None). Arabic stays unicode, lowercased before hash."""
    parts = full_name.strip().split()
    fn = parts[0] if parts else full_name.strip()
    ln = " ".join(parts[1:]) if len(parts) > 1 else None
    return fn, ln
