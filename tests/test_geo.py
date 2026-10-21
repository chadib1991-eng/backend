"""MaxMind gate decisions. No network and no database."""
from app.services.geo import assess_insights, extract_client_ip, is_public_ip


def _uae(**extra):
    data = {"country": {"iso_code": "AE"}, "traits": {}}
    data.update(extra)
    return data


def test_uae_clean_ip_is_allowed():
    verdict = assess_insights(_uae(), 5.0)
    assert verdict.allowed
    assert verdict.code == "ok"


def test_outside_uae_is_blocked():
    verdict = assess_insights({"country": {"iso_code": "US"}, "traits": {}}, 5.0)
    assert not verdict.allowed
    assert verdict.code == "outside_uae"


def test_missing_country_is_blocked():
    verdict = assess_insights({}, 5.0)
    assert verdict.code == "outside_uae"


def test_uae_vpn_is_blocked():
    verdict = assess_insights(
        _uae(anonymizer={"is_anonymous_vpn": True, "provider_name": "nordvpn"}),
        5.0,
    )
    assert verdict.code == "vpn"


def test_legacy_traits_vpn_flag_is_blocked():
    verdict = assess_insights(_uae(traits={"is_anonymous_vpn": True}), 5.0)
    assert verdict.code == "vpn"


def test_proxy_tor_and_hosting_are_suspicious():
    for flag in (
        "is_public_proxy",
        "is_residential_proxy",
        "is_tor_exit_node",
        "is_hosting_provider",
        "is_anonymous",
    ):
        verdict = assess_insights(_uae(anonymizer={flag: True}), 5.0)
        assert verdict.code == "suspicious", flag


def test_high_risk_snapshot_is_suspicious():
    verdict = assess_insights(_uae(traits={"ip_risk_snapshot": 12.5}), 5.0)
    assert verdict.code == "suspicious"


def test_omitted_risk_snapshot_is_low_risk():
    verdict = assess_insights(_uae(traits={"isp": "Etisalat"}), 5.0)
    assert verdict.allowed


def test_risk_just_under_threshold_is_allowed():
    verdict = assess_insights(_uae(traits={"ip_risk_snapshot": 4.99}), 5.0)
    assert verdict.allowed


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
