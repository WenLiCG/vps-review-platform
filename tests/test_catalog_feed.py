"""Offline synthetic feed tests. No real VPS facts or AI reviews are asserted."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from legacy_helpers import synthetic_legacy
from vps_pipeline.analysis import _load_review
from vps_pipeline.catalog_feed import catalog_records, _fact, _mapping, _observations, _time_observations
from vps_pipeline.legacy_projection import FIELD_SCHEMAS, STATUSES
from vps_pipeline.store import Store, encoded, sha


URL = "https://www.nodeseek.com/post-913633-1"
TEXT = ("SYNTHETIC TEST ONLY. No real review. 2 vCPU. Measured memory 1024 MiB. "
        "Geekbench 6.3.0 single 500 multi 1000. HardwareQuality v2026-01-01 100. "
        "Routes CN2GIA CMI. TCP latency 0 ms. PRIVATE QUOTATION.")
PAGE = ('<div id="0"><article class="post-content"><p>' + TEXT + '</p></article></div>')


class CatalogFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.html = self.base / "capture.html"
        self.html.write_text(PAGE, encoding="utf-8")
        self.store = Store(self.base / "private")
        self.job = self.store.enqueue(URL)
        self.store.import_html(self.job["id"], self.html)

    def tearDown(self):
        self.temp.cleanup()

    def envelope(self):
        with self.store._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (self.job["id"],)).fetchone()
        path = self.store._manifest(row)
        manifest = json.loads(path.read_text())
        analysis = _load_review().draft(manifest)
        analysis["ai_review"] = {"completed": True, "agent": "PRIVATE AGENT",
                                 "reviewer": "PRIVATE REVIEWER",
                                 "reviewed_files": [f["id"] for f in manifest["files"]]}
        analysis["summary"] = "PRIVATE SUMMARY. Synthetic protocol test only, not actual review."
        return {"schema_version": "vps-analysis-envelope/1", "archive_sha256": sha(path.read_bytes()),
                "analysis": analysis, "observations": [], "test_fixture": True,
                "review_log": [{"file_id": f["id"], "sha256": f["sha256"], "reviewer": "PRIVATE SIDECAR PERSON",
                                "reviewed_at": "2026-10-09T00:00:00+00:00", "coverage": "full",
                                "regions": ["PRIVATE SYNTHETIC REGION"], "issues": []}
                               for f in manifest["files"]]}

    def observation(self, envelope, field, value, *, kind="measurement", status="reported", original_value=None,
                    original_unit=None, benchmark=None, network=None, set_fact=True):
        with self.store._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (self.job["id"],)).fetchone()
        manifest = json.loads(self.store._manifest(row).read_text())
        file_id = next(f["id"] for f in manifest["files"] if f["role"] == "first_post_text")
        evidence = [{"file_id": file_id, "locator": "PRIVATE LOCATOR", "quote": "PRIVATE QUOTATION"}]
        if set_fact:
            envelope["analysis"]["facts"][field] = {"value": value, "status": status,
                                                      "evidence": evidence, "note": "PRIVATE NOTE"}
        item = {"field_id": field, "value": value, "status": status, "kind": kind,
                "original_value": original_value, "original_unit": original_unit,
                "evidence": evidence, "note": "PRIVATE OBSERVATION NOTE"}
        if benchmark is not None:
            item["benchmark"] = benchmark
        if network is not None:
            item["network"] = network
        envelope["observations"].append(item)
        return item

    def accepted(self, envelope=None):
        self.store.submit(self.job["id"], envelope if envelope is not None else self.envelope())
        return catalog_records(self.store)[0]

    def mapping(self, **changes):
        return {"confirmed": True, "item_id": "913633-1", "post_object_count": 1,
                "reviewed_object_count": 1, "entry_kind": "measured_vps",
                "public_label": "Synthetic public configuration", **changes}

    def test_pending_job_is_not_a_fabricated_review(self):
        self.assertEqual(catalog_records(self.store), [])
        self.assertEqual(self.store.get_job(self.job["id"])["status"], "awaiting_analysis")

    def test_accepted_mapping_and_true_zero_are_preserved(self):
        envelope = self.envelope()
        envelope["catalog_mapping"] = self.mapping()
        self.observation(envelope, "vcpu", 0, original_value=0, original_unit="vCPU")
        result = self.accepted(envelope)
        self.assertEqual(result["catalog_mapping"], self.mapping())
        self.assertEqual(result["record_kind"], "accepted")
        self.assertEqual(result["analysis_version"], 1)
        self.assertEqual(result["archive_status"], "ready")
        self.assertEqual(result["manifest_sha256"], envelope["archive_sha256"])
        self.assertEqual(result["analysis_sha256"], sha(encoded(envelope).encode()))
        self.assertEqual(result["facts"]["vcpu"], {"status": "reported", "value": 0, "projection_status": "unchanged"})
        self.assertEqual(result["safe_observations"][0]["original_value"], 0)
        json.dumps(result, allow_nan=False)

    def test_unknown_fields_remain_unknown_without_mapping_or_axes(self):
        result = self.accepted()
        self.assertNotIn("catalog_mapping", result)
        self.assertEqual(set(result["facts"]), set(FIELD_SCHEMAS))
        self.assertEqual(len(result["facts"]), 61)
        self.assertTrue(all(f == {"status": "unknown", "value": None, "projection_status": "unchanged"}
                            for f in result["facts"].values()))
        for key in ("safe_observations", "benchmark_observations", "network_observations", "time_observations"):
            self.assertEqual(result[key], [])
        self.assertIs(result["new_review_performed"], False)
        self.assertIs(result["review_attestation_verified"], False)

    def test_new_pending_archive_does_not_hide_latest_accepted_snapshot(self):
        old = self.envelope()
        self.accepted(old)
        old["analysis"]["summary"] += " PRIVATE SECOND VERSION"
        previous = self.accepted(old)
        self.html.write_text(PAGE.replace("2 vCPU", "4 vCPU"), encoding="utf-8")
        self.store.import_html(self.job["id"], self.html)
        self.assertEqual(self.store.get_job(self.job["id"])["status"], "awaiting_analysis")
        self.assertEqual(catalog_records(self.store), [previous])
        self.assertEqual(previous["analysis_version"], 2)
        self.assertNotEqual(previous["manifest_sha256"], self.store.get_job(self.job["id"])["archive_sha256"])

    def test_legacy_and_accepted_same_post_remain_separate_without_new_attestations(self):
        self.accepted()
        manifest, analysis = synthetic_legacy(self.base / "legacy", post_id="913633")
        original = analysis.read_bytes()
        imported = self.store.import_legacy(manifest, analysis)
        result = catalog_records(self.store)
        self.assertEqual([r["record_kind"] for r in result], ["accepted", "legacy_imported"])
        legacy = result[1]
        self.assertEqual(legacy["record_id"], imported["id"])
        self.assertIsNone(legacy["analysis_version"])
        self.assertEqual(legacy["analysis_sha256"], sha(original))
        self.assertNotIn("catalog_mapping", legacy)
        self.assertEqual(legacy["safe_observations"], [])
        self.assertEqual(legacy["benchmark_observations"], [])
        self.assertEqual(legacy["network_observations"], [])
        self.assertEqual(legacy["time_observations"], [])
        self.assertFalse(legacy["new_review_performed"])
        self.assertFalse(legacy["review_attestation_verified"])
        self.assertEqual(analysis.read_bytes(), original)
        with self.store._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM analyses").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM legacy_records").fetchone()[0], 1)

    def test_no_private_names_prose_resources_paths_or_unrequested_keys(self):
        envelope = self.envelope()
        self.observation(envelope, "provider", "PRIVATE SIDECAR PERSON")
        self.observation(envelope, "geekbench_single_score", 500,
                         benchmark={"name": "PRIVATE AGENT", "version": "https://private.example/key",
                                    "parameters": {"token": "PRIVATE TOKEN"}})
        envelope["catalog_mapping"] = self.mapping(public_label="PRIVATE REVIEWER")
        envelope["private_path"] = str(self.base)
        envelope["raw_image"] = "https://private.example/image.png"
        # Historical optional mapping must be omitted even if the current
        # submit validator now rejects it. Simulate that pre-upgrade ledger row.
        envelope.pop("catalog_mapping")
        self.store.submit(self.job["id"], envelope)
        envelope["catalog_mapping"] = self.mapping(public_label="PRIVATE REVIEWER")
        with self.store._db() as db:
            db.execute("UPDATE analyses SET envelope=?,digest=?", (encoded(envelope), sha(encoded(envelope).encode())))
        result = catalog_records(self.store)[0]
        payload = json.dumps(result)
        self.assertNotIn("PRIVATE", payload)
        self.assertNotIn(str(self.base), payload)
        self.assertNotIn("private.example", payload)
        self.assertNotIn("catalog_mapping", result)
        self.assertEqual(result["facts"]["provider"]["projection_status"], "redacted")
        for key in ("manifest", "analysis", "review_log", "evidence", "summary", "sources", "files"):
            self.assertNotIn(key, result)
        self.assertEqual(result["benchmark_observations"], [])
        self.assertEqual(result["safe_observations"][1]["benchmark"], {"name": None, "version": None})

    def test_benchmark_version_is_explicit_and_plan_kind_never_coerced(self):
        envelope = self.envelope()
        self.observation(envelope, "geekbench_single_score", 500, original_value=500, original_unit="score",
                         benchmark={"name": "Geekbench", "version": "6.3.0"})
        self.observation(envelope, "geekbench_multi_score", 1000,
                         benchmark={"name": "Geekbench", "version": None})
        self.observation(envelope, "geekbench_single_score", 900, kind="plan", set_fact=False,
                         benchmark={"name": "Geekbench", "version": "5"})
        result = self.accepted(envelope)
        self.assertEqual(result["benchmark_observations"], [
            {"field_id": "geekbench_single_score", "tool": "Geekbench", "version": 6,
             "metric": "single", "score": 500, "kind": "measurement", "status": "reported"}])
        self.assertEqual(result["safe_observations"][2]["kind"], "plan")
        self.assertIsNone(result["safe_observations"][1]["benchmark"]["version"])

    def test_geekbench_version_is_not_inferred_from_name_or_score(self):
        for name, version in (("Geekbench 6", None), (None, "6"), ("Geekbench 5", "6"),
                              ("Geekbench", "future"), ("Geekbench", "7"), ("Geekbench", "v6")):
            with self.subTest(name=name, version=version):
                envelope = self.envelope()
                self.observation(envelope, "geekbench_single_score", 6000,
                                 benchmark={"name": name, "version": version})
                self.assertEqual(self.accepted(envelope)["benchmark_observations"], [])

    def test_hardware_quality_uses_only_explicit_dated_version_and_matching_score(self):
        envelope = self.envelope()
        self.observation(envelope, "hardware_total_score", 100,
                         benchmark={"name": "HardwareQuality", "version": "v2026-01-01"})
        self.observation(envelope, "hardware_cpu_score", 50,
                         benchmark={"name": "HardwareQuality", "version": None})
        self.observation(envelope, "hardware_total_score", 99, set_fact=False,
                         benchmark={"name": "HardwareQuality", "version": "v2026-02-02"})
        result = self.accepted(envelope)
        self.assertEqual(result["benchmark_observations"], [
            {"field_id": "hardware_total_score", "tool": "HardwareQuality", "version": "v2026-01-01",
             "metric": "total", "score": 100, "kind": "measurement", "status": "reported"}])

    def test_explicit_network_axes_stay_protocol_specific(self):
        envelope = self.envelope()
        routes = {"ipv4": {"telecom": "CN2GIA", "unicom": None, "mobile": "CMI"}, "ipv6": None}
        network = {"ip_family": "ipv4", "direction": "from_server", "transport": "TCP", "carrier": "telecom"}
        self.observation(envelope, "routes_from_server", routes, network=network)
        latency = {"telecom": {"mean_ms": 0, "sample_count": 1, "method": "TCP"}, "unicom": None, "mobile": None}
        self.observation(envelope, "ipv4_latency", latency,
                         network={**network, "direction": "to_server"}, original_value=0, original_unit="ms")
        result = self.accepted(envelope)
        self.assertEqual(result["network_observations"], [
            {"field_id": "routes_from_server", "family": "IPv4", "direction": "return", "operator": "电信",
             "transport": "TCP", "targetCity": None, "reportedLabels": ["CN2GIA"],
             "status": "reported", "kind": "measurement"}])
        self.assertEqual(result["safe_observations"][1]["network"]["transport"], "TCP")
        self.assertEqual(result["facts"]["ipv4_latency"]["value"]["telecom"]["mean_ms"], 0)
        self.assertNotIn("ICMP", json.dumps(result))

    def test_unknown_route_axes_and_prose_do_not_become_filter_labels(self):
        envelope = self.envelope()
        routes = {"ipv4": {"telecom": "CN2GIA via 203.0.113.1", "unicom": "CN2", "mobile": "CMI"}, "ipv6": None}
        self.observation(envelope, "routes_to_server", routes,
                         network={"ip_family": "ipv4", "direction": "to_server", "transport": None, "carrier": "telecom"})
        self.observation(envelope, "routes_to_server", routes, set_fact=False,
                         network={"ip_family": None, "direction": "to_server", "transport": None, "carrier": "unicom"})
        self.observation(envelope, "routes_to_server", routes, set_fact=False,
                         network={"ip_family": "ipv4", "direction": "to_server", "transport": "203.0.113.1", "carrier": None})
        result = self.accepted(envelope)
        self.assertEqual(result["network_observations"], [])
        self.assertNotIn("203.0.113.1", json.dumps(result))
        self.assertIsNone(result["safe_observations"][2]["network"]["transport"])

    def test_unknown_transport_remains_unknown_on_known_route_axes(self):
        envelope = self.envelope()
        self.observation(envelope, "routes_to_server", {
            "ipv4": {"telecom": "CN2GIA", "unicom": None, "mobile": None}, "ipv6": None},
            network={"ip_family": "ipv4", "direction": "to_server", "transport": None, "carrier": "telecom"})
        route = self.accepted(envelope)["network_observations"][0]
        self.assertEqual(route["direction"], "outbound")
        self.assertIsNone(route["transport"])

    def test_raw_capacity_units_remain_explicit_and_no_conversion_is_invented(self):
        envelope = self.envelope()
        self.observation(envelope, "memory_gb", 1.073741824, original_value=1024, original_unit="MiB")
        self.observation(envelope, "memory_gb", 2, original_value="2 GB", original_unit="GB", kind="plan", set_fact=False)
        result = self.accepted(envelope)
        self.assertEqual(result["safe_observations"][0]["original_value"], 1024)
        self.assertEqual(result["safe_observations"][0]["original_unit"], "MiB")
        self.assertIsNone(result["safe_observations"][1]["original_value"])
        self.assertEqual(result["facts"]["memory_gb"]["value"], 1.073741824)

    def test_safe_unit_allowlist_keeps_speeds_without_allowing_paths(self):
        envelope = {"observations": [{"field_id": "memory_read_mbps", "kind": "measurement", "status": "reported",
                                      "value": 0, "original_value": 0, "original_unit": "MiB/s"}]}
        self.assertEqual(_observations(envelope, ())[0]["original_unit"], "MiB/s")
        for unsafe in ("/private/path", "C:/Users/test", "https://example.com", "private token", "203.0.113.1"):
            envelope["observations"][0]["original_unit"] = unsafe
            self.assertIsNone(_observations(envelope, ())[0]["original_unit"])

    def test_mapping_rejects_ambiguous_malformed_and_private_labels(self):
        for changes in ({"confirmed": False}, {"confirmed": 1}, {"post_object_count": True}, {"post_object_count": 0},
                        {"post_object_count": float("inf")}, {"reviewed_object_count": True}, {"reviewed_object_count": 2},
                        {"item_id": "999-1"}, {"item_id": "913633-2"}, {"item_id": "913633-01"},
                        {"entry_kind": "measured"}, {"public_label": "PRIVATE NAME"}, {"public_label": "203.0.113.1"},
                        {"public_label": "<b>Label</b>"}, {"public_label": "/tmp/source"},
                        {"public_label": "https://example.com"}, {"public_label": "api_key abc"}):
            with self.subTest(changes=changes):
                self.assertIsNone(_mapping(self.mapping(**changes), "913633", ("private name",)))
        self.assertEqual(_mapping(self.mapping(entry_kind="advertised_plan"), "913633", ())["entry_kind"], "advertised_plan")

    def test_all_six_statuses_and_nonfinite_redaction_match_original_projection(self):
        for status in STATUSES:
            self.assertEqual(_fact({"value": None, "status": status}, "number", ()),
                             {"value": None, "status": status, "projection_status": "unchanged"})
        for unsafe in (True, float("inf"), float("nan"), 10**100):
            fact = _fact({"value": unsafe, "status": "reported"}, "number", ())
            self.assertIsNone(fact["value"])
            json.dumps(fact, allow_nan=False)

    def test_tampered_manifest_and_evidence_block_entire_feed(self):
        self.accepted()
        with self.store._db() as db:
            row = db.execute("SELECT * FROM analyses").fetchone()
        path = self.store._manifest(row)
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "manifest hash changed"):
            catalog_records(self.store)
        path.write_bytes(original)
        manifest = json.loads(original)
        evidence = path.parent / next(f["path"] for f in manifest["files"] if f["role"] == "first_post_text")
        evidence.write_text("TAMPERED", encoding="utf-8")
        with self.assertRaises(ValueError):
            catalog_records(self.store)

    def test_legacy_tampering_is_reverified(self):
        manifest, analysis = synthetic_legacy(self.base / "legacy")
        imported = self.store.import_legacy(manifest, analysis)
        with self.store._db() as db:
            row = db.execute("SELECT archive_rel FROM legacy_records WHERE id=?", (imported["id"],)).fetchone()
        archived = self.store.root / row["archive_rel"]
        (archived.parent / "analysis.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            catalog_records(self.store)

    def test_stored_envelope_and_normalization_tampering_fail_closed(self):
        envelope = self.envelope()
        self.accepted(envelope)
        with self.store._db() as db:
            envelope["analysis"]["summary"] = "CHANGED"
            db.execute("UPDATE analyses SET envelope=?", (encoded(envelope),))
        with self.assertRaisesRegex(ValueError, "envelope digest changed"):
            catalog_records(self.store)
        with self.store._db() as db:
            db.execute("UPDATE analyses SET digest=?,normalized=?", (sha(encoded(envelope).encode()), "{}"))
        with self.assertRaisesRegex(ValueError, "normalization does not match"):
            catalog_records(self.store)

    def test_known_aware_report_times_are_retained_without_private_basis(self):
        envelope = self.envelope()
        self.observation(envelope, "test_time", {
            "report_times": ["2026-10-08T16:00:00Z", "2026-10-09T00:30:00+08:00"],
            "timezone_basis": "PRIVATE TIMEZONE BASIS from explicit report offsets, not capture time"}, kind="context")
        result = self.accepted(envelope)
        times = ["2026-10-09T00:00:00+08:00", "2026-10-09T00:30:00+08:00"]
        self.assertEqual(result["time_observations"], [{"field_id": "test_time", "status": "reported",
                         "timezone_basis_declared": True, "report_times": times}])
        self.assertEqual(result["facts"]["test_time"]["value"]["report_times"], times)
        self.assertEqual(result["facts"]["test_time"]["projection_status"], "partial")
        self.assertEqual(result["facts"]["test_date"]["value"], "2026-10-09")
        self.assertNotIn("PRIVATE TIMEZONE BASIS", json.dumps(result))
        self.assertNotIn("capture time", json.dumps(result))

    def test_computed_report_times_keep_status_without_inferred_or_unknown_times(self):
        self.assertEqual(self.accepted()["time_observations"], [])
        for status in ("computed", "inferred"):
            envelope = self.envelope()
            self.observation(envelope, "test_time", {
                "report_times": ["2026-10-09T00:00:00+08:00"], "timezone_basis": "PRIVATE OFFSET DECLARATION"},
                status=status, kind="context")
            result = self.accepted(envelope)
            self.assertEqual(result["facts"]["test_time"]["status"], status)
            if status == "computed":
                self.assertEqual(result["time_observations"][0]["status"], "computed")
            else:
                self.assertEqual(result["time_observations"], [])

    def test_time_metadata_requires_basis_aware_times_and_exact_projection(self):
        value = {"report_times": ["2026-10-09T00:00:00+08:00"],
                 "half_hour_buckets": ["2026-10-09 00:00–00:30"], "timezone_basis": "PRIVATE BASIS"}
        original = {"status": "reported", "value": value}
        analysis = {"facts": {"test_time": original}}
        facts = {"test_time": _fact(original, FIELD_SCHEMAS["test_time"], ())}
        self.assertEqual(len(_time_observations(analysis, facts, ())), 1)
        for changes in ({"timezone_basis": None}, {"timezone_basis": ""}, {"timezone_basis": " "},
                        {"report_times": ["2026-10-09T00:00:00"]},
                        {"report_times": ["2026-10-09 00:00:00 CST"]},
                        {"report_times": ["2026-02-30T00:00:00Z"]}, {"report_times": []},
                        {"report_times": ["2026-10-09T01:00:00+08:00"]},
                        {"private_extra": "PRIVATE TIME NOTE"}):
            with self.subTest(changes=changes):
                altered = {"facts": {"test_time": {"status": "reported", "value": {**value, **changes}}}}
                self.assertEqual(_time_observations(altered, facts, ()), [])
        mismatch = copy.deepcopy(facts)
        mismatch["test_time"]["status"] = "computed"
        self.assertEqual(_time_observations(analysis, mismatch, ()), [])
        del value["timezone_basis"]
        self.assertEqual(_time_observations(analysis, facts, ()), [])

    def test_unqualified_time_basis_does_not_bypass_submission_validation(self):
        for value in ({"report_times": ["2026-10-09T00:00:00+08:00"]},
                      {"report_times": ["2026-10-09T00:00:00"], "timezone_basis": "PRIVATE AMBIGUOUS CST"}):
            with self.subTest(value=value):
                envelope = self.envelope()
                self.observation(envelope, "test_time", value, kind="context")
                with self.assertRaises(ValueError):
                    self.store.submit(self.job["id"], envelope)
                self.assertEqual(catalog_records(self.store), [])


    def test_feed_does_not_mutate_ledger_files_or_invoke_network(self):
        self.accepted()
        with self.store._db() as db:
            before = {name: [tuple(r) for r in db.execute("SELECT * FROM " + name)]
                      for name in ("jobs", "events", "analyses", "legacy_records")}
        files = {str(path): path.read_bytes() for path in (self.store.root / "archives").rglob("*") if path.is_file()}
        with patch("vps_pipeline.network.fetch_first_post", side_effect=AssertionError("network forbidden")):
            first = catalog_records(self.store)
            self.assertEqual(first, catalog_records(self.store))
        with self.store._db() as db:
            after = {name: [tuple(r) for r in db.execute("SELECT * FROM " + name)] for name in before}
        self.assertEqual(before, after)
        self.assertEqual(files, {str(path): path.read_bytes() for path in (self.store.root / "archives").rglob("*") if path.is_file()})
        first[0]["facts"]["memory_gb"]["value"] = 999
        self.assertIsNone(catalog_records(self.store)[0]["facts"]["memory_gb"]["value"])


if __name__ == "__main__":
    unittest.main()
