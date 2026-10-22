"""ipapi.is gate decisions. No network and no database."""
from app.services.geo import assess_lookup, extract_client_ip, is_public_ip


def _uae(**extra):
    data = {
        "location": {"country_code": "AE"},
        "is_vpn": False,
        "is_proxy": False,
        "is_tor": False,
        "is_datacenter": False,
        "is_abuser": False,
    }
    data.update(extra)
    return data


def test_uae_clean_ip_is_allowed():
    verdict = assess_lookup(_uae())
    assert verdict.allowed
    assert verdict.code == "ok"


def test_outside_uae_is_blocked():
    verdict = assess_lookup(_uae(location={"country_code": "US"}))
    assert not verdict.allowed
    assert verdict.code == "outside_uae"


def test_missing_country_is_blocked():
    verdict = assess_lookup(_uae(location=None))
    assert verdict.code == "outside_uae"


def test_uae_vpn_is_blocked():
    verdict = assess_lookup(_uae(is_vpn=True))
    assert verdict.code == "vpn"


def test_truthy_vpn_string_is_blocked():
    verdict = assess_lookup(_uae(is_vpn="yes"))
    assert verdict.code == "vpn"


def test_proxy_tor_datacenter_and_abuser_are_suspicious():
    for flag in ("is_proxy", "is_tor", "is_datacenter", "is_abuser"):
        verdict = assess_lookup(_uae(**{flag: True}))
        assert verdict.code == "suspicious", flag


def test_keyless_response_without_flags_is_blocked():
    verdict = assess_lookup({"country": "United Arab Emirates", "docs": "https://ipapi.is/free-tier.html"})
    assert verdict.code == "unavailable"


def test_api_error_is_blocked():
    verdict = assess_lookup({"error": "quota", "error_code": "ERR_QUOTA_EXCEEDED"})
    assert verdict.code == "unavailable"


def test_forwarded_for_uses_the_last_hop():
    ip = extract_client_ip(
        {"x-forwarded-for": "1.1.1.1, 94.200.1.10"},
        peer="172.18.0.2",
    )
    assert ip == "94.200.1.10"


def test_public_peer_is_not_overridden_by_a_spoofed_header():
    ip = extract_client_ip(
        {"x-forwarded-for": "94.200.1.10"},
        peer="8.8.8.8",
    )
    assert ip == "8.8.8.8"


def test_private_and_loopback_are_not_public():
    assert not is_public_ip("127.0.0.1")
    assert not is_public_ip("10.1.2.3")
    assert not is_public_ip("")
    assert is_public_ip("94.200.1.10")


def test_bypass_phone(monkeypatch):
    from app.settings import settings
    from app.services.geo import is_bypass_phone

    monkeypatch.setattr(settings, "checkout_bypass_phones", "0500000099")
    assert is_bypass_phone("+971500000099")
    assert not is_bypass_phone("+971501234567")
