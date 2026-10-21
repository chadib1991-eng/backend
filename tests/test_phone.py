"""
Phone validation tests. Does not require a database.
"""
import pytest
from app.services.phone import parse_uae_mobile


# ---------- Valid numbers ----------

@pytest.mark.parametrize("raw,expected_local,expected_e164,expected_digits", [
    ("0501234567",   "0501234567", "+971501234567", "971501234567"),
    ("501234567",    "0501234567", "+971501234567", "971501234567"),
    ("+971501234567","0501234567", "+971501234567", "971501234567"),
    ("971501234567", "0501234567", "+971501234567", "971501234567"),
    ("00971501234567","0501234567","+971501234567","971501234567"),
    # All valid UAE mobile prefixes after 5: 0,2,4,5,6,8
    ("0521234567",   "0521234567", "+971521234567", "971521234567"),
    ("0541234567",   "0541234567", "+971541234567", "971541234567"),
    ("0551234567",   "0551234567", "+971551234567", "971551234567"),
    ("0561234567",   "0561234567", "+971561234567", "971561234567"),
    ("0581234567",   "0581234567", "+971581234567", "971581234567"),
])
def test_valid(raw, expected_local, expected_e164, expected_digits):
    result = parse_uae_mobile(raw)
    assert result is not None, f"Expected valid for {raw!r}"
    assert result.local == expected_local
    assert result.e164 == expected_e164
    assert result.digits == expected_digits
    assert result.tiktok == expected_e164  # tiktok = e164


# ---------- Invalid numbers ----------

@pytest.mark.parametrize("raw", [
    "041234567",       # landline Abu Dhabi
    "041234567890",    # landline with too many digits
    "0512345678",      # 11 digits — too long
    "051234567",       # 9 digits — short
    "051 234 567 8",   # 51 is not a valid prefix
    "+44501234567",    # UK number
    "0701234567",      # 7x prefix not valid
    "0311234567",      # 3x prefix
    "",                # empty
    "abc",             # non-numeric
    "0000000000",      # not mobile
])
def test_invalid(raw):
    result = parse_uae_mobile(raw)
    assert result is None, f"Expected invalid for {raw!r}, got {result}"


# ---------- Hash vectors (docs/09, docs/11) ----------

def test_hash_meta_snap_vector():
    """Meta and Snap hash: digits 971501234567 (no plus)"""
    from app.services.hashing import hash_phone_meta_snap
    phone = parse_uae_mobile("0501234567")
    assert phone is not None
    assert phone.digits == "971501234567"
    # SHA-256 of "971501234567"
    import hashlib
    expected = hashlib.sha256("971501234567".encode()).hexdigest()
    assert hash_phone_meta_snap(phone.digits) == expected


def test_hash_tiktok_vector():
    """TikTok hash: +971501234567 (with plus)"""
    from app.services.hashing import hash_phone_tiktok
    phone = parse_uae_mobile("0501234567")
    assert phone is not None
    assert phone.tiktok == "+971501234567"
    import hashlib
    expected = hashlib.sha256("+971501234567".encode()).hexdigest()
    assert hash_phone_tiktok(phone.tiktok) == expected


def test_meta_snap_input_has_no_plus():
    """The digits field used for Meta/Snap has no plus."""
    phone = parse_uae_mobile("+971502345678")
    assert phone is not None
    assert not phone.digits.startswith("+")
    assert phone.digits == "971502345678"


def test_tiktok_input_has_plus():
    """The tiktok field used for TikTok has a plus."""
    phone = parse_uae_mobile("0502345678")
    assert phone is not None
    assert phone.tiktok.startswith("+")
    assert phone.tiktok == "+971502345678"
