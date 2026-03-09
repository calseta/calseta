"""
Indicator enrichability validation — pure functions, no external dependencies.

Determines whether an indicator value is worth sending to external enrichment
providers. Non-routable IPs (RFC 1918, loopback, link-local, CGNAT, etc.) and
internal domains (.local, .internal, etc.) are skipped to avoid fabricated
verdicts from threat intel APIs that don't handle private addresses correctly.

Indicators are still persisted regardless — only external API enrichment is skipped.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.schemas.indicators import IndicatorType

# Domain suffixes that indicate internal/reserved names (case-insensitive)
_NON_ROUTABLE_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".home",
    ".lan",
    ".corp",
    ".test",
    ".example",
    ".invalid",
    ".arpa",
)

_NON_ROUTABLE_EXACT: frozenset[str] = frozenset({"localhost"})


def is_enrichable(indicator_type: IndicatorType, value: str) -> tuple[bool, str | None]:
    """
    Check whether an indicator should be sent to external enrichment providers.

    Returns (True, None) if enrichable, or (False, reason) if it should be skipped.
    """
    if indicator_type == IndicatorType.IP:
        return _is_ip_enrichable(value)
    if indicator_type == IndicatorType.DOMAIN:
        return _is_domain_enrichable(value)
    if indicator_type == IndicatorType.URL:
        return _is_url_enrichable(value)
    # Hash, email, account — always enrichable
    return True, None


def _is_ip_enrichable(value: str) -> tuple[bool, str | None]:
    """Return (False, reason) for non-global IPs (private, loopback, link-local, etc.)."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False, "invalid IP address format"

    if not addr.is_global:
        return False, f"non-routable IP address ({value})"
    return True, None


def _is_domain_enrichable(value: str) -> tuple[bool, str | None]:
    """Return (False, reason) for internal/reserved domain suffixes."""
    lower = value.lower().rstrip(".")
    if lower in _NON_ROUTABLE_EXACT:
        return False, f"reserved domain ({value})"
    for suffix in _NON_ROUTABLE_SUFFIXES:
        if lower == suffix.lstrip(".") or lower.endswith(suffix):
            return False, f"non-routable domain suffix ({value})"
    return True, None


def _is_url_enrichable(value: str) -> tuple[bool, str | None]:
    """Extract hostname from URL and delegate to IP or domain validator."""
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except Exception:
        return False, "invalid URL format"

    if not hostname:
        return False, "URL has no hostname"

    # Check if hostname is an IP address
    try:
        ipaddress.ip_address(hostname)
        return _is_ip_enrichable(hostname)
    except ValueError:
        pass

    return _is_domain_enrichable(hostname)
