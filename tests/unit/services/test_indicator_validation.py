"""Unit tests for indicator enrichability validation — no DB, no network."""

from __future__ import annotations

import pytest

from app.schemas.indicators import IndicatorType
from app.services.enrichment import is_enrichable


class TestIPEnrichable:
    """IPv4 and IPv6 private/reserved ranges should not be enrichable."""

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.0.8.55",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "192.168.0.100",
        ],
    )
    def test_private_ipv4_not_enrichable(self, ip: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, ip)
        assert enrichable is False
        assert reason is not None
        assert "non-routable" in reason

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",       # loopback
            "169.254.1.1",     # link-local
            "100.64.0.1",      # CGNAT (shared address space)
            "0.0.0.0",         # unspecified
            "255.255.255.255", # broadcast
        ],
    )
    def test_other_non_global_ipv4_not_enrichable(self, ip: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, ip)
        assert enrichable is False

    @pytest.mark.parametrize("ip", ["8.8.8.8", "203.0.114.1", "1.1.1.1", "93.184.216.34"])
    def test_public_ipv4_enrichable(self, ip: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, ip)
        assert enrichable is True
        assert reason is None

    @pytest.mark.parametrize(
        "ip",
        [
            "::1",          # loopback
            "fe80::1",      # link-local
            "fd00::1",      # unique-local (RFC 4193)
            "fc00::1",      # unique-local
        ],
    )
    def test_non_global_ipv6_not_enrichable(self, ip: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, ip)
        assert enrichable is False

    def test_public_ipv6_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, "2001:4860:4860::8888")
        assert enrichable is True
        assert reason is None

    def test_invalid_ip_not_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.IP, "not-an-ip")
        assert enrichable is False
        assert reason is not None
        assert "invalid" in reason


class TestDomainEnrichable:
    @pytest.mark.parametrize(
        "domain",
        [
            "server.internal",
            "app.corp",
            "host.local",
            "localhost",
            "myhost.localhost",
            "dc.home",
            "printer.lan",
            "fake.test",
            "demo.example",
            "nope.invalid",
            "1.168.192.in-addr.arpa",
        ],
    )
    def test_internal_domains_not_enrichable(self, domain: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.DOMAIN, domain)
        assert enrichable is False

    @pytest.mark.parametrize("domain", ["evil.com", "malware.net", "c2.attacker.org"])
    def test_public_domains_enrichable(self, domain: str) -> None:
        enrichable, reason = is_enrichable(IndicatorType.DOMAIN, domain)
        assert enrichable is True
        assert reason is None


class TestURLEnrichable:
    def test_url_with_private_ip_not_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.URL, "http://192.168.1.1/admin")
        assert enrichable is False

    def test_url_with_internal_domain_not_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.URL, "https://app.internal/api")
        assert enrichable is False

    def test_url_with_public_domain_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.URL, "https://evil.com/payload")
        assert enrichable is True

    def test_url_with_public_ip_enrichable(self) -> None:
        enrichable, reason = is_enrichable(IndicatorType.URL, "http://8.8.8.8/test")
        assert enrichable is True


class TestAlwaysEnrichableTypes:
    """Hash, email, and account types have no validation — always enrichable."""

    @pytest.mark.parametrize(
        ("itype", "value"),
        [
            (IndicatorType.HASH_MD5, "d41d8cd98f00b204e9800998ecf8427e"),
            (IndicatorType.HASH_SHA1, "da39a3ee5e6b4b0d3255bfef95601890afd80709"),
            (IndicatorType.HASH_SHA256, "e3b0c44298fc1c149afbf4c8996fb924"),
            (IndicatorType.EMAIL, "attacker@evil.com"),
            (IndicatorType.ACCOUNT, "jsmith"),
        ],
    )
    def test_always_enrichable(self, itype: IndicatorType, value: str) -> None:
        enrichable, reason = is_enrichable(itype, value)
        assert enrichable is True
        assert reason is None
