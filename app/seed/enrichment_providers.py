"""
Seed builtin enrichment providers and their field extractions.

Called at startup to ensure the 4 builtin providers (VirusTotal, AbuseIPDB,
Okta, Entra) exist as rows in enrichment_providers. Idempotent — skips
providers that already exist. Also seeds ~50 system field extraction rows.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
from app.db.models.enrichment_provider import EnrichmentProvider

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Builtin provider definitions
# ---------------------------------------------------------------------------

_BUILTIN_PROVIDERS: list[dict] = [
    {
        "provider_name": "virustotal",
        "display_name": "VirusTotal",
        "description": "VirusTotal v3 API — IP, domain, and file hash reputation lookups.",
        "supported_indicator_types": ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256"],
        "auth_type": "api_key",
        "env_var_mapping": {"api_key": "VIRUSTOTAL_API_KEY"},
        "default_cache_ttl_seconds": 3600,
        "cache_ttl_by_type": {
            "ip": 3600,
            "domain": 21600,
            "hash_md5": 86400,
            "hash_sha1": 86400,
            "hash_sha256": 86400,
        },
        "http_config": {
            "steps": [
                {
                    "name": "lookup",
                    "method": "GET",
                    "url": "https://www.virustotal.com/api/v3/ip_addresses/{{indicator.value}}",
                    "headers": {"x-apikey": "{{auth.api_key}}"},
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "not_found_status": [404],
                }
            ],
            "url_templates_by_type": {
                "ip": "https://www.virustotal.com/api/v3/ip_addresses/{{indicator.value}}",
                "domain": "https://www.virustotal.com/api/v3/domains/{{indicator.value}}",
                "hash_md5": "https://www.virustotal.com/api/v3/files/{{indicator.value}}",
                "hash_sha1": "https://www.virustotal.com/api/v3/files/{{indicator.value}}",
                "hash_sha256": "https://www.virustotal.com/api/v3/files/{{indicator.value}}",
            },
        },
        "malice_rules": {
            "rules": [
                {
                    "field": "data.attributes.last_analysis_stats.malicious",
                    "operator": ">",
                    "value": 0,
                    "verdict": "Malicious",
                },
                {
                    "field": "data.attributes.last_analysis_stats.suspicious",
                    "operator": ">",
                    "value": 0,
                    "verdict": "Suspicious",
                },
            ],
            "default_verdict": "Benign",
            "not_found_verdict": "Pending",
        },
    },
    {
        "provider_name": "abuseipdb",
        "display_name": "AbuseIPDB",
        "description": "AbuseIPDB v2 API — IP address abuse confidence scoring.",
        "supported_indicator_types": ["ip"],
        "auth_type": "api_key",
        "env_var_mapping": {"api_key": "ABUSEIPDB_API_KEY"},
        "default_cache_ttl_seconds": 3600,
        "cache_ttl_by_type": {"ip": 3600},
        "http_config": {
            "steps": [
                {
                    "name": "lookup",
                    "method": "GET",
                    "url": "https://api.abuseipdb.com/api/v2/check",
                    "headers": {
                        "Key": "{{auth.api_key}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                }
            ],
        },
        "malice_rules": {
            "rules": [
                {
                    "field": "data.abuseConfidenceScore",
                    "operator": ">=",
                    "value": 75,
                    "verdict": "Malicious",
                },
                {
                    "field": "data.abuseConfidenceScore",
                    "operator": ">=",
                    "value": 25,
                    "verdict": "Suspicious",
                },
            ],
            "default_verdict": "Benign",
            "not_found_verdict": "Pending",
        },
    },
    {
        "provider_name": "okta",
        "display_name": "Okta",
        "description": "Okta Management API v1 — user account and group membership lookups.",
        "supported_indicator_types": ["account"],
        "auth_type": "api_token",
        "env_var_mapping": {"domain": "OKTA_DOMAIN", "api_token": "OKTA_API_TOKEN"},
        "default_cache_ttl_seconds": 900,
        "cache_ttl_by_type": {"account": 900},
        "http_config": {
            "steps": [
                {
                    "name": "user_lookup",
                    "method": "GET",
                    "url": "https://{{auth.domain}}/api/v1/users/{{indicator.value | urlencode}}",
                    "headers": {
                        "Authorization": "SSWS {{auth.api_token}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "not_found_status": [404],
                },
                {
                    "name": "user_groups",
                    "method": "GET",
                    "url": "https://{{auth.domain}}/api/v1/users/{{steps.user_lookup.response.id}}/groups",
                    "headers": {
                        "Authorization": "SSWS {{auth.api_token}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "optional": True,
                },
            ],
        },
        "malice_rules": {
            "rules": [],
            "default_verdict": "Pending",
            "not_found_verdict": "Pending",
        },
    },
    {
        "provider_name": "entra",
        "display_name": "Microsoft Entra ID",
        "description": (
            "Microsoft Graph API v1.0 — Azure AD user "
            "account and group membership lookups."
        ),
        "supported_indicator_types": ["account"],
        "auth_type": "oauth2_client_credentials",
        "env_var_mapping": {
            "tenant_id": "ENTRA_TENANT_ID",
            "client_id": "ENTRA_CLIENT_ID",
            "client_secret": "ENTRA_CLIENT_SECRET",
        },
        "default_cache_ttl_seconds": 900,
        "cache_ttl_by_type": {"account": 900},
        "http_config": {
            "steps": [
                {
                    "name": "token",
                    "method": "POST",
                    "url": "https://login.microsoftonline.com/{{auth.tenant_id}}/oauth2/v2.0/token",
                    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                    "form_body": {
                        "client_id": "{{auth.client_id}}",
                        "client_secret": "{{auth.client_secret}}",
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                },
                {
                    "name": "user_lookup",
                    "method": "GET",
                    "url": (
                        "https://graph.microsoft.com/v1.0/"
                        "users/{{indicator.value | urlencode}}"
                        "?$select=id,displayName,"
                        "userPrincipalName,mail,"
                        "accountEnabled,department,"
                        "jobTitle,"
                        "lastPasswordChangeDateTime"
                    ),
                    "headers": {
                        "Authorization": "Bearer {{steps.token.response.access_token}}",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "not_found_status": [404],
                },
                {
                    "name": "user_groups",
                    "method": "GET",
                    "url": (
                        "https://graph.microsoft.com/v1.0/"
                        "users/"
                        "{{steps.user_lookup.response.id}}"
                        "/memberOf?$select=displayName"
                    ),
                    "headers": {
                        "Authorization": "Bearer {{steps.token.response.access_token}}",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "optional": True,
                },
            ],
        },
        "malice_rules": {
            "rules": [],
            "default_verdict": "Pending",
            "not_found_verdict": "Pending",
        },
    },
]


# ---------------------------------------------------------------------------
# Builtin field extraction definitions
# ---------------------------------------------------------------------------

# (provider, type, source_path, target_key, value_type, desc)
_E = tuple[str, str, str, str, str, str]

# VT common fields replicated per indicator type
_VT_STATS = "data.attributes.last_analysis_stats"
_VT_ATTRS = "data.attributes"


def _vt_common(itype: str) -> list[_E]:
    """Common VT extractions shared by all indicator types."""
    return [
        ("virustotal", itype,
         f"{_VT_STATS}.malicious", "malicious_count",
         "int", "Engines flagging malicious"),
        ("virustotal", itype,
         f"{_VT_STATS}.suspicious", "suspicious_count",
         "int", "Engines flagging suspicious"),
        ("virustotal", itype,
         f"{_VT_ATTRS}.reputation", "reputation",
         "int", "VT reputation score"),
        ("virustotal", itype,
         f"{_VT_ATTRS}.tags", "tags",
         "list", "VT tags"),
    ]


def _vt_ip() -> list[_E]:
    return _vt_common("ip") + [
        ("virustotal", "ip",
         f"{_VT_ATTRS}.country", "country",
         "string", "Country code"),
        ("virustotal", "ip",
         f"{_VT_ATTRS}.as_owner", "as_owner",
         "string", "AS owner name"),
        ("virustotal", "ip",
         f"{_VT_ATTRS}.asn", "asn",
         "int", "Autonomous system number"),
        ("virustotal", "ip",
         f"{_VT_ATTRS}.network", "network",
         "string", "IP network CIDR"),
        ("virustotal", "ip",
         f"{_VT_ATTRS}.categories", "categories",
         "dict", "VT categories"),
    ]


def _vt_domain() -> list[_E]:
    return _vt_common("domain") + [
        ("virustotal", "domain",
         f"{_VT_ATTRS}.registrar", "registrar",
         "string", "Domain registrar"),
        ("virustotal", "domain",
         f"{_VT_ATTRS}.creation_date", "creation_date",
         "int", "Domain creation date"),
        ("virustotal", "domain",
         f"{_VT_ATTRS}.categories", "categories",
         "dict", "VT categories"),
    ]


def _vt_hash(itype: str) -> list[_E]:
    return _vt_common(itype) + [
        ("virustotal", itype,
         f"{_VT_ATTRS}.meaningful_name", "meaningful_name",
         "string", "Meaningful file name"),
        ("virustotal", itype,
         f"{_VT_ATTRS}.type_description", "type_description",
         "string", "File type description"),
        ("virustotal", itype,
         f"{_VT_ATTRS}.size", "size",
         "int", "File size in bytes"),
    ]


def _build_extractions() -> list[_E]:
    result: list[_E] = []
    # VirusTotal
    result.extend(_vt_ip())
    result.extend(_vt_domain())
    result.extend(_vt_hash("hash_md5"))
    result.extend(_vt_hash("hash_sha1"))
    result.extend(_vt_hash("hash_sha256"))
    # AbuseIPDB
    result.extend([
        ("abuseipdb", "ip",
         "data.abuseConfidenceScore",
         "abuse_confidence_score", "int",
         "Abuse confidence score (0-100)"),
        ("abuseipdb", "ip",
         "data.totalReports", "total_reports",
         "int", "Total abuse reports"),
        ("abuseipdb", "ip",
         "data.countryCode", "country_code",
         "string", "Country code"),
        ("abuseipdb", "ip",
         "data.isp", "isp",
         "string", "Internet service provider"),
        ("abuseipdb", "ip",
         "data.usageType", "usage_type",
         "string", "IP usage type"),
        ("abuseipdb", "ip",
         "data.isWhitelisted", "is_whitelisted",
         "bool", "IP is whitelisted"),
        ("abuseipdb", "ip",
         "data.isTor", "is_tor",
         "bool", "Tor exit node"),
        ("abuseipdb", "ip",
         "data.isPublic", "is_public",
         "bool", "Public IP"),
        ("abuseipdb", "ip",
         "data.numDistinctUsers", "num_distinct_users",
         "int", "Distinct reporting users"),
        ("abuseipdb", "ip",
         "data.lastReportedAt", "last_reported_at",
         "string", "Last reported timestamp"),
    ])
    # Okta
    result.extend([
        ("okta", "account",
         "user_lookup.id", "user_id",
         "string", "Okta user ID"),
        ("okta", "account",
         "user_lookup.profile.login", "login",
         "string", "Okta login (email)"),
        ("okta", "account",
         "user_lookup.profile.email", "email",
         "string", "User email address"),
        ("okta", "account",
         "user_lookup.profile.firstName", "first_name",
         "string", "First name"),
        ("okta", "account",
         "user_lookup.profile.lastName", "last_name",
         "string", "Last name"),
        ("okta", "account",
         "user_lookup.status", "status",
         "string", "User status"),
        ("okta", "account",
         "user_lookup.created", "created",
         "string", "Account creation time"),
        ("okta", "account",
         "user_lookup.lastLogin", "last_login",
         "string", "Last login time"),
        ("okta", "account",
         "user_lookup.passwordChanged",
         "password_changed", "string",
         "Last password change"),
    ])
    # Entra
    result.extend([
        ("entra", "account",
         "user_lookup.id", "object_id",
         "string", "Azure AD object ID"),
        ("entra", "account",
         "user_lookup.userPrincipalName",
         "user_principal_name", "string",
         "User principal name"),
        ("entra", "account",
         "user_lookup.displayName", "display_name",
         "string", "Display name"),
        ("entra", "account",
         "user_lookup.mail", "mail",
         "string", "Email address"),
        ("entra", "account",
         "user_lookup.accountEnabled",
         "account_enabled", "bool",
         "Account is enabled"),
        ("entra", "account",
         "user_lookup.department", "department",
         "string", "Department"),
        ("entra", "account",
         "user_lookup.jobTitle", "job_title",
         "string", "Job title"),
        ("entra", "account",
         "user_lookup.lastPasswordChangeDateTime",
         "last_password_change", "string",
         "Last password change"),
    ])
    return result


_BUILTIN_FIELD_EXTRACTIONS = _build_extractions()


async def seed_builtin_providers(db: AsyncSession) -> None:
    """Idempotently insert all builtin enrichment provider configs."""
    inserted = 0

    for defn in _BUILTIN_PROVIDERS:
        existing = await db.execute(
            select(EnrichmentProvider).where(
                EnrichmentProvider.provider_name == defn["provider_name"]
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        db.add(
            EnrichmentProvider(
                provider_name=defn["provider_name"],
                display_name=defn["display_name"],
                description=defn.get("description"),
                is_builtin=True,
                is_active=True,
                supported_indicator_types=defn["supported_indicator_types"],
                http_config=defn["http_config"],
                auth_type=defn.get("auth_type", "no_auth"),
                auth_config=None,
                env_var_mapping=defn.get("env_var_mapping"),
                default_cache_ttl_seconds=defn.get("default_cache_ttl_seconds", 3600),
                cache_ttl_by_type=defn.get("cache_ttl_by_type"),
                malice_rules=defn.get("malice_rules"),
                mock_responses=None,
            )
        )
        inserted += 1

    if inserted > 0:
        await db.flush()
        logger.info("builtin_enrichment_providers_seeded", count=inserted)
    else:
        logger.debug("builtin_enrichment_providers_already_seeded")


async def seed_builtin_field_extractions(db: AsyncSession) -> None:
    """Idempotently insert all builtin enrichment field extraction rules."""
    inserted = 0

    for (
        provider_name,
        indicator_type,
        source_path,
        target_key,
        value_type,
        description,
    ) in _BUILTIN_FIELD_EXTRACTIONS:
        existing = await db.execute(
            select(EnrichmentFieldExtraction).where(
                EnrichmentFieldExtraction.provider_name == provider_name,
                EnrichmentFieldExtraction.indicator_type == indicator_type,
                EnrichmentFieldExtraction.source_path == source_path,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        db.add(
            EnrichmentFieldExtraction(
                provider_name=provider_name,
                indicator_type=indicator_type,
                source_path=source_path,
                target_key=target_key,
                value_type=value_type,
                is_system=True,
                is_active=True,
                description=description,
            )
        )
        inserted += 1

    if inserted > 0:
        await db.flush()
        logger.info("builtin_field_extractions_seeded", count=inserted)
    else:
        logger.debug("builtin_field_extractions_already_seeded")
