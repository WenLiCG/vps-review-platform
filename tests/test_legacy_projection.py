"""Synthetic privacy fixtures; these are not new historical review attestations."""

import copy
import json
from pathlib import Path
import unittest

from vps_pipeline.legacy_projection import (
    FIELD_SCHEMAS, MIGRATION_VERSION, PUBLIC_PROJECTION_VERSION, STATUSES,
    public_legacy_record,
)


CATALOG = (Path(__file__).resolve().parents[1] / "vps_pipeline" / "vendor" /
           "vps-review-analyze" / "references" / "fields.json")


class LegacyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "id": "c" * 64, "bundle_sha256": "c" * 64,
            "manifest_sha256": "a" * 64, "analysis_sha256": "b" * 64,
            "post_id": "12345", "source_url": "https://www.nodeseek.com/post-12345-1",
            "imported_at": "2026-10-09T01:00:00+00:00",
            "manifest": {"author": "PRIVATE-ORIGINAL-AUTHOR", "title": "PRIVATE TITLE",
                         "files": [{"path": "/private/source.txt"}]},
            "analysis": {
                "ai_review": {"completed": True, "agent": "PRIVATE-REVIEW-AGENT",
                              "reviewer": "PRIVATE-REVIEW-PERSON", "reviewed_files": ["private-image"]},
                "facts": {field: {"status": "unknown", "value": None,
                                  "evidence": [{"quote": "PRIVATE QUOTATION"}],
                                  "note": "PRIVATE NOTE"} for field in FIELD_SCHEMAS},
                "summary": "PRIVATE SUMMARY", "sources": [{"path": "/private/raw.html"}],
            },
            "provenance": {"schema_version": "vps-legacy-provenance/1",
                           "first_post_identity": "historical_browser_import_declaration",
                           "capture_method": "browser_import", "max_report_depth": 2,
                           "original_bytes_preserved": True,
                           "missing_new_envelope_fields": ["observations", "review_log"],
                           "resource_chains": [{"quote": "PRIVATE CHAIN"}],
                           "derived_files": [{"path": "/private/derived.txt"}]},
            "validation": {"validator_version": "vps-pipeline-legacy/1", "field_count": 61,
                           "original_validator_sha256": "d" * 64, "field_catalog_sha256": "e" * 64,
                           "archive_status": "partial", "evidence_file_count": 3, "evidence_bytes": 900,
                           "warnings": ["PRIVATE WARNING"], "new_review_performed": False},
        }

    def fact(self, field, value, status="reported"):
        self.record["analysis"]["facts"][field].update(value=value, status=status)

    def projected(self, field):
        return public_legacy_record(self.record)["facts"][field]

    def test_catalog_has_exactly_the_same_61_ids_and_types(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["fields"]
        self.assertEqual(len(catalog), 61)
        self.assertEqual(set(FIELD_SCHEMAS), {field["id"] for field in catalog})
        for field in catalog:
            schema = FIELD_SCHEMAS[field["id"]]
            inferred = "object" if isinstance(schema, dict) else "number" if schema == "number" else "string"
            self.assertEqual(inferred, field["value_type"], field["id"])

    def test_original_statuses_and_null_are_never_replaced(self):
        for status in STATUSES:
            self.fact("memory_gb", None, status)
            self.assertEqual(self.projected("memory_gb"), {
                "value": None, "status": status, "projection_status": "unchanged"})
        self.assertEqual(len(public_legacy_record(self.record)["facts"]), 61)

    def test_real_zero_and_negative_numbers_are_not_treated_as_missing(self):
        for value in (0, 0.0, -0.0, -1, 0.125, 1234):
            self.fact("memory_gb", value, "computed")
            fact = self.projected("memory_gb")
            self.assertEqual(fact["value"], value)
            self.assertEqual(fact["projection_status"], "unchanged")
            self.assertEqual(fact["status"], "computed")

    def test_numbers_reject_bools_nonfinite_and_oversized_integers(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"), 10 ** 5000, "0", []):
            self.fact("memory_gb", value)
            self.assertEqual(self.projected("memory_gb"), {
                "value": None, "status": "reported", "projection_status": "redacted"})
            json.dumps(public_legacy_record(self.record), allow_nan=False)

    def test_public_contract_and_historical_declaration(self):
        result = public_legacy_record(self.record)
        for key in ("id", "post_id", "source_url", "imported_at", "manifest_sha256", "analysis_sha256", "bundle_sha256"):
            self.assertEqual(result[key], self.record[key])
        self.assertEqual(result["status"], "legacy_imported")
        self.assertEqual(result["migration_schema_version"], MIGRATION_VERSION)
        self.assertEqual(result["public_projection_schema_version"], PUBLIC_PROJECTION_VERSION)
        self.assertIs(result["new_review_performed"], False)
        self.assertEqual(result["historical_review"], {"completed_declared": True, "independently_verified": False})
        for key in ("new_review_performed", "ai_invoked", "review_attestation_verified", "new_analysis_accepted"):
            self.assertIs(result["validation"][key], False)

    def test_rich_originals_and_arbitrary_metadata_never_escape(self):
        self.record["observations"] = [{"text": "PRIVATE OBSERVATION"}]
        self.record["review_log"] = [{"reviewed_at": "PRIVATE TIME"}]
        self.record["provenance"]["historical_ai_review"] = {"agent": "PRIVATE REVIEWER"}
        self.record["provenance"]["quote_checks"] = [{"locator": "PRIVATE LOCATOR", "image_file_ids": ["PRIVATE IMAGE"]}]
        self.record["validation"]["raw_html"] = "<script>PRIVATE</script>"
        result = public_legacy_record(self.record)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("/private", encoded)
        for key in ("manifest", "analysis", "observations", "review_log", "sources", "files", "evidence", "summary"):
            self.assertNotIn(key, result)
        for fact in result["facts"].values():
            self.assertEqual(set(fact), {"status", "value", "projection_status"})

    def test_safe_provenance_and_validation_remain_useful(self):
        result = public_legacy_record(self.record)
        self.assertEqual(result["provenance"]["first_post_identity"], "historical_browser_import_declaration")
        self.assertIs(result["provenance"]["original_bytes_preserved"], True)
        self.assertEqual(result["validation"]["field_count"], 61)
        self.assertEqual(result["validation"]["archive_status"], "partial")
        self.assertEqual(result["validation"]["evidence_file_count"], 3)
        self.assertEqual(result["validation"]["original_validator_sha256"], "d" * 64)
        self.assertNotIn("warnings", result["validation"])

    def test_private_author_and_review_names_are_redacted_inside_values(self):
        for name in ("PRIVATE-ORIGINAL-AUTHOR", "PRIVATE-REVIEW-AGENT", "PRIVATE-REVIEW-PERSON"):
            for field in ("provider", "city", "cpu_model"):
                self.fact(field, "Example " + name.lower())
                self.assertEqual(self.projected(field)["projection_status"], "redacted")
            self.fact("ip_organization", {"ipv4": name, "ipv6": None})
            self.assertEqual(self.projected("ip_organization")["value"], {"ipv4": None, "ipv6": None})

    def test_ip_literals_paths_credentials_markup_controls_and_quotes_are_redacted(self):
        unsafe = [
            "Example 203.0.113.1", "2001:db8::1", "::1", "::", "fe80::1%eth0",
            "::ffff:192.0.2.1", "1:2:3:4:5:6:7:8", "１２７.０.０.１",
            "/home/person/file", "See /tmp/private.txt", "C:\\Users\\person\\file.txt",
            "D:/private/file", "\\\\server\\share\\file", "See \\\\host\\share",
            "https://example.com", "https://user:password@example.com", "www.example.com",
            "API_KEY=private", "secret material", "Bearer abc", "person@example.com",
            "AKIAABCDEFGHIJKLMNOP", "sk-abcdefghijklmnop", "ghp_abcdefghijklmnop",
            "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl",
            "<script>alert(1)</script>", "<b>value</b>", "&lt;script&gt;",
            "private\x00string", "private\nstring", "private\x7fstring", "private\u202estring",
            '"private quotation"', "'private quotation'", "“private quotation”", "a" * 129,
        ]
        for value in unsafe:
            with self.subTest(value=value):
                self.fact("provider", value)
                self.assertEqual(self.projected("provider"), {
                    "status": "reported", "value": None, "projection_status": "redacted"})

    def test_public_company_and_hardware_labels_survive(self):
        for field, value in {
            "provider": "Example Hosting", "city": "Los Angeles", "datacenter": "LAX-01",
            "operating_system": "Debian GNU/Linux 12 (bookworm)", "cpu_model": "Intel Xeon Gold 6133 @ 2.50GHz",
        }.items():
            self.fact(field, value)
            self.assertEqual(self.projected(field)["value"], value)
        company = {"ipv4": "Alibaba (US) Technology Co., Ltd.", "ipv6": "Amazon.com, Inc."}
        self.fact("ip_organization", company)
        self.assertEqual(self.projected("ip_organization")["value"], company)

    def test_os_product_slash_exception_does_not_allow_paths(self):
        for value in ("Debian GNU/Linux /private/file", "GNU/Linux C:\\private", "/GNU/Linux", "GNU/Linux/secret"):
            self.fact("operating_system", value)
            self.assertEqual(self.projected("operating_system")["projection_status"], "redacted")

    def test_private_names_with_surrounding_whitespace_are_still_suppressed(self):
        self.record["manifest"]["author"] = "  Sensitive Name  "
        self.fact("provider", "Sensitive Name")
        self.assertEqual(self.projected("provider")["projection_status"], "redacted")

    def test_monthly_price_retains_amount_currency_and_zero(self):
        for amount in (0, 0.0, 0.99, None):
            self.fact("monthly_price", {"amount": amount, "currency": "USD", "note": "PRIVATE NOTE"})
            fact = self.projected("monthly_price")
            self.assertEqual(fact["value"], {"amount": amount, "currency": "USD"})
            self.assertEqual(fact["projection_status"], "partial")

    def test_test_time_preserves_only_valid_historical_timestamp_lists(self):
        self.fact("test_time", {
            "report_times": ["2026-10-08T23:11:18+08:00", "2026-10-08T23:11:18Z"],
            "half_hour_buckets": ["2026-10-08 23:00–23:30", "2026-10-08 23:30–2026-10-09 00:00"],
            "timezone_basis": "PRIVATE QUOTATION /private/path", "reviewed_at": "PRIVATE TIME",
        })
        result = self.projected("test_time")
        self.assertEqual(result["projection_status"], "partial")
        self.assertEqual(set(result["value"]), {"report_times", "half_hour_buckets"})
        self.assertEqual(len(result["value"]["report_times"]), 2)
        self.assertEqual(len(result["value"]["half_hour_buckets"]), 2)
        self.assertNotIn("reviewed_at", json.dumps(public_legacy_record(self.record)))

    def test_invalid_dates_and_timestamp_payloads_fail_closed(self):
        self.fact("test_date", "2026-02-30")
        self.assertEqual(self.projected("test_date")["projection_status"], "redacted")
        self.fact("test_time", {"report_times": ["2026-10-08T23:11:18", "2026-02-30T01:00:00Z", "2001:db8::1"],
                                "half_hour_buckets": ["2026-10-08 25:00–25:30"]})
        self.assertEqual(self.projected("test_time")["value"], {"report_times": [None, None, None], "half_hour_buckets": [None]})
        self.assertEqual(self.projected("test_time")["projection_status"], "redacted")

    def test_location_and_asn_axes_are_retained_without_addresses(self):
        values = {
            "country_region": {"continent": "亚洲", "country": "中国", "region": "香港"},
            "ip_usage_location": {"ipv4": {"country": "美国", "continent": "北美洲"}, "ipv6": None},
            "ip_registered_location": {"ipv4": "美国", "ipv6": "德国"},
            "asn": {"ipv4": "AS12345", "ipv6": "AS67890"},
        }
        for field, value in values.items():
            self.fact(field, value)
            self.assertEqual(self.projected(field)["value"], value)
            self.assertEqual(self.projected(field)["projection_status"], "unchanged")
        self.fact("ip_usage_location", {"ipv4": {"country": "US", "continent": "North America", "ip": "203.0.113.1"}, "ipv6": {"country": "2001:db8::1", "continent": None}})
        self.assertEqual(self.projected("ip_usage_location")["value"], {"ipv4": {"country": "US", "continent": "North America"}, "ipv6": {"country": None, "continent": None}})
        self.fact("asn", {"ipv4": "AS1 203.0.113.1", "ipv6": "AS2"})
        self.assertEqual(self.projected("asn")["value"], {"ipv4": None, "ipv6": "AS2"})

    def test_latency_preserves_measurements_but_drops_method_prose(self):
        self.fact("ipv4_latency", {
            "telecom": {"mean_ms": 0, "sample_count": 0, "method": "non_null_arithmetic_mean", "quote": "PRIVATE"},
            "unicom": {"mean_ms": None, "sample_count": 0, "method": "ICMP"},
            "mobile": {"mean_ms": 5.5, "sample_count": 3, "method": "TCP from 203.0.113.1"},
            "203.0.113.1": {"quote": "PRIVATE"},
        })
        value = self.projected("ipv4_latency")["value"]
        self.assertEqual(value["telecom"], {"mean_ms": 0, "sample_count": 0, "method": "non_null_arithmetic_mean"})
        self.assertEqual(value["unicom"], {"mean_ms": None, "sample_count": 0, "method": "ICMP"})
        self.assertEqual(value["mobile"], {"mean_ms": 5.5, "sample_count": 3, "method": None})
        self.assertEqual(set(value), {"telecom", "unicom", "mobile"})

    def test_classification_risk_counts_smtp_and_overcommit(self):
        samples = {
            "memory_overcommit": {"balloon": "detected", "ksm": "not_detected"},
            "ip_classifications": {"ipv4": {"usage_counts": {"hosting": 0, "business": 3}, "company_counts": {"residential": None}}, "ipv6": None},
            "risk_counts": {"ipv4": {"very_low": 0, "low": 3, "medium": 0, "high": None, "very_high": 0, "suspicious": 1}, "ipv6": None},
            "blacklist_count": {"ipv4": 0, "ipv6": None},
            "flagged_count": {"ipv4": 2, "ipv6": 0},
            "unlock_count": {"ipv4": 0, "ipv6": 3},
            "native_count": {"ipv4": 2, "ipv6": None},
            "ip_origin": {"ipv4": "native", "ipv6": "broadcast"},
            "smtp25_outbound": {"ipv4": "available", "ipv6": "blocked"},
            "smtp25_inbound": {"ipv4": None, "ipv6": "blocked"},
        }
        for field, value in samples.items():
            self.fact(field, value)
            self.assertEqual(self.projected(field)["value"], value, field)
            self.assertEqual(self.projected(field)["projection_status"], "unchanged", field)

    def test_unknown_and_malformed_nested_keys_never_escape(self):
        self.fact("ip_classifications", {"ipv4": {
            "usage_counts": {"hosting": 0, "PRIVATE-AUTHOR": 7, "/private/key": 5, "quote": "PRIVATE"},
            "company_counts": {"hosting": {"raw": "PRIVATE"}, "business": -1},
            "notes": "PRIVATE", "author": "PRIVATE",
        }, "ipv6": ["2001:db8::1"], "unknown_axis": "PRIVATE"})
        result = self.projected("ip_classifications")
        self.assertEqual(result["value"], {"ipv4": {"usage_counts": {"hosting": 0}, "company_counts": {"hosting": None, "business": None}}, "ipv6": None})
        self.assertEqual(result["projection_status"], "partial")
        self.assertNotIn("PRIVATE", json.dumps(public_legacy_record(self.record)))

    def test_route_summaries_with_narrative_are_withheld_without_reinterpreting(self):
        self.fact("routes_from_server", {"ipv4": {"telecom": "AS1 to 203.0.113.1", "unicom": "普通31省10099→4837", "mobile": "CMI"}, "ipv6": None})
        self.assertEqual(self.projected("routes_from_server")["value"], {"ipv4": {"telecom": None, "unicom": None, "mobile": "CMI"}, "ipv6": None})
        self.assertEqual(self.projected("routes_from_server")["projection_status"], "partial")

    def test_tampered_identifiers_and_metadata_do_not_escape(self):
        self.record.update(id="/private/hash", post_id="12345?secret=private", source_url="https://evil.example",
                           imported_at="203.0.113.1", manifest_sha256="<script>private</script>")
        self.record["validation"].update(archive_status="PRIVATE", evidence_bytes="/private/path", new_review_performed=True)
        self.record["provenance"].update(first_post_identity="PRIVATE", resource_chains=[{"address": "2001:db8::1"}])
        result = public_legacy_record(self.record)
        for key in ("id", "post_id", "source_url", "imported_at", "manifest_sha256"):
            self.assertIsNone(result[key])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertIs(result["validation"]["new_review_performed"], False)

    def test_canonical_url_cannot_smuggle_query_credentials_fragment_or_other_post(self):
        for url in ("https://user:pass@www.nodeseek.com/post-12345-1", "https://www.nodeseek.com/post-12345-1#0",
                    "https://www.nodeseek.com/post-12345-1?token=private", "https://www.nodeseek.com/post-99999-1"):
            self.record["source_url"] = url
            self.assertIsNone(public_legacy_record(self.record)["source_url"])

    def test_projection_is_pure_and_mutable_results_do_not_alias_originals(self):
        self.fact("monthly_price", {"amount": 0, "currency": "USD"})
        before = copy.deepcopy(self.record)
        result = public_legacy_record(self.record)
        self.assertEqual(self.record, before)
        result["facts"]["monthly_price"]["value"]["amount"] = 999
        result["provenance"]["missing_new_envelope_fields"].append("modified")
        self.assertEqual(self.record, before)
        self.assertEqual(public_legacy_record(self.record), public_legacy_record(self.record))

    def test_unknown_facts_invalid_statuses_and_wrong_container_types_fail_closed(self):
        self.record["analysis"]["facts"]["PRIVATE-NEW-FIELD"] = {"value": "PRIVATE", "status": "reported"}
        self.fact("memory_gb", {"raw": "PRIVATE"}, "PRIVATE-STATUS")
        result = public_legacy_record(self.record)
        self.assertEqual(len(result["facts"]), 61)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(result["facts"]["memory_gb"], {"status": None, "value": None, "projection_status": "redacted"})
        for record in (None, [], {}, {"analysis": []}, {"analysis": {"facts": []}}):
            result = public_legacy_record(record)
            self.assertEqual(len(result["facts"]), 61)
            json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
