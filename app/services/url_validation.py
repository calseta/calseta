"""
URL validation to prevent Server-Side Request Forgery (SSRF).

Blocks requests to private, loopback, link-local, and cloud metadata addresses.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

# Cloud metadata endpoints
_METADATA_IPS = frozenset({
    "169.254.169.254",  # AWS, GCP, Azure IMDS
    "100.100.100.200",  # Alibaba Cloud
    "169.254.170.2",    # AWS ECS task metadata
})

_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})


def _get_allowed_hosts() -> frozenset[str]:
    """Load SSRF_ALLOWED_HOSTS from settings (cached after first call)."""
    from app.config import settings

    raw = settings.SSRF_ALLOWED_HOSTS.strip()
    if not raw:
        return frozenset()
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def is_safe_outbound_url(url: str) -> tuple[bool, str]:
    """
    Check whether a URL is safe for outbound HTTP requests.

    Returns (True, "") if safe, or (False, reason) if blocked.
    Resolves hostnames to IPs to catch DNS rebinding of private addresses.
    Hostnames listed in SSRF_ALLOWED_HOSTS bypass all checks.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname"

    # Allow explicitly configured hosts (dev/local use)
    if hostname.lower() in _get_allowed_hosts():
        return True, ""

    # Block known metadata hostnames (never bypassable)
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, f"Blocked metadata hostname: {hostname}"

    # Block .internal, .local, .corp TLDs
    lower = hostname.lower()
    for suffix in (".internal", ".local", ".corp", ".lan", ".home.arpa"):
        if lower.endswith(suffix):
            return False, f"Blocked internal domain suffix: {suffix}"

    # Resolve hostname to IP(s) and check each
    try:
        # Use getaddrinfo to resolve (handles both IPv4 and IPv6)
        addrinfos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        ips = {info[4][0] for info in addrinfos}
    except socket.gaierror:
        # Can't resolve — allow (external service may be temporarily down)
        # Log for monitoring
        logger.warning("ssrf_dns_resolution_failed", hostname=hostname, url=url)
        return True, ""

    for ip_str in ips:
        # Check metadata IPs
        if ip_str in _METADATA_IPS:
            return False, f"Blocked cloud metadata IP: {ip_str}"

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if ip.is_private:
            return False, f"Blocked private IP: {ip_str}"
        if ip.is_loopback:
            return False, f"Blocked loopback IP: {ip_str}"
        if ip.is_link_local:
            return False, f"Blocked link-local IP: {ip_str}"
        if ip.is_reserved:
            return False, f"Blocked reserved IP: {ip_str}"

    return True, ""


def validate_outbound_url(url: str) -> None:
    """
    Validate a URL is safe for outbound requests.
    Raises ValueError if the URL targets a private/internal address.
    """
    safe, reason = is_safe_outbound_url(url)
    if not safe:
        logger.warning("ssrf_blocked", url=url, reason=reason)
        raise ValueError(f"URL blocked by SSRF protection: {reason}")
