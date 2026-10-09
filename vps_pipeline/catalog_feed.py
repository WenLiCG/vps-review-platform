"""Read-only, evidence-bound public input for the v5 catalog adapter.

The accepted-analysis ledger and historical imports are distinct sources. A new
pending archive cannot replace a previous accepted snapshot. No model, network,
archive export, review attestation, or write is performed here. Digests identify
verified bytes (legacy) or the canonical submitted JSON (accepted analyses).
"""

from __future__ import annotations

import json
import re
import unicodedata

from .analysis import OBSERVATION_KINDS, validate_submission
from .archive import verify_archive
from .legacy_projection import (
    FIELD_SCHEMAS, STATUSES, _date, _has_value, _number, _project, _safe_label, _timestamp,
)
from .store import ID, canonical_url, encoded, sha


_ENTRY_KINDS = frozenset({
    "measured_vps", "advertised_plan", "review_configuration_version", "measured_host",
})
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_POST = re.compile(r"[1-9][0-9]{0,19}\Z")
_MISSING = object()
_UNIT_WITH_SLASH = frozenset({
    "MB/s", "MiB/s", "GB/s", "GiB/s", "KB/s", "KiB/s", "Mbit/s", "Gbit/s",
    "Kbit/s", "events/s", "ops/s",
})
_NETWORK_ENUMS = {
    "ip_family": frozenset({"ipv4", "ipv6"}),
    "direction": frozenset({"to_server", "from_server", "outbound", "inbound"}),
    "transport": frozenset({"TCP", "UDP", "ICMP", "tcp", "udp", "icmp"}),
    "carrier": frozenset({"telecom", "unicom", "mobile", "电信", "联通", "移动"}),
}
_CARRIERS = {"telecom": "电信", "unicom": "联通", "mobile": "移动",
             "电信": "电信", "联通": "联通", "移动": "移动"}
_CARRIER_KEYS = {"电信": "telecom", "联通": "unicom", "移动": "mobile"}


def _private_names(manifest, analysis, envelope=None):
    """Include sidecar reviewers as well as the original author/reviewer names."""
    values = [manifest.get("author")]
    analyses = [analysis]
    if isinstance(envelope, dict):
        analyses.append(envelope.get("analysis"))
        for entry in envelope.get("review_log", []):
            if isinstance(entry, dict):
                values.append(entry.get("reviewer"))
    for candidate in analyses:
        if isinstance(candidate, dict) and isinstance(candidate.get("ai_review"), dict):
            values.extend(candidate["ai_review"].get(key) for key in ("agent", "reviewer"))
    return tuple(unicodedata.normalize("NFKC", value.strip()).casefold()
                 for value in values if isinstance(value, str) and value.strip())


def _fact(value, schema, names):
    value = value if isinstance(value, dict) else {}
    projected, withheld = _project(value.get("value", _MISSING), schema, names)
    status = value.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        status, withheld = None, True
    return {"status": status, "value": projected, "projection_status": (
        "partial" if _has_value(projected) else "redacted") if withheld else "unchanged"}


def _facts(analysis, names):
    facts = analysis.get("facts")
    facts = facts if isinstance(facts, dict) else {}
    return {field: _fact(facts.get(field), schema, names)
            for field, schema in sorted(FIELD_SCHEMAS.items())}


def _mapping(value, post_id, names):
    """An explicit single-object assignment, never guessed from the source post."""
    if not isinstance(value, dict) or value.get("confirmed") is not True:
        return None
    count = value.get("post_object_count")
    reviewed = value.get("reviewed_object_count")
    if (type(count) is not int or not 1 <= count <= 2**53 - 1
            or type(reviewed) is not int or reviewed != 1):
        return None
    item_id = value.get("item_id")
    if not isinstance(item_id, str) or len(item_id) > 40:
        return None
    match = re.fullmatch(re.escape(post_id) + r"-([1-9][0-9]*)", item_id, re.ASCII)
    if not match or int(match[1]) > count:
        return None
    kind, label = value.get("entry_kind"), value.get("public_label")
    if (not isinstance(kind, str) or kind not in _ENTRY_KINDS
            or not _safe_label(label, names)):
        return None
    return {"confirmed": True, "item_id": item_id, "post_object_count": count,
            "reviewed_object_count": 1, "entry_kind": kind, "public_label": label}


def _safe_unit(value, names):
    if isinstance(value, str) and value in _UNIT_WITH_SLASH:
        return value if _safe_label(value.replace("/", " "), names, maximum=32) else None
    return value if _safe_label(value, names, maximum=32) else None


def _observations(envelope, names):
    """Preserve declared kinds and axes, omitting evidence/prose/parameters."""
    result = []
    for item in envelope.get("observations", []):
        if not isinstance(item, dict):
            continue
        field = item.get("field_id")
        kind, status = item.get("kind"), item.get("status")
        if (not isinstance(field, str) or field not in FIELD_SCHEMAS
                or not isinstance(kind, str) or kind not in OBSERVATION_KINDS
                or not isinstance(status, str) or status not in STATUSES):
            continue
        observation = {"field_id": field, "kind": kind,
                       **_fact(item, FIELD_SCHEMAS[field], names),
                       "original_value": item.get("original_value") if _number(item.get("original_value")) else None,
                       "original_unit": _safe_unit(item.get("original_unit"), names)}
        benchmark = item.get("benchmark")
        if isinstance(benchmark, dict):
            observation["benchmark"] = {
                key: benchmark.get(key) if _safe_label(benchmark.get(key), names, maximum=limit) else None
                for key, limit in (("name", 64), ("version", 32))}
        network = item.get("network")
        if isinstance(network, dict):
            observation["network"] = {
                key: network.get(key) if isinstance(network.get(key), str)
                and network[key] in allowed and _safe_label(network[key], names) else None
                for key, allowed in _NETWORK_ENUMS.items()}
        result.append(observation)
    return result


def _benchmarks(observations, facts):
    """Only explicit, compatible benchmark axes can enable v5 version filters."""
    result = []
    for item in observations:
        field = item["field_id"]
        benchmark = item.get("benchmark", {})
        if (item["kind"] != "measurement" or item["status"] not in {"reported", "computed"}
                or not _number(item["value"]) or item["value"] < 0):
            continue
        version, name = benchmark.get("version"), benchmark.get("name")
        hardware = re.fullmatch(r"hardware_(total|cpu|gpu|memory|disk)_score", field)
        if hardware:
            if (isinstance(name, str) and name.casefold() == "hardwarequality"
                    and isinstance(version, str) and version.startswith("v") and _date(version[1:])
                    and facts[field]["value"] == item["value"]):
                result.append({"field_id": field, "tool": "HardwareQuality", "version": version,
                               "metric": hardware[1], "score": item["value"],
                               "kind": item["kind"], "status": item["status"]})
            continue
        if field not in {"geekbench_single_score", "geekbench_multi_score"}:
            continue
        match = re.fullmatch(r"([56])(?:\.[0-9]+){0,2}", version, re.ASCII) if isinstance(version, str) else None
        if not match:
            continue
        major = int(match[1])
        name = benchmark.get("name")
        if not isinstance(name, str) or name.casefold() not in {"geekbench", f"geekbench {major}"}:
            continue
        result.append({"field_id": field, "tool": "Geekbench", "version": major,
                       "metric": "single" if field == "geekbench_single_score" else "multi",
                       "score": item["value"], "kind": item["kind"], "status": item["status"]})
    return result


def _routes(observations):
    """Exact route labels on explicitly declared axes; never parse route prose."""
    result = []
    fields = {"routes_to_server": ("to_server", "outbound"),
              "routes_from_server": ("from_server", "return")}
    for item in observations:
        if (item["field_id"] not in fields or item["kind"] != "measurement"
                or item["status"] not in {"reported", "computed"}):
            continue
        expected, direction = fields[item["field_id"]]
        network = item.get("network", {})
        family, carrier = network.get("ip_family"), network.get("carrier")
        if family not in {"ipv4", "ipv6"} or carrier not in _CARRIERS or network.get("direction") != expected:
            continue
        value = item["value"]
        group = value.get(family) if isinstance(value, dict) else None
        operator = _CARRIERS[carrier]
        label = group.get(_CARRIER_KEYS[operator]) if isinstance(group, dict) else None
        if not isinstance(label, str):
            continue
        transport = network.get("transport")
        result.append({"field_id": item["field_id"], "family": "IPv4" if family == "ipv4" else "IPv6",
                       "direction": direction, "operator": operator,
                       "transport": transport.upper() if transport is not None else None,
                       "targetCity": None, "reportedLabels": [label],
                       "status": item["status"], "kind": item["kind"]})
    return result


def _time_observations(analysis, facts, names):
    """Publish only verified offset-aware report times, never their basis prose.

    The normalized accepted analysis retains the declared source timezone basis.
    The adapter may use these times when the public projection was partial solely
    because that prose was withheld. This flag is not a new review attestation.
    """
    original = analysis.get("facts", {}).get("test_time")
    projected = facts.get("test_time")
    if not isinstance(original, dict) or not isinstance(projected, dict):
        return []
    status, value = original.get("status"), original.get("value")
    if status not in {"reported", "computed"} or not isinstance(value, dict):
        return []
    basis, times = value.get("timezone_basis"), value.get("report_times")
    if (not isinstance(basis, str) or not basis.strip()
            or not isinstance(times, list) or not times or not all(_timestamp(time) for time in times)):
        return []
    safe_value = {key: child for key, child in value.items() if key != "timezone_basis"}
    expected = _fact({"status": status, "value": safe_value}, FIELD_SCHEMAS["test_time"], names)
    public_value = projected.get("value")
    if (expected["projection_status"] != "unchanged"
            or projected.get("status") != status
            or projected.get("projection_status") not in {"unchanged", "partial"}
            or not isinstance(public_value, dict)
            or public_value != expected["value"] or public_value.get("report_times") != times):
        return []
    return [{"field_id": "test_time", "status": status, "timezone_basis_declared": True,
             "report_times": list(times)}]


def _identity(post_id, source_url):
    if not isinstance(post_id, str) or not _POST.fullmatch(post_id):
        raise ValueError("Catalog source has an invalid post identity")
    if canonical_url(source_url) != f"https://www.nodeseek.com/post-{post_id}-1":
        raise ValueError("Catalog source identity does not match its post")


def _accepted(store, row):
    path = store._manifest(row)
    manifest = verify_archive(path)
    _identity(row["post_id"], row["source_url"])
    if manifest["post_id"] != row["post_id"] or manifest["source_url"] != row["source_url"]:
        raise ValueError("Accepted source identity does not match its bound archive")
    if (not ID.fullmatch(row["job_id"]) or type(row["version"]) is not int
            or not 1 <= row["version"] <= 2**53 - 1):
        raise ValueError("Invalid accepted record identity")
    envelope = json.loads(row["envelope"])
    if sha(encoded(envelope).encode("utf-8")) != row["digest"]:
        raise ValueError("Accepted envelope digest changed")
    # Older accepted envelopes may contain an unrecognized catalog mapping. Its
    # projection is checked independently below, never used to validate facts.
    validation_input = dict(envelope)
    validation_input.pop("catalog_mapping", None)
    verified = validate_submission(path, validation_input)
    analysis = json.loads(row["normalized"])
    if encoded(analysis) != encoded(verified["normalized"]):
        raise ValueError("Accepted normalization does not match its validated envelope")
    if verified["archive_sha256"] != row["archive_sha256"]:
        raise ValueError("Accepted archive identity changed")
    names = _private_names(manifest, analysis, envelope)
    observations = _observations(envelope, names)
    facts = _facts(analysis, names)
    result = {
        "post_id": row["post_id"], "source_url": row["source_url"],
        "record_id": f"accepted-{row['job_id']}-{row['version']}", "record_kind": "accepted",
        "analysis_version": row["version"], "archive_status": manifest["status"],
        "facts": facts, "safe_observations": observations,
        "benchmark_observations": _benchmarks(observations, facts), "network_observations": _routes(observations),
        "time_observations": _time_observations(analysis, facts, names),
        "new_review_performed": False, "review_attestation_verified": False,
        "manifest_sha256": row["archive_sha256"], "analysis_sha256": row["digest"],
    }
    mapping = _mapping(envelope.get("catalog_mapping"), row["post_id"], names)
    if mapping is not None:
        result["catalog_mapping"] = mapping
    return result


def _legacy(store, identity):
    record = store.get_legacy(identity)
    _identity(record["post_id"], record["source_url"])
    if any(not isinstance(record.get(key), str) or not _HASH.fullmatch(record[key])
           for key in ("id", "manifest_sha256", "analysis_sha256")):
        raise ValueError("Invalid legacy record identity")
    manifest, analysis = record["manifest"], record["analysis"]
    return {
        "post_id": record["post_id"], "source_url": record["source_url"],
        "record_id": record["id"], "record_kind": "legacy_imported", "analysis_version": None,
        "archive_status": manifest["status"], "facts": _facts(analysis, _private_names(manifest, analysis)),
        "safe_observations": [], "benchmark_observations": [], "network_observations": [], "time_observations": [],
        "new_review_performed": False, "review_attestation_verified": False,
        "manifest_sha256": record["manifest_sha256"], "analysis_sha256": record["analysis_sha256"],
    }


def catalog_records(store):
    """Return sanitized latest accepted snapshots and separately verified imports.

    Integrity failures raise without returning a partial feed. The current job
    state is deliberately irrelevant: accepted history remains available while a
    subsequent archive is pending, failed, cancelled, or being reviewed.
    """
    with store._db() as db:
        accepted = db.execute('''SELECT a.*,j.source_url,j.post_id
            FROM analyses a JOIN jobs j ON j.id=a.job_id
            WHERE a.version=(SELECT max(b.version) FROM analyses b WHERE b.job_id=a.job_id)
            ORDER BY j.post_id,a.job_id''').fetchall()
        legacy = db.execute('SELECT id FROM legacy_records ORDER BY post_id,imported_at,id').fetchall()
    records = [_accepted(store, row) for row in accepted]
    records.extend(_legacy(store, row["id"]) for row in legacy)
    # Fail closed at the API boundary even if future schema edits introduce a
    # non-finite value or a non-JSON object.
    encoded(records)
    return records
