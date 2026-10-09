"""Synthetic review declarations test validation, not AI/OCR capability.

All asserted reviews in this file are deliberately synthetic test fixtures.
No real image reading, model call, web collection, or production analysis occurs.
"""

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from vps_pipeline.analysis import (
    AnalysisError, create_work_package, validate_submission, _load_review,
)
from vps_pipeline.archive import archive_from_html, verify_archive


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZGkAAAAASUVORK5CYII="
)
TEXT = "Synthetic test only. Measured memory 1024 MiB. Plan memory 2 GB. 2 vCPU. Geekbench 6: 500. Latency TCP 0 ms, missing."
IMAGE_URL = "https://images.example.org/synthetic.png"


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "input"
        self.input.mkdir()
        (self.input / "capture.html").write_text(
            '<html><head><title>Synthetic fixture</title></head><body>'
            '<div id="0"><article class="post-content"><p>' + TEXT + '</p>'
            '<img src="' + IMAGE_URL + '"></article></div>'
            '<div id="1"><article class="post-content">REPLY NOT EVIDENCE</article></div>'
            '</body></html>', encoding="utf-8")
        (self.input / "synthetic.png").write_bytes(PNG)
        self.manifest_path = archive_from_html(
            self.input / "capture.html", "https://www.nodeseek.com/post-12345-1",
            self.root / "archive", {IMAGE_URL: "synthetic.png"})
        self.manifest = verify_archive(self.manifest_path)
        self.review = _load_review()
        self.records = {record["role"]: record for record in self.manifest["files"]}

    def tearDown(self):
        self.temp.cleanup()

    def envelope(self):
        analysis = self.review.draft(self.manifest)
        reviewed = [record["id"] for record in self.manifest["files"]]
        analysis["ai_review"] = {"completed": True, "agent": "SYNTHETIC TEST DECLARATION ONLY",
                                 "reviewed_files": reviewed}
        analysis["summary"] = "Synthetic fixture: validation test, not a real AI analysis."
        return {
            "schema_version": "vps-analysis-envelope/1",
            "archive_sha256": hashlib.sha256(self.manifest_path.read_bytes()).hexdigest(),
            "analysis": analysis, "observations": [],
            "review_log": [
                {"file_id": record["id"], "sha256": record["sha256"],
                 "reviewer": "SYNTHETIC TEST DECLARATION ONLY",
                 "reviewed_at": "2026-10-09T00:00:00+00:00", "coverage": "full",
                 "regions": ["Synthetic whole-file test declaration; no actual review"], "issues": []}
                for record in self.manifest["files"]
            ],
            "test_fixture": True,
        }

    def evidence(self, quote="1024 MiB", locator="synthetic memory line"):
        return {"file_id": self.records["first_post_text"]["id"], "locator": locator, "quote": quote}

    def fact(self, envelope, field="memory_gb", value=1.073741824, quote="1024 MiB"):
        evidence = [self.evidence(quote)]
        envelope["analysis"]["facts"][field] = {
            "value": value, "status": "reported", "evidence": evidence,
            "note": "Synthetic test; 1024 MiB is 1.073741824 decimal GB.",
        }
        observation = {
            "field_id": field, "kind": "measurement", "status": "reported", "value": value,
            "original_value": 1024, "original_unit": "MiB", "evidence": evidence,
            "note": "Synthetic measured value, independently preserved from advertised value.",
        }
        envelope["observations"].append(observation)
        return observation

    def test_package_draft_is_pending_and_contains_all_evidence_and_skill(self):
        output = self.root / "work.zip"
        result = create_work_package(self.manifest_path, output)
        self.assertEqual(result["status"], "needs_ai")
        with zipfile.ZipFile(output) as package:
            names = package.namelist()
            draft = json.loads(package.read("envelope.json"))
            self.assertIs(draft["analysis"]["ai_review"]["completed"], False)
            self.assertEqual(len(draft["analysis"]["facts"]), 61)
            self.assertTrue(all(fact["value"] is None for fact in draft["analysis"]["facts"].values()))
            self.assertEqual(draft["review_log"], [])
            self.assertEqual(draft["observations"], [])
            for record in self.manifest["files"]:
                data = package.read("assets/12345/" + record["path"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
                if record["role"].startswith("first_post_"):
                    self.assertNotIn(b"REPLY NOT EVIDENCE", data)
            self.assertEqual(package.read("assets/12345/manifest.json"), self.manifest_path.read_bytes())
            for name in ("skill/SKILL.md", "skill/references/fields.json", "skill/references/contract.md",
                         "skill/scripts/review.py", "sidecar-template.json", "package.json", "README.md"):
                self.assertIn(name, names)
            self.assertTrue(all("\\" not in name and not name.startswith("/") and ".." not in name.split("/")
                                for name in names))
            self.assertNotIn(str(self.root).encode(), package.read("package.json"))
            self.assertNotIn(str(self.root).encode(), package.read("envelope.json"))
        with self.assertRaises(ValueError):
            validate_submission(self.manifest_path, draft)

    def test_repeat_export_is_deterministic_and_different_output_is_protected(self):
        output = self.root / "work.zip"
        first = create_work_package(self.manifest_path, output)
        second = create_work_package(self.manifest_path, output)
        self.assertEqual(first["package_sha256"], second["package_sha256"])
        output.write_bytes(b"existing unrelated file")
        with self.assertRaisesRegex(AnalysisError, "different content"):
            create_work_package(self.manifest_path, output)
        self.assertEqual(output.read_bytes(), b"existing unrelated file")
        self.assertEqual(list(self.root.glob(".vps-work-*.zip")), [])

    def test_two_image_urls_with_identical_bytes_share_one_zip_entry(self):
        second_url = "https://images.example.org/synthetic-copy.png"
        capture = self.input / "capture.html"
        capture.write_text(capture.read_text(encoding="utf-8").replace(
            '<img src="' + IMAGE_URL + '">',
            '<img src="' + IMAGE_URL + '"><img src="' + second_url + '">'), encoding="utf-8")
        self.manifest_path = archive_from_html(
            capture, "https://www.nodeseek.com/post-12345-1", self.root / "duplicates",
            {IMAGE_URL: "synthetic.png", second_url: "synthetic.png"})
        self.manifest = verify_archive(self.manifest_path)
        images = [record for record in self.manifest["files"] if record["role"] == "image"]
        self.assertEqual(len(images), 2)
        self.assertNotEqual(images[0]["id"], images[1]["id"])
        self.assertEqual(images[0]["path"], images[1]["path"])
        output = self.root / "duplicate-images.zip"
        result = create_work_package(self.manifest_path, output)
        self.assertEqual(result["file_count"], len(self.manifest["files"]))
        with zipfile.ZipFile(output) as package:
            name = "assets/12345/" + images[0]["path"]
            self.assertEqual(package.namelist().count(name), 1)
            self.assertEqual(package.read(name), PNG)
            self.assertEqual(package.read("assets/12345/manifest.json"), self.manifest_path.read_bytes())
            summary = json.loads(package.read("package.json"))
            self.assertTrue({record["id"] for record in images} <= {record["id"] for record in summary["files"]})
        # Each source ID remains reviewable even though its bytes are shared.
        self.assertEqual(validate_submission(self.manifest_path, self.envelope())["status"], "validated")

    def test_export_cannot_overwrite_archive(self):
        with self.assertRaisesRegex(AnalysisError, "outside the post archive"):
            create_work_package(self.manifest_path, self.manifest_path.parent / "work.zip")
        verify_archive(self.manifest_path)

    def test_tampered_evidence_rejected_before_packaging_and_import(self):
        envelope = self.envelope()
        evidence_file = self.manifest_path.parent / self.records["first_post_text"]["path"]
        evidence_file.write_text("tampered", encoding="utf-8")
        for action in (lambda: create_work_package(self.manifest_path, self.root / "work.zip"),
                       lambda: validate_submission(self.manifest_path, envelope)):
            with self.assertRaises(ValueError):
                action()

    def test_bound_manifest_hash_rejects_even_reserialized_manifest(self):
        envelope = self.envelope()
        self.manifest_path.write_text(json.dumps(self.manifest, separators=(",", ":")), encoding="utf-8")
        with self.assertRaisesRegex(AnalysisError, "different archive"):
            validate_submission(self.manifest_path, envelope)

    def test_no_ai_claim_and_unknown_values_survive(self):
        result = validate_submission(self.manifest_path, self.envelope())
        self.assertEqual(result["status"], "validated")
        self.assertIs(result["validation"]["ai_invoked"], False)
        self.assertIs(result["validation"]["review_attestation_verified"], False)
        self.assertIn("declarations", result["validation"]["limitations"])
        self.assertIsNone(result["normalized"]["facts"]["smtp25_inbound"]["value"])

    def test_separate_plan_and_measured_units_preserved(self):
        envelope = self.envelope()
        self.fact(envelope)
        envelope["observations"].append({
            "field_id": "memory_gb", "kind": "plan", "status": "reported", "value": 2,
            "original_value": "2 GB", "original_unit": "GB", "evidence": [self.evidence("2 GB")],
            "note": "Synthetic plan specification, not measured memory.", "extra_detail": {"billing_scope": None},
        })
        original = copy.deepcopy(envelope)
        result = validate_submission(self.manifest_path, envelope)
        self.assertEqual(envelope, original)
        self.assertEqual(result["submitted_envelope"], original)
        self.assertEqual(result["observations"], original["observations"])
        self.assertEqual([item["kind"] for item in result["observations"]], ["measurement", "plan"])
        self.assertEqual(result["normalized"]["facts"]["memory_gb"]["value"], 1.073741824)

    def test_non_null_facts_need_observations_and_zero_is_a_real_fact(self):
        for value in (1, 0):
            with self.subTest(value=value):
                envelope = self.envelope()
                self.fact(envelope, value=value)
                envelope["observations"] = []
                with self.assertRaisesRegex(AnalysisError, "needs an evidence-bearing observation"):
                    validate_submission(self.manifest_path, envelope)

    def test_html_quote_cannot_bypass_fact_and_observation_checks(self):
        envelope = self.envelope()
        observation = self.fact(envelope, value=999999, quote="INVENTED QUOTE NEVER IN EVIDENCE")
        observation["evidence"][0]["file_id"] = self.records["first_post_html"]["id"]
        with self.assertRaisesRegex(AnalysisError, "HTML quote is absent"):
            validate_submission(self.manifest_path, envelope)

    def test_fact_html_quote_checked_independently_of_valid_observation(self):
        envelope = self.envelope()
        self.fact(envelope)
        envelope["analysis"]["facts"]["memory_gb"]["evidence"] = [{
            "file_id": self.records["first_post_html"]["id"],
            "locator": "synthetic memory line", "quote": "INVENTED FACT QUOTE"}]
        with self.assertRaisesRegex(AnalysisError, "HTML quote is absent"):
            validate_submission(self.manifest_path, envelope)

    def test_observation_html_quote_checked_independently_of_valid_fact(self):
        envelope = self.envelope()
        observation = self.fact(envelope)
        observation["evidence"] = [{
            "file_id": self.records["first_post_html"]["id"],
            "locator": "synthetic memory line", "quote": "INVENTED OBSERVATION QUOTE"}]
        with self.assertRaisesRegex(AnalysisError, "HTML quote is absent"):
            validate_submission(self.manifest_path, envelope)

    def test_html_quote_in_paired_archive_text_is_accepted(self):
        envelope = self.envelope()
        observation = self.fact(envelope)
        observation["evidence"][0]["file_id"] = self.records["first_post_html"]["id"]
        result = validate_submission(self.manifest_path, envelope)
        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["normalized"]["facts"]["memory_gb"]["value"], 1.073741824)

    def report_html_fixture(self):
        report_url = "https://nodequality.com/r/synthetic-html-report"
        page = self.input / "capture.html"
        page.write_text(page.read_text(encoding="utf-8").replace(
            "</article></div>", '<a href="' + report_url + '">Report</a></article></div>', 1),
            encoding="utf-8")
        (self.input / "report.html").write_text(
            '<html><body><p>' + TEXT.replace("1024 MiB", "1024&nbsp;<b>MiB</b>") + '</p>'
            '<script>INVISIBLE SCRIPT CLAIM</script></body></html>', encoding="utf-8")
        self.manifest_path = archive_from_html(
            page, "https://www.nodeseek.com/post-12345-1", self.root / "report-archive",
            {IMAGE_URL: "synthetic.png", report_url: "report.html"})
        self.manifest = verify_archive(self.manifest_path)
        self.records = {record["role"]: record for record in self.manifest["files"]}

    def test_report_html_cannot_support_invented_or_script_quotes(self):
        self.report_html_fixture()
        for quote in ["INVENTED HTML REPORT QUOTE", "INVISIBLE SCRIPT CLAIM"]:
            with self.subTest(quote=quote):
                envelope = self.envelope()
                observation = self.fact(envelope, quote=quote)
                observation["evidence"][0]["file_id"] = self.records["report_html"]["id"]
                with self.assertRaisesRegex(AnalysisError, "HTML quote is absent"):
                    validate_submission(self.manifest_path, envelope)

    def test_report_html_visible_quote_decodes_entities_and_markup(self):
        self.report_html_fixture()
        envelope = self.envelope()
        observation = self.fact(envelope)
        observation["evidence"][0]["file_id"] = self.records["report_html"]["id"]
        self.assertEqual(validate_submission(self.manifest_path, envelope)["status"], "validated")

    def test_observation_quote_must_exist_in_source_text(self):
        envelope = self.envelope()
        observation = self.fact(envelope)
        observation["evidence"] = [self.evidence("invented source claim")]
        with self.assertRaisesRegex(AnalysisError, "absent from source text"):
            validate_submission(self.manifest_path, envelope)

    def test_missing_image_log_hash_reviewer_or_region_rejected(self):
        image_id = self.records["image"]["id"]
        for mutation in ("missing", "sha256", "reviewer", "reviewed_at", "regions", "coverage"):
            with self.subTest(mutation=mutation):
                envelope = self.envelope()
                image_log = next(item for item in envelope["review_log"] if item["file_id"] == image_id)
                if mutation == "missing":
                    envelope["review_log"].remove(image_log)
                else:
                    image_log[mutation] = {"sha256": "0" * 64, "reviewer": "", "reviewed_at": "2026-10-09T00:00:00",
                                           "regions": [], "coverage": "top-only"}[mutation]
                with self.assertRaises(ValueError):
                    validate_submission(self.manifest_path, envelope)

    def test_partial_image_review_requires_issue_and_is_retained_as_warning(self):
        envelope = self.envelope()
        image_log = next(item for item in envelope["review_log"] if item["file_id"] == self.records["image"]["id"])
        image_log.update(coverage="partial", regions=["Synthetic visible top region only"])
        with self.assertRaisesRegex(AnalysisError, "Partial coverage"):
            validate_submission(self.manifest_path, envelope)
        image_log["issues"] = ["Synthetic bottom region unreadable; associated fields remain unknown."]
        result = validate_submission(self.manifest_path, envelope)
        self.assertTrue(any("Partial" in warning for warning in result["validation"]["warnings"]))

    def test_affiliate_link_is_rejected_without_user_authorization(self):
        envelope = self.envelope()
        envelope["analysis"]["affiliate_url"] = "https://example.org/?aff=someone"
        with self.assertRaisesRegex(AnalysisError, "AFF authorization"):
            validate_submission(self.manifest_path, envelope)

    def test_conflict_requires_two_distinct_evidence_references(self):
        envelope = self.envelope()
        fact = envelope["analysis"]["facts"]["memory_gb"]
        fact.update(status="conflict", value=None, note="Synthetic conflicting measurements.",
                    evidence=[self.evidence("1024 MiB")])
        with self.assertRaisesRegex(AnalysisError, "at least two distinct"):
            validate_submission(self.manifest_path, envelope)
        fact["evidence"].append(self.evidence("2 GB", "synthetic plan line"))
        result = validate_submission(self.manifest_path, envelope)
        self.assertIsNone(result["normalized"]["facts"]["memory_gb"]["value"])
        self.assertEqual(result["normalized"]["facts"]["memory_gb"]["status"], "conflict")

    def test_benchmark_version_must_be_explicit_and_is_preserved(self):
        envelope = self.envelope()
        observation = self.fact(envelope, "geekbench_single_score", 500, "Geekbench 6: 500")
        with self.assertRaisesRegex(AnalysisError, "Benchmark metadata"):
            validate_submission(self.manifest_path, envelope)
        observation["benchmark"] = {"name": "Geekbench", "version": "6", "parameters": {"synthetic": True}}
        self.assertEqual(validate_submission(self.manifest_path, envelope)["observations"][0]["benchmark"]["version"], "6")
        observation["benchmark"]["version"] = None
        self.assertIsNone(validate_submission(self.manifest_path, envelope)["observations"][0]["benchmark"]["version"])

    def test_network_protocol_and_true_zero_are_preserved(self):
        envelope = self.envelope()
        evidence = [self.evidence("Latency TCP 0 ms, missing")]
        envelope["analysis"]["facts"]["ipv4_latency"] = {
            "value": {"telecom": {"mean_ms": 99, "sample_count": 99, "method": "submitted"},
                      "unicom": None, "mobile": None}, "status": "computed", "evidence": evidence,
            "note": "Synthetic TCP result; null marks missing; real zero remains zero.",
        }
        envelope["analysis"]["latency_samples"] = {"ipv4": {"telecom": [0, None], "unicom": [], "mobile": []}}
        observation = {
            "field_id": "ipv4_latency", "kind": "measurement", "status": "computed", "value": 0,
            "original_value": [0, None], "original_unit": "ms", "evidence": evidence,
            "note": "Synthetic fixture only.",
            "network": {"ip_family": "ipv4", "direction": "to_server", "transport": "TCP", "carrier": "telecom",
                        "protocol_details": "Synthetic TCP large-packet test"},
        }
        envelope["observations"].append(observation)
        result = validate_submission(self.manifest_path, envelope)
        normalized = result["normalized"]["facts"]["ipv4_latency"]["value"]
        self.assertEqual(normalized["telecom"]["mean_ms"], 0)
        self.assertEqual(normalized["telecom"]["sample_count"], 1)
        self.assertIsNone(normalized["unicom"]["mean_ms"])
        self.assertEqual(result["submitted_envelope"]["analysis"]["facts"]["ipv4_latency"]["value"]["telecom"]["mean_ms"], 99)
        self.assertEqual(result["observations"][0]["network"]["transport"], "TCP")
        observation["network"]["ip_family"] = "ipv6"
        with self.assertRaisesRegex(AnalysisError, "IP family mismatch"):
            validate_submission(self.manifest_path, envelope)

    def test_nan_and_malformed_review_log_are_rejected(self):
        envelope = self.envelope()
        envelope["observations"].append({"value": float("nan")})
        with self.assertRaisesRegex(AnalysisError, "finite JSON"):
            validate_submission(self.manifest_path, envelope)
        envelope = self.envelope()
        envelope["review_log"][0]["coverage"] = []
        with self.assertRaises(AnalysisError):
            validate_submission(self.manifest_path, envelope)

    def test_package_rejects_local_metadata_paths_and_credentials(self):
        original = self.manifest_path.read_bytes()
        for extra in ({"local_source_path": "C:/Users/private/source.html"}, {"api_key": "not-a-real-key"}):
            with self.subTest(extra=extra):
                manifest = copy.deepcopy(self.manifest)
                manifest.update(extra)
                self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    create_work_package(self.manifest_path, self.root / "work.zip")
                self.manifest_path.write_bytes(original)

    def test_partial_archive_keeps_missing_resource_failure(self):
        self.manifest_path = archive_from_html(
            self.input / "capture.html", "https://www.nodeseek.com/post-12345-1", self.root / "partial")
        self.manifest = verify_archive(self.manifest_path)
        self.records = {record["role"]: record for record in self.manifest["files"]}
        result = validate_submission(self.manifest_path, self.envelope())
        self.assertEqual(result["validation"]["archive_status"], "partial")
        self.assertEqual(result["validation"]["download_failures"], self.manifest["failures"])
        self.assertTrue(any("Archive is partial" in item for item in result["validation"]["warnings"]))

    def test_traversal_manifest_entry_is_never_packaged(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["files"][0]["path"] = "../outside.txt"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            create_work_package(self.manifest_path, self.root / "work.zip")
        self.assertFalse((self.root / "work.zip").exists())

    def test_validation_has_no_file_side_effects(self):
        before = {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in self.root.rglob("*") if path.is_file()}
        validate_submission(self.manifest_path, self.envelope())
        after = {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_unknown_observation_cannot_support_known_fact(self):
        envelope = self.envelope()
        observation = self.fact(envelope)
        observation.update(status="unknown", value=None, note="Synthetic unsupported value.")
        with self.assertRaisesRegex(AnalysisError, "needs an evidence-bearing observation"):
            validate_submission(self.manifest_path, envelope)


if __name__ == "__main__":
    unittest.main()
