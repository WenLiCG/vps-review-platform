"""Fail-closed public view of a verified historical import.

Original archives, evidence, reviewer declarations and prose remain private.
This module does no I/O, does not normalize historical facts, and never creates
new observations, review logs, or review timestamps. The schema below is an
explicit allowlist pinned by tests to the original 61-field catalog.
"""

from __future__ import annotations

from datetime import date, datetime
import math
import re
import unicodedata


PUBLIC_PROJECTION_VERSION = "vps-legacy-public/1"
MIGRATION_VERSION = "vps-legacy-import/1"
STATUSES = frozenset({"reported", "computed", "inferred", "official_current", "unknown", "conflict"})
_AXES = ("ipv4", "ipv6")
_CARRIERS = ("telecom", "unicom", "mobile")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_POST = re.compile(r"[1-9][0-9]{0,19}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z", re.ASCII)
_BUCKET = re.compile(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}–(?:\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}\Z", re.ASCII)
_CREDENTIAL = re.compile(
    r"password|passwd|secret|token|api[ _-]?key|authorization|bearer|credential|cookie|private[ _-]?key", re.I)
_IPV4 = re.compile(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}")
_URL = re.compile(r"[a-z][a-z0-9+.-]*://|www\.|mailto:|data:|javascript:", re.I)
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-f]+|[a-z][a-z0-9]+);", re.I)
_SECRET_VALUE = re.compile(
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
    r"[A-Za-z0-9_+-]{40,}")
_MISSING = object()


def _number(value):
    return ((type(value) is int and value.bit_length() <= 256)
            or (type(value) is float and math.isfinite(value)))


def _safe_label(value, private_names, maximum=128):
    """Labels, never prose: no paths, addresses, URLs, markup, or controls.

    Colons and both slash forms are deliberately forbidden, suppressing all
    literal IPv6 representations as well as embedded/relative filesystem paths.
    Dates and timestamp fields have separate strict grammars.
    """
    if not isinstance(value, str) or not value or len(value) > maximum:
        return False
    if value != value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
        return False
    normalized = unicodedata.normalize("NFKC", value)
    if any(character in normalized for character in '\\/:<>"`={}[]'):
        return False
    if any(pattern.search(normalized) for pattern in (_CREDENTIAL, _IPV4, _URL, _EMAIL, _ENTITY, _SECRET_VALUE)):
        return False
    if re.search(r"(?<!\w)'|'(?!\w)", normalized):
        return False
    if any(name in normalized.casefold() for name in private_names):
        return False
    # A compact public label may contain company/CPU punctuation. Arbitrary
    # sentences, shell syntax, source quotations and line breaks are not labels.
    return all(c.isalnum() or c in " .,_-+()&'@®™" for c in normalized)


def _timestamp(value):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def _date(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _bucket(value):
    if not isinstance(value, str) or not _BUCKET.fullmatch(value):
        return False
    start, end = value.split("–")
    if " " not in end:
        end = start[:10] + " " + end
    try:
        return datetime.fromisoformat(end) > datetime.fromisoformat(start)
    except ValueError:
        return False


def _enum(*values):
    return frozenset(values)


def _axes(schema):
    return {axis: schema for axis in _AXES}


_LABELS = {
    "city", "datacenter", "provider", "cpu_model",
}
_NUMBERS = {
    "monthly_transfer_tb", "vcpu", "sysbench_single_score", "sysbench_multi_score",
    "geekbench_single_score", "geekbench_multi_score", "memory_gb",
    "memory_read_mbps", "memory_write_mbps", "disk_gb",
    "disk_rnd4k_q1_read_mbps", "disk_rnd4k_q1_write_mbps",
    "disk_rnd4k_q32_read_mbps", "disk_rnd4k_q32_write_mbps",
    "disk_seq1m_q1_read_mbps", "disk_seq1m_q1_write_mbps",
    "disk_seq1m_q8_read_mbps", "disk_seq1m_q8_write_mbps",
    "hardware_total_score", "hardware_cpu_score", "hardware_gpu_score",
    "hardware_memory_score", "hardware_disk_score", "port_bandwidth_mbps", "ipv4_count",
}
_COUNT_FIELDS = {"blacklist_count", "flagged_count", "unlock_count", "native_count"}
_CLASSIFICATIONS = {key: "count" for key in (
    "hosting", "business", "residential", "mobile", "education", "government",
    "organization", "isp", "other", "unknown",
)}
_LATENCY = {carrier: {"mean_ms": "number", "sample_count": "count", "method": _enum(
    "ICMP", "TCP", "UDP", "icmp", "tcp", "udp", "arithmetic_mean",
    "non_null_arithmetic_mean", "weighted_mean", "sample_weighted_mean",
)} for carrier in _CARRIERS}

# Public route strings are restricted to single route labels. Narrative routes
# can mix cities, protocols, evidence, and addresses and are withheld rather than
# reinterpreted or summarized into a claim the original review did not make.
_ROUTE = _enum("163", "4837", "9929", "10099", "CMI", "CMIN2", "CN2", "CN2GIA", "CTGGIA")
FIELD_SCHEMAS = {
    **{key: "label" for key in _LABELS},
    **{key: "number" for key in _NUMBERS},
    **{key: _axes("count") for key in _COUNT_FIELDS},
    "test_date": "date",
    "operating_system": "os_label",
    "test_time": {"report_times": ["timestamp"], "half_hour_buckets": ["bucket"]},
    "country_region": {"continent": "label", "country": "label", "region": "label"},
    "ip_usage_location": _axes({"country": "label", "continent": "label"}),
    "ip_registered_location": _axes("label"),
    "asn": _axes("asn"),
    "ip_organization": _axes("label"),
    "monthly_price": {"amount": "number", "currency": "currency"},
    "billing_period": _enum("monthly", "quarterly", "semiannual", "annual", "biennial", "triennial"),
    "transfer_billing": _enum("outbound_only", "inbound_only", "both_directions", "unmetered", "one_direction_unspecified"),
    "virtualization": _enum("KVM", "LXC", "OpenVZ", "Xen", "VMware", "Hyper-V", "QEMU", "kvm", "lxc", "openvz"),
    "architecture": _enum("x86_64", "aarch64", "arm64", "i386", "i686", "armv7l"),
    "cpu_vendor": _enum("Intel", "AMD", "ARM", "Ampere", "Apple", "IBM"),
    "memory_overcommit": {"balloon": _enum("detected", "not_detected"), "ksm": _enum("detected", "not_detected")},
    "disk_type": _enum("NVMe SSD", "SATA SSD", "SSD", "HDD", "NVMe", "SAS SSD", "SAS HDD"),
    "ip_connectivity": _enum("NAT", "独立公网IPv4", "无IPv4", "多IP", "public_ipv4", "dedicated_ipv4", "nat", "no_ipv4", "multiple_ips"),
    "ipv6_connectivity": _enum("dual_stack", "ipv6_only", "available", "unavailable"),
    "routes_to_server": _axes({carrier: _ROUTE for carrier in _CARRIERS}),
    "routes_from_server": _axes({carrier: _ROUTE for carrier in _CARRIERS}),
    "ipv4_latency": _LATENCY,
    "ipv6_latency": _LATENCY,
    "nat_type": _enum("Open Internet", "No NAT", "Full Cone", "Restricted Cone", "Port Restricted Cone", "Restricted", "Symmetric", "开放无NAT", "开放网络无NAT", "无NAT", "open_internet", "full_cone", "restricted_cone", "port_restricted_cone", "symmetric"),
    "ip_origin": _axes(_enum("native", "broadcast")),
    "ip_classifications": _axes({"usage_counts": _CLASSIFICATIONS, "company_counts": _CLASSIFICATIONS}),
    "risk_counts": _axes({key: "count" for key in ("very_low", "low", "medium", "high", "very_high", "suspicious")}),
    "smtp25_outbound": _axes(_enum("available", "blocked")),
    "smtp25_inbound": _axes(_enum("available", "blocked")),
}


def _project(value, schema, names):
    """Return a safe value and whether any input was withheld. Never echo keys."""
    if value is None:
        return None, False
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            return None, True
        result, changed = {}, any(key not in schema for key in value)
        # Keep absent keys absent rather than synthesizing measurements or zeros.
        for key, child_schema in schema.items():
            if key in value:
                result[key], withheld = _project(value[key], child_schema, names)
                changed |= withheld
        return (result if result else None), changed or not result
    if isinstance(schema, list):
        if not isinstance(value, list) or len(value) > 256:
            return None, True
        result, changed = [], False
        for item in value:
            projected, withheld = _project(item, schema[0], names)
            # Null/redacted elements keep list positions explicit.
            result.append(projected)
            changed |= withheld
        return result, changed
    if isinstance(schema, frozenset):
        valid = isinstance(value, str) and value in schema and _safe_label(value, names)
    elif schema == "number":
        valid = _number(value)
    elif schema == "count":
        valid = type(value) is int and value >= 0 and _number(value)
    elif schema == "bool":
        valid = type(value) is bool
    elif schema == "label":
        valid = _safe_label(value, names)
    elif schema == "os_label":
        # GNU/Linux is a standard product name. Permit only this exact slash
        # phrase; every other slash/path remains forbidden. Return original text.
        valid = (isinstance(value, str) and len(value) <= 128
                 and _safe_label(value.replace("GNU/Linux", "GNU Linux"), names)
                 and not any(name in unicodedata.normalize("NFKC", value).casefold() for name in names))
    elif schema in {"asn", "currency"}:
        pattern = r"AS[0-9]{1,10}" if schema == "asn" else r"[A-Z]{3}"
        valid = isinstance(value, str) and bool(re.fullmatch(pattern, value, re.ASCII)) and _safe_label(value, names)
    elif schema == "date":
        valid = _date(value)
    elif schema == "timestamp":
        valid = _timestamp(value)
    elif schema == "bucket":
        valid = _bucket(value)
    else:
        valid = False
    return (value, False) if valid else (None, True)


def _has_value(value):
    if isinstance(value, dict):
        return any(_has_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_value(child) for child in value)
    return value is not None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _hash(value):
    return value if isinstance(value, str) and _HASH.fullmatch(value) else None


def _metadata(record, names):
    """Migration metadata contains no freely chosen strings or resource edges."""
    original = _mapping(record.get("provenance"))
    provenance, _ = _project(original, {
        "capture_method": _enum("browser_import"),
        "first_post_identity": _enum("historical_browser_import_declaration"),
        "max_report_depth": "count", "original_bytes_preserved": "bool",
        "missing_new_envelope_fields": [_enum("observations", "review_log")],
    }, names)
    provenance = provenance or {}
    if original.get("schema_version") == "vps-legacy-provenance/1":
        provenance["schema_version"] = "vps-legacy-provenance/1"
    provenance.update({
        "kind": "historical_import", "new_review_performed": False,
        "historical_declaration_independently_verified": False,
    })
    original = _mapping(record.get("validation"))
    validation, _ = _project(original, {
        "field_count": "count", "archive_status": _enum("ready", "partial"),
        "evidence_file_count": "count", "evidence_bytes": "count",
        "missing_new_envelope_fields": [_enum("observations", "review_log")],
    }, names)
    validation = validation or {}
    if original.get("validator_version") == "vps-pipeline-legacy/1":
        validation["validator_version"] = "vps-pipeline-legacy/1"
    for key in ("original_validator_sha256", "field_catalog_sha256"):
        if key in original:
            validation[key] = _hash(original[key])
    # Migration never attests a fresh review, regardless of malicious metadata.
    validation.update({"new_review_performed": False, "ai_invoked": False,
                       "review_attestation_verified": False, "new_analysis_accepted": False})
    return provenance, validation


def public_legacy_record(record):
    """Project verify_legacy's result into facts/status/provenance safe for JSON.

    ``projection_status`` describes the value projection, not confidence or the
    original fact status. ``unchanged`` includes a genuine historical null;
    ``partial`` retains some safe content; ``redacted`` withholds the value.
    Invalid/missing fact statuses become null, never a fabricated ``unknown``.
    """
    record = _mapping(record)
    manifest, analysis = _mapping(record.get("manifest")), _mapping(record.get("analysis"))
    ai_review = _mapping(analysis.get("ai_review"))
    names = tuple(unicodedata.normalize("NFKC", name.strip()).casefold() for name in (
        manifest.get("author"), ai_review.get("agent"), ai_review.get("reviewer"),
    ) if isinstance(name, str) and name.strip())
    facts = {}
    original_facts = _mapping(analysis.get("facts"))
    for field, schema in sorted(FIELD_SCHEMAS.items()):
        original = _mapping(original_facts.get(field))
        value, withheld = _project(original.get("value", _MISSING), schema, names)
        status = original.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            status, withheld = None, True
        facts[field] = {"status": status, "value": value, "projection_status": (
            "partial" if _has_value(value) else "redacted") if withheld else "unchanged"}
    post_id = record.get("post_id")
    if not isinstance(post_id, str) or not _POST.fullmatch(post_id):
        post_id = None
    canonical = f"https://www.nodeseek.com/post-{post_id}-1" if post_id else None
    if record.get("source_url") != canonical:
        canonical = None
    imported_at = record.get("imported_at")
    declared_complete = ai_review.get("completed")
    provenance, validation = _metadata(record, names)
    return {
        "id": _hash(record.get("id")), "post_id": post_id, "source_url": canonical,
        "status": "legacy_imported", "imported_at": imported_at if _timestamp(imported_at) else None,
        "manifest_sha256": _hash(record.get("manifest_sha256")),
        "analysis_sha256": _hash(record.get("analysis_sha256")),
        "bundle_sha256": _hash(record.get("bundle_sha256")),
        "migration_schema_version": MIGRATION_VERSION,
        "public_projection_schema_version": PUBLIC_PROJECTION_VERSION,
        "new_review_performed": False,
        "historical_review": {
            "completed_declared": declared_complete if type(declared_complete) is bool else None,
            "independently_verified": False,
        },
        "provenance": provenance,
        "validation": validation,
        "facts": facts,
    }
