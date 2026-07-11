"""P2.6 — Unit tests for pure source-backbone services (no DB, no network)."""
from __future__ import annotations

import pytest

from app.services.source_canonical_key import (
    CanonicalKeyError,
    build_canonical_key,
    canonical_key_for_decision,
    canonical_key_for_legislation,
    normalize_source_type,
)
from app.services.source_fetcher import SourceFetchError, validate_url
from app.services.source_ingestion_service import effective_verification_status
from app.services.source_verification import (
    can_transition,
    evaluate_source_validity,
    index_eligibility,
)


# --- Controlled vocabulary + canonical key --------------------------------
def test_source_type_alias_normalization():
    assert normalize_source_type("yargitay") == "supreme_court_decision"
    assert normalize_source_type("Yargıtay") == "supreme_court_decision"
    assert normalize_source_type("supreme_court") == "supreme_court_decision"
    assert normalize_source_type("supreme_court_decision") == "supreme_court_decision"


def test_unknown_source_type_rejected():
    with pytest.raises(CanonicalKeyError):
        normalize_source_type("random_thing")


def test_decision_canonical_key_equivalent_variants():
    a = canonical_key_for_decision(
        source_type="yargitay", court="Yargıtay", chamber="13. Hukuk Dairesi",
        case_number="E.2020/123", decision_number="K.2021/456", decision_date="12.06.2021")
    b = canonical_key_for_decision(
        source_type="supreme_court_decision", court="YARGITAY", chamber="13 HD",
        case_number="2020-123", decision_number="2021-456", decision_date="2021-06-12")
    assert a == b


def test_materially_different_decision_does_not_collide():
    a = canonical_key_for_decision(
        source_type="supreme_court_decision", court="Yargıtay", chamber="13 HD",
        case_number="2020/123", decision_number="2021/456", decision_date="2021-06-12")
    b = canonical_key_for_decision(
        source_type="supreme_court_decision", court="Yargıtay", chamber="13 HD",
        case_number="2020/123", decision_number="2021/999", decision_date="2021-06-12")
    assert a != b


def test_legislation_canonical_key():
    k = canonical_key_for_legislation(
        source_type="legislation", issuing_authority="TBMM", number="6098",
        publication_date="2011-02-04")
    assert k.startswith("legislation|")
    assert "6098" in k


def test_decision_requires_numbers():
    with pytest.raises(CanonicalKeyError):
        canonical_key_for_decision(
            source_type="supreme_court_decision", court="Yargıtay", chamber="13 HD",
            case_number="", decision_number="", decision_date="2021-06-12")


# --- Verification state machine -------------------------------------------
def test_quarantined_cannot_go_directly_to_verified_official():
    assert can_transition("quarantined", "verified_official") is False
    assert can_transition("quarantined", "needs_review") is True


def test_needs_review_can_be_verified():
    assert can_transition("needs_review", "verified_official") is True
    assert can_transition("needs_review", "editor_verified") is True


def test_conflicting_requires_path_not_silent():
    # conflicting can be resolved to editor_verified/official (authz-gated) but
    # cannot silently remain trusted; a normal automated ingestion path elsewhere
    # sets conflicting, and only review resolves it.
    assert can_transition("conflicting", "editor_verified") is True
    assert can_transition("conflicting", "verified_secondary") is False


def test_repealed_terminal_ish():
    assert can_transition("repealed", "verified_official") is False
    assert can_transition("repealed", "needs_review") is True


# --- Index eligibility ----------------------------------------------------
def test_index_eligibility_matrix():
    assert index_eligibility("verified_official").weight == "full_weight"
    assert index_eligibility("editor_verified").weight == "full_weight"
    assert index_eligibility("verified_secondary").weight == "reduced_weight"
    assert index_eligibility("needs_review").weight == "low_weight"
    assert index_eligibility("conflicting").eligible is False
    assert index_eligibility("quarantined").eligible is False
    assert index_eligibility("superseded").weight == "historical_only"
    assert index_eligibility("repealed").weight == "historical_only"


# --- Temporal validity ----------------------------------------------------
def test_temporal_valid_at_event_date():
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="2011-07-01",
        valid_to="", repeal_date="", event_date="2020-05-01") == "valid"


def test_temporal_not_yet_effective():
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="2021-01-01",
        valid_to="", repeal_date="", event_date="2020-05-01") == "not_yet_effective"


def test_temporal_repealed():
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="2011-07-01",
        valid_to="", repeal_date="2019-01-01", event_date="2020-05-01") == "repealed"


def test_temporal_expired_superseded():
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="2011-07-01",
        valid_to="2018-12-31", repeal_date="", event_date="2020-05-01") == "expired"
    assert evaluate_source_validity(
        verification_status="superseded", valid_from="", valid_to="",
        repeal_date="", event_date="2020-05-01") == "superseded"


def test_temporal_unknown_when_no_dates():
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="", valid_to="",
        repeal_date="", event_date="2020-05-01") == "unknown"
    assert evaluate_source_validity(
        verification_status="verified_official", valid_from="2011-07-01",
        valid_to="", repeal_date="", event_date="") == "unknown"


# --- SSRF matrix (deterministic resolver) ---------------------------------
def _resolver(ip):
    return lambda host: [ip]


def test_ssrf_blocks_localhost():
    with pytest.raises(SourceFetchError) as e:
        validate_url("http://localhost/x", resolver=_resolver("93.184.216.34"))
    assert e.value.code == "blocked_host"


def test_ssrf_blocks_non_http_scheme():
    with pytest.raises(SourceFetchError) as e:
        validate_url("ftp://mevzuat.gov.tr/x", resolver=_resolver("93.184.216.34"))
    assert e.value.code == "unsafe_scheme"


def test_ssrf_blocks_credentials():
    with pytest.raises(SourceFetchError) as e:
        validate_url("https://user:pass@yargitay.gov.tr/x", resolver=_resolver("93.184.216.34"))
    assert e.value.code == "credentials_in_url"


def test_ssrf_blocks_unallowlisted_domain():
    with pytest.raises(SourceFetchError) as e:
        validate_url("https://evil.example.com/x", resolver=_resolver("93.184.216.34"))
    assert e.value.code == "domain_not_allowed"


def test_ssrf_blocks_dns_to_private_ipv4():
    with pytest.raises(SourceFetchError) as e:
        validate_url("https://yargitay.gov.tr/x", resolver=_resolver("10.0.0.5"))
    assert e.value.code == "dns_unsafe_ip"


def test_ssrf_blocks_dns_to_link_local():
    with pytest.raises(SourceFetchError) as e:
        validate_url("https://yargitay.gov.tr/x", resolver=_resolver("169.254.169.254"))
    assert e.value.code == "dns_unsafe_ip"


def test_ssrf_blocks_ipv6_loopback_and_private():
    with pytest.raises(SourceFetchError):
        validate_url("https://yargitay.gov.tr/x", resolver=_resolver("::1"))
    with pytest.raises(SourceFetchError):
        validate_url("https://yargitay.gov.tr/x", resolver=_resolver("fd00::1"))


def test_ssrf_blocks_ip_literal_url():
    with pytest.raises(SourceFetchError) as e:
        validate_url("http://169.254.169.254/latest/meta-data", resolver=_resolver("169.254.169.254"))
    assert e.value.code in ("blocked_ip", "ip_literal_not_allowed")


def test_ssrf_allows_official_public_ip():
    ips = validate_url("https://karararama.yargitay.gov.tr/x", resolver=_resolver("93.184.216.34"))
    assert ips == ["93.184.216.34"]


def test_fetch_redirect_to_private_ip_blocked():
    from app.services.source_fetcher import _StubResponse, fetch_source

    def transport(url):
        return _StubResponse(status_code=302, headers={}, content=b"", location="https://evil.example.com/x")

    with pytest.raises(SourceFetchError) as e:
        fetch_source("https://yargitay.gov.tr/x", resolver=_resolver("93.184.216.34"), transport=transport)
    # The redirect target is not allowlisted → blocked on the next hop.
    assert e.value.code == "domain_not_allowed"


# --- Effective verification status (version-scoped trust) -------------------
def test_effective_verified_official_with_valid_evidence():
    assert effective_verification_status(
        "verified_official", "v1", ("v1", True)
    ) == "verified_official"


def test_effective_verified_official_without_fetch_evidence_resets():
    """A verified_official record whose current version lacks official_fetch_match
    evidence must be treated as needs_review."""
    assert effective_verification_status(
        "verified_official", "v2", ("v2", False)
    ) == "needs_review"


def test_effective_verified_official_with_no_current_version():
    assert effective_verification_status(
        "verified_official", None, None
    ) == "needs_review"


def test_effective_preserves_non_verified_statuses():
    assert effective_verification_status(
        "conflicting", "v1", ("v1", False)
    ) == "conflicting"
    assert effective_verification_status(
        "editor_verified", "v1", ("v1", False)
    ) == "editor_verified"
