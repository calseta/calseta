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
                    "query_params": {
                        "ipAddress": "{{indicator.value}}",
                        "maxAgeInDays": "90",
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
        "description": (
            "Okta Management API v1 — user account, "
            "group membership, and manager lookups."
        ),
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
                {
                    "name": "user_manager",
                    "method": "GET",
                    "url": "https://{{auth.domain}}/api/v1/users/{{steps.user_lookup.response.id}}/linkedObjects/manager",
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
            "account, group membership, and manager lookups."
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
                {
                    "name": "user_manager",
                    "method": "GET",
                    "url": (
                        "https://graph.microsoft.com/v1.0/"
                        "users/"
                        "{{steps.user_lookup.response.id}}"
                        "/manager?$select=displayName,"
                        "mail,jobTitle"
                    ),
                    "headers": {
                        "Authorization": "Bearer {{steps.token.response.access_token}}",
                    },
                    "timeout_seconds": 30,
                    "expected_status": [200],
                    "not_found_status": [404],
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
    # -----------------------------------------------------------------
    # Internal IP Intelligence — classify IPs as VPN, cloud, datacenter,
    # or corporate. Surface cloud account details for cloud IPs.
    # -----------------------------------------------------------------
    {
        "provider_name": "internal_ip_intel",
        "display_name": "Internal IP Intelligence",
        "description": (
            "Internal CMDB / IPAM lookup — classifies IPs as VPN, cloud, "
            "datacenter, or corporate. For cloud IPs, surfaces the cloud "
            "account name, owner, region, and provider."
        ),
        "supported_indicator_types": ["ip"],
        "auth_type": "api_key",
        "env_var_mapping": {"api_key": "INTERNAL_IP_INTEL_API_KEY"},
        "default_cache_ttl_seconds": 1800,
        "cache_ttl_by_type": {"ip": 1800},
        "http_config": {
            "steps": [
                {
                    "name": "lookup",
                    "method": "GET",
                    "url": "{{auth.base_url}}/api/v1/ip/{{indicator.value}}",
                    "headers": {
                        "Authorization": "Bearer {{auth.api_key}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 15,
                    "expected_status": [200],
                    "not_found_status": [404],
                },
            ],
        },
        "malice_rules": {
            "rules": [],
            "default_verdict": "Pending",
            "not_found_verdict": "Pending",
        },
    },
    # -----------------------------------------------------------------
    # HR / Insider Risk — insider threat group membership, manager chain,
    # employment status, risk flags.
    # -----------------------------------------------------------------
    {
        "provider_name": "hr_insider_risk",
        "display_name": "HR / Insider Risk",
        "description": (
            "HR system integration — surfaces insider threat group "
            "membership (leavers, new hires, executives/VIPs, security "
            "team, contractors, PIP), manager chain, hire date, and "
            "employment risk flags."
        ),
        "supported_indicator_types": ["account"],
        "auth_type": "api_key",
        "env_var_mapping": {"api_key": "HR_INSIDER_RISK_API_KEY"},
        "default_cache_ttl_seconds": 900,
        "cache_ttl_by_type": {"account": 900},
        "http_config": {
            "steps": [
                {
                    "name": "employee_lookup",
                    "method": "GET",
                    "url": "{{auth.base_url}}/api/v1/employees/{{indicator.value | urlencode}}",
                    "headers": {
                        "Authorization": "Bearer {{auth.api_key}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 15,
                    "expected_status": [200],
                    "not_found_status": [404],
                },
            ],
        },
        "malice_rules": {
            "rules": [],
            "default_verdict": "Pending",
            "not_found_verdict": "Pending",
        },
    },
    # -----------------------------------------------------------------
    # Asset Management — devices assigned to a user from Intune / Jamf /
    # CMDB, with EDR agent status and last check-in.
    # -----------------------------------------------------------------
    {
        "provider_name": "asset_management",
        "display_name": "Asset Management",
        "description": (
            "Unified asset management lookup (Intune, Jamf, CMDB) — "
            "returns devices assigned to a user with OS version, "
            "compliance status, EDR agent state, last user login, "
            "and network connection details."
        ),
        "supported_indicator_types": ["account"],
        "auth_type": "api_key",
        "env_var_mapping": {"api_key": "ASSET_MGMT_API_KEY"},
        "default_cache_ttl_seconds": 600,
        "cache_ttl_by_type": {"account": 600},
        "http_config": {
            "steps": [
                {
                    "name": "device_lookup",
                    "method": "GET",
                    "url": "{{auth.base_url}}/api/v1/users/{{indicator.value | urlencode}}/devices",
                    "headers": {
                        "Authorization": "Bearer {{auth.api_key}}",
                        "Accept": "application/json",
                    },
                    "timeout_seconds": 15,
                    "expected_status": [200],
                    "not_found_status": [404],
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
         "user_lookup.profile.department", "department",
         "string", "Department"),
        ("okta", "account",
         "user_lookup.profile.title", "title",
         "string", "Job title"),
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
    # Internal IP Intelligence
    result.extend([
        ("internal_ip_intel", "ip",
         "classification", "classification",
         "string", "IP classification (external_unknown, corporate, cloud)"),
        ("internal_ip_intel", "ip",
         "network_zone", "network_zone",
         "string", "Network zone"),
        ("internal_ip_intel", "ip",
         "is_vpn", "is_vpn",
         "bool", "Is VPN IP"),
        ("internal_ip_intel", "ip",
         "is_cloud", "is_cloud",
         "bool", "Is cloud IP"),
        ("internal_ip_intel", "ip",
         "is_datacenter", "is_datacenter",
         "bool", "Is datacenter IP"),
        ("internal_ip_intel", "ip",
         "is_internal", "is_internal",
         "bool", "Is internal/recognized IP"),
        ("internal_ip_intel", "ip",
         "known_asset", "known_asset",
         "bool", "IP belongs to a known managed asset"),
        ("internal_ip_intel", "ip",
         "previous_sightings", "previous_sightings",
         "number", "Number of previous sightings in environment"),
    ])
    # HR / Insider Risk
    result.extend([
        ("hr_insider_risk", "account",
         "employee_id", "employee_id",
         "string", "HR employee ID"),
        ("hr_insider_risk", "account",
         "employment_status", "employment_status",
         "string", "Employment status"),
        ("hr_insider_risk", "account",
         "employment_type", "employment_type",
         "string", "Employment type (full_time, contractor)"),
        ("hr_insider_risk", "account",
         "hire_date", "hire_date",
         "string", "Hire date"),
        ("hr_insider_risk", "account",
         "manager.name", "manager_name",
         "string", "Manager name"),
        ("hr_insider_risk", "account",
         "manager.email", "manager_email",
         "string", "Manager email"),
        ("hr_insider_risk", "account",
         "insider_threat_groups",
         "insider_threat_groups", "list",
         "Insider threat group memberships"),
        ("hr_insider_risk", "account",
         "risk_flags", "risk_flags",
         "list", "Active risk flags"),
        ("hr_insider_risk", "account",
         "notice_period_active",
         "notice_period_active", "bool",
         "Is notice period active (leaver)"),
    ])
    # Asset Management
    result.extend([
        ("asset_management", "account",
         "total_devices", "total_devices",
         "int", "Total assigned devices"),
        ("asset_management", "account",
         "devices.0.device_name",
         "primary_device_name", "string",
         "Primary device name"),
        ("asset_management", "account",
         "devices.0.os", "primary_device_os",
         "string", "Primary device OS"),
        ("asset_management", "account",
         "devices.0.compliance_status",
         "primary_device_compliance", "string",
         "Primary device compliance status"),
        ("asset_management", "account",
         "devices.0.edr.agent",
         "primary_edr_agent", "string",
         "Primary device EDR agent"),
        ("asset_management", "account",
         "devices.0.edr.status",
         "primary_edr_status", "string",
         "Primary device EDR status"),
        ("asset_management", "account",
         "devices.0.managed_by",
         "primary_device_managed_by", "string",
         "Primary device management platform"),
        ("asset_management", "account",
         "devices.0.network.last_ip",
         "primary_device_last_ip", "string",
         "Primary device last IP"),
    ])
    return result


_BUILTIN_FIELD_EXTRACTIONS = _build_extractions()


# ---------------------------------------------------------------------------
# Mock responses — returned when ENRICHMENT_MOCK_MODE=true
# Keyed by indicator type; each has "raw", "extracted", and "malice"
# ---------------------------------------------------------------------------

_MOCK_RESPONSES: dict[str, dict[str, object]] = {
    "virustotal": {
        "ip": {
            "raw": {
                "data": {
                    "id": "185.220.101.34",
                    "type": "ip_address",
                    "attributes": {
                        "country": "DE",
                        "as_owner": "Zwiebelfreunde e.V.",
                        "asn": 205100,
                        "network": "185.220.101.0/24",
                        "reputation": -42,
                        "tags": ["tor", "proxy"],
                        "categories": {"Forcepoint ThreatSeeker": "proxy"},
                        "last_analysis_stats": {
                            "malicious": 14,
                            "suspicious": 2,
                            "harmless": 52,
                            "undetected": 12,
                        },
                    },
                },
            },
            "extracted": {
                "malicious_count": 14,
                "suspicious_count": 2,
                "reputation": -42,
                "tags": ["tor", "proxy"],
                "country": "DE",
                "as_owner": "Zwiebelfreunde e.V.",
                "asn": 205100,
                "network": "185.220.101.0/24",
                "categories": {"Forcepoint ThreatSeeker": "proxy"},
            },
            "malice": "Malicious",
        },
        "domain": {
            "raw": {
                "data": {
                    "id": "evil-c2.example.com",
                    "type": "domain",
                    "attributes": {
                        "registrar": "Namecheap Inc.",
                        "creation_date": 1701388800,
                        "reputation": -15,
                        "tags": ["c2", "malware"],
                        "categories": {},
                        "last_analysis_stats": {
                            "malicious": 8,
                            "suspicious": 1,
                            "harmless": 60,
                            "undetected": 11,
                        },
                    },
                },
            },
            "extracted": {
                "malicious_count": 8,
                "suspicious_count": 1,
                "reputation": -15,
                "tags": ["c2", "malware"],
                "registrar": "Namecheap Inc.",
                "creation_date": 1701388800,
                "categories": {},
            },
            "malice": "Malicious",
        },
        "hash_sha256": {
            "raw": {
                "data": {
                    "id": "a1b2c3d4e5f6...",
                    "type": "file",
                    "attributes": {
                        "meaningful_name": "svchost_update.exe",
                        "type_description": "Win32 EXE",
                        "size": 245760,
                        "reputation": -50,
                        "tags": ["emotet", "trojan"],
                        "last_analysis_stats": {
                            "malicious": 48,
                            "suspicious": 3,
                            "harmless": 5,
                            "undetected": 14,
                        },
                    },
                },
            },
            "extracted": {
                "malicious_count": 48,
                "suspicious_count": 3,
                "reputation": -50,
                "tags": ["emotet", "trojan"],
                "meaningful_name": "svchost_update.exe",
                "type_description": "Win32 EXE",
                "size": 245760,
            },
            "malice": "Malicious",
        },
    },
    "abuseipdb": {
        "ip": {
            "raw": {
                "data": {
                    "ipAddress": "185.220.101.34",
                    "isPublic": True,
                    "abuseConfidenceScore": 100,
                    "countryCode": "DE",
                    "isp": "Zwiebelfreunde e.V.",
                    "usageType": "Reserved",
                    "isTor": True,
                    "isWhitelisted": False,
                    "totalReports": 2847,
                    "numDistinctUsers": 312,
                    "lastReportedAt": "2026-03-06T12:34:56Z",
                },
            },
            "extracted": {
                "abuse_confidence_score": 100,
                "total_reports": 2847,
                "country_code": "DE",
                "isp": "Zwiebelfreunde e.V.",
                "usage_type": "Reserved",
                "is_whitelisted": False,
                "is_tor": True,
                "is_public": True,
                "num_distinct_users": 312,
                "last_reported_at": "2026-03-06T12:34:56Z",
            },
            "malice": "Malicious",
        },
    },
    "okta": {
        "account": {
            "raw": {
                "user_lookup": {
                    "id": "00u1a2b3c4d5e6f7g8",
                    "status": "ACTIVE",
                    "created": "2024-06-15T09:00:00.000Z",
                    "lastLogin": "2026-03-06T14:22:00.000Z",
                    "passwordChanged": "2026-01-10T08:00:00.000Z",
                    "profile": {
                        "login": "j.martinez@contoso.com",
                        "email": "j.martinez@contoso.com",
                        "firstName": "Jorge",
                        "lastName": "Martinez",
                        "department": "Engineering",
                        "title": "Senior Engineer",
                    },
                },
                "user_groups": [
                    {"id": "00g1", "profile": {"name": "Engineering"}},
                    {"id": "00g2", "profile": {"name": "VPN-Users"}},
                    {"id": "00g3", "profile": {"name": "AWS-ReadOnly"}},
                ],
                "user_manager": [
                    {
                        "id": "00u9z8y7x6w5v4u3t2",
                        "status": "ACTIVE",
                        "profile": {
                            "login": "s.patel@contoso.com",
                            "email": "s.patel@contoso.com",
                            "firstName": "Sunita",
                            "lastName": "Patel",
                            "title": "VP of Engineering",
                        },
                    },
                ],
            },
            "extracted": {
                "user_id": "00u1a2b3c4d5e6f7g8",
                "login": "j.martinez@contoso.com",
                "email": "j.martinez@contoso.com",
                "first_name": "Jorge",
                "last_name": "Martinez",
                "status": "ACTIVE",
                "department": "Engineering",
                "title": "Senior Engineer",
                "created": "2024-06-15T09:00:00.000Z",
                "last_login": "2026-03-06T14:22:00.000Z",
                "password_changed": "2026-01-10T08:00:00.000Z",
                "groups": ["Engineering", "VPN-Users", "AWS-ReadOnly"],
                "manager_name": "Sunita Patel",
                "manager_email": "s.patel@contoso.com",
                "manager_title": "VP of Engineering",
            },
            "malice": "Pending",
        },
    },
    "entra": {
        "account": {
            "raw": {
                "user_lookup": {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "userPrincipalName": "j.martinez@contoso.com",
                    "displayName": "Jorge Martinez",
                    "mail": "j.martinez@contoso.com",
                    "accountEnabled": True,
                    "department": "Engineering",
                    "jobTitle": "Senior Engineer",
                    "lastPasswordChangeDateTime": "2026-01-10T08:00:00Z",
                },
                "user_groups": {
                    "value": [
                        {"displayName": "Engineering"},
                        {"displayName": "GlobalAdmins"},
                        {"displayName": "Azure-Contributors"},
                    ],
                },
                "user_manager": {
                    "displayName": "Sunita Patel",
                    "mail": "s.patel@contoso.com",
                    "jobTitle": "VP of Engineering",
                },
            },
            "extracted": {
                "object_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "user_principal_name": "j.martinez@contoso.com",
                "display_name": "Jorge Martinez",
                "mail": "j.martinez@contoso.com",
                "account_enabled": True,
                "department": "Engineering",
                "job_title": "Senior Engineer",
                "last_password_change": "2026-01-10T08:00:00Z",
                "groups": [
                    "Engineering",
                    "GlobalAdmins",
                    "Azure-Contributors",
                ],
                "manager_name": "Sunita Patel",
                "manager_email": "s.patel@contoso.com",
                "manager_title": "VP of Engineering",
            },
            "malice": "Pending",
        },
    },
    "internal_ip_intel": {
        "ip": {
            "raw": {
                "classification": "external_unknown",
                "network_zone": "external",
                "is_vpn": False,
                "is_cloud": False,
                "is_datacenter": False,
                "is_internal": False,
                "known_asset": False,
                "previous_sightings": 0,
                "first_seen_in_environment": None,
                "notes": "IP not recognized in any internal network, "
                "VPN pool, or managed cloud account.",
            },
            "extracted": {
                "classification": "external_unknown",
                "network_zone": "external",
                "is_vpn": False,
                "is_cloud": False,
                "is_datacenter": False,
                "is_internal": False,
                "known_asset": False,
                "previous_sightings": 0,
            },
            "malice": "Suspicious",
        },
        "default": {
            "raw": {
                "classification": "external_unknown",
                "network_zone": "external",
                "is_vpn": False,
                "is_cloud": False,
                "is_datacenter": False,
                "is_internal": False,
                "known_asset": False,
                "previous_sightings": 0,
                "notes": "IP not recognized in any internal network, "
                "VPN pool, or managed cloud account.",
            },
            "extracted": {
                "classification": "external_unknown",
                "network_zone": "external",
                "is_vpn": False,
                "is_cloud": False,
                "is_datacenter": False,
                "is_internal": False,
                "known_asset": False,
                "previous_sightings": 0,
            },
            "malice": "Suspicious",
        },
    },
    "hr_insider_risk": {
        "account": {
            "raw": {
                "employee_id": "EMP-10042",
                "email": "j.martinez@contoso.com",
                "full_name": "Jorge Martinez",
                "employment_status": "active",
                "employment_type": "full_time",
                "hire_date": "2024-06-15",
                "department": "Engineering",
                "title": "Senior Engineer",
                "location": "New York, NY",
                "manager": {
                    "name": "Sunita Patel",
                    "email": "s.patel@contoso.com",
                    "title": "VP of Engineering",
                },
                "insider_threat_groups": [
                    "new_hire_watchlist",
                    "privileged_access",
                ],
                "risk_flags": [],
                "last_review_date": "2026-02-01",
                "notice_period_active": False,
                "all_groups_available": [
                    "executives_vip",
                    "leavers",
                    "new_hire_watchlist",
                    "contractors",
                    "privileged_access",
                    "pip_active",
                    "security_team",
                    "finance_team",
                    "board_members",
                ],
            },
            "extracted": {
                "employee_id": "EMP-10042",
                "employment_status": "active",
                "employment_type": "full_time",
                "hire_date": "2024-06-15",
                "location": "New York, NY",
                "manager_name": "Sunita Patel",
                "manager_email": "s.patel@contoso.com",
                "insider_threat_groups": [
                    "new_hire_watchlist",
                    "privileged_access",
                ],
                "risk_flags": [],
                "notice_period_active": False,
                "last_review_date": "2026-02-01",
            },
            "malice": "Pending",
        },
    },
    "asset_management": {
        "account": {
            "raw": {
                "user_email": "j.martinez@contoso.com",
                "total_devices": 2,
                "devices": [
                    {
                        "device_id": "DEV-A1B2C3",
                        "device_name": "JMartinez-MBP",
                        "device_type": "laptop",
                        "manufacturer": "Apple",
                        "model": "MacBook Pro 16-inch (M3 Max)",
                        "os": "macOS",
                        "os_version": "15.3.1",
                        "serial_number": "C02ZX1ABCDEF",
                        "managed_by": "Jamf",
                        "compliance_status": "compliant",
                        "encryption_enabled": True,
                        "firewall_enabled": True,
                        "last_check_in": "2026-03-06T14:15:00Z",
                        "edr": {
                            "agent": "CrowdStrike Falcon",
                            "agent_version": "7.14.17409",
                            "status": "online",
                            "last_seen": "2026-03-06T14:22:00Z",
                            "prevention_policy": "Workstation-High",
                            "sensor_mode": "kernel",
                        },
                        "last_user_login": "2026-03-06T08:30:00Z",
                        "network": {
                            "last_ip": "10.0.15.201",
                            "connection_type": "corporate_vpn",
                            "wifi_ssid": "Contoso-Corp",
                        },
                    },
                    {
                        "device_id": "DEV-D4E5F6",
                        "device_name": "JMartinez-iPhone",
                        "device_type": "mobile",
                        "manufacturer": "Apple",
                        "model": "iPhone 16 Pro",
                        "os": "iOS",
                        "os_version": "19.3",
                        "serial_number": "F17ZN4ABCDEF",
                        "managed_by": "Intune",
                        "compliance_status": "compliant",
                        "encryption_enabled": True,
                        "last_check_in": "2026-03-06T13:45:00Z",
                        "edr": None,
                        "last_user_login": "2026-03-06T07:00:00Z",
                        "network": {
                            "last_ip": "192.168.1.42",
                            "connection_type": "cellular",
                            "wifi_ssid": None,
                        },
                    },
                ],
            },
            "extracted": {
                "total_devices": 2,
                "device_names": ["JMartinez-MBP", "JMartinez-iPhone"],
                "device_summary": [
                    {
                        "name": "JMartinez-MBP",
                        "type": "laptop",
                        "os": "macOS 15.3.1",
                        "managed_by": "Jamf",
                        "compliance": "compliant",
                        "edr_agent": "CrowdStrike Falcon",
                        "edr_status": "online",
                        "last_ip": "10.0.15.201",
                        "last_login": "2026-03-06T08:30:00Z",
                    },
                    {
                        "name": "JMartinez-iPhone",
                        "type": "mobile",
                        "os": "iOS 19.3",
                        "managed_by": "Intune",
                        "compliance": "compliant",
                        "edr_agent": None,
                        "edr_status": None,
                        "last_ip": "192.168.1.42",
                        "last_login": "2026-03-06T07:00:00Z",
                    },
                ],
                "all_compliant": True,
                "edr_coverage": "partial",
                "encryption_all_enabled": True,
            },
            "malice": "Pending",
        },
    },
}

# Also provide hash_md5 and hash_sha1 as aliases for the sha256 mock
_MOCK_RESPONSES["virustotal"]["hash_md5"] = (
    _MOCK_RESPONSES["virustotal"]["hash_sha256"]
)
_MOCK_RESPONSES["virustotal"]["hash_sha1"] = (
    _MOCK_RESPONSES["virustotal"]["hash_sha256"]
)


async def seed_builtin_providers(db: AsyncSession) -> None:
    """Idempotently insert all builtin enrichment provider configs."""
    inserted = 0
    updated = 0

    for defn in _BUILTIN_PROVIDERS:
        result = await db.execute(
            select(EnrichmentProvider).where(
                EnrichmentProvider.provider_name == defn["provider_name"]
            )
        )
        existing = result.scalar_one_or_none()

        mock = _MOCK_RESPONSES.get(defn["provider_name"])

        if existing is not None:
            # Update http_config and mock_responses on existing builtins
            changed = False
            if existing.http_config != defn["http_config"]:
                existing.http_config = defn["http_config"]
                changed = True
            if existing.mock_responses != mock:
                existing.mock_responses = mock
                changed = True
            if changed:
                updated += 1
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
                mock_responses=mock,
            )
        )
        inserted += 1

    if inserted > 0 or updated > 0:
        await db.flush()
        logger.info(
            "builtin_enrichment_providers_seeded",
            inserted=inserted,
            updated=updated,
        )
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
