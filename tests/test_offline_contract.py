"""Offline contract checks against synthetic fixtures. No network and no vps-analysis rewrite."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from vps_pipeline.offline_contract import (
    INFERRED_TIME_CASES, affiliate_from_source, affiliate_url, apply_explicit_times,
    benchmark_buckets, derive_route_tags, derive_samples, normalize_price,
    resolve_tested_at, retain_unit, suggest_filenames, vps_analysis_adaptation,
)


ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "offline-spec"
CASES = ROOT / "fixtures" / "cases"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dig(document, path):
    if not path.startswith("$"):
        raise AssertionError(path)
    current = document
    for part in path.split(".")[1:]:
        current = current[int(part)] if part.isdigit() else current[part]
    return current


class OfflineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        for directory in sorted(path for path in CASES.iterdir() if path.is_dir()):
            cls.cases[directory.name] = {
                "expected": load(directory / "expected.normalized.json"),
                "asserts": load(directory / "acceptance.asserts.json"),
                "raw": (directory / "raw.excerpt.txt").read_text(encoding="utf-8"),
            }

    def test_fixture_asserts_match_their_expected_documents(self):
        self.assertEqual(len(self.cases), 13)
        for case_id, case in self.cases.items():
            for check in case["asserts"]:
                value = dig(case["expected"], check["path"])
                if "equals" in check:
                    self.assertEqual(value, check["equals"], f"{case_id} {check['name']}")
                if "contains" in check:
                    self.assertIn(check["contains"], value, f"{case_id} {check['name']}")
                if "length" in check:
                    self.assertEqual(len(value), check["length"], f"{case_id} {check['name']}")

    def test_filenames_match_expected_when_time_rule_agrees(self):
        documents = [case["expected"] for case in self.cases.values()]
        names = suggest_filenames(documents)
        for case_id, case in self.cases.items():
            expected = case["expected"]["export"]["suggested_filename"]
            post_id = case["expected"]["source"]["source_post_id"]
            if case_id in INFERRED_TIME_CASES:
                self.assertNotEqual(names[post_id], expected, case_id)
                self.assertIn("unknownDate", names[post_id])
                self.assertTrue(names[post_id].endswith("__" + post_id))
            else:
                self.assertEqual(names[post_id], expected, case_id)

    def test_explicit_zone_converts_and_bare_date_does_not(self):
        first = resolve_tested_at("2025-06-03 21:00 (北京时间)", published_at="2025-06-04T10:00:00+08:00")
        self.assertEqual(first["tz_confidence"], "explicit")
        self.assertEqual(first["tested_at_beijing"], "2025-06-03T21:00:00+08:00")
        utc = resolve_tested_at("2025-06-03T17:30:00Z", published_at="2025-06-04T09:00:00+08:00")
        self.assertEqual(utc["tested_at_beijing"], "2025-06-04T01:30:00+08:00")
        self.assertEqual(utc["tz_confidence"], "explicit")
        missing = resolve_tested_at(None, published_at="2025-09-01T00:00:00+08:00")
        self.assertIsNone(missing["tested_at_beijing"])
        self.assertEqual(missing["tz_confidence"], "unknown")
        bare = resolve_tested_at("2025-06-03", published_at="2025-06-03T00:00:00+08:00")
        self.assertIsNone(bare["tested_at_beijing"])
        self.assertEqual(bare["tz_confidence"], "inferred_weak")
        ambiguous = resolve_tested_at("2025-06-03 21:00 CST")
        self.assertIsNone(ambiguous["tested_at_beijing"])
        self.assertEqual(ambiguous["tz_confidence"], "inferred_weak")
        for case_id in INFERRED_TIME_CASES:
            observation = self.cases[case_id]["expected"]["observations"][0]
            resolved = resolve_tested_at(observation["tested_at_raw"])
            self.assertIsNone(resolved["tested_at_beijing"], case_id)
            self.assertNotEqual(resolved["tested_at_beijing"], observation["tested_at_beijing"])

    def test_gib_is_not_rewritten_as_gb(self):
        fields = self.cases["FX-007"]["expected"]["plans"][0]["fields"]
        disk = retain_unit(fields["disk_value"], fields["disk_unit"])
        traffic = retain_unit(fields["traffic_value"], fields["traffic_unit"])
        self.assertEqual(disk, {"value": 50, "unit": "GiB"})
        self.assertEqual(traffic, {"value": 1000, "unit": "GB"})

    def test_asn4809_does_not_create_gia_and_single_sample_has_no_stability_tag(self):
        route = self.cases["FX-010"]["expected"]["observations"][0]["routes"][0]
        tags = derive_route_tags(route["asn_path"], route["route_tags"])
        self.assertEqual(tags, [])
        self.assertNotIn("CN2_GIA", tags)
        stated = derive_route_tags([4809], ["CMIN2"])
        self.assertEqual(stated, ["CMIN2"])
        explicit = derive_route_tags([4809], ["CN2 GIA"])
        self.assertEqual(explicit, ["CN2 GIA"])
        for case_id, case in self.cases.items():
            derived = derive_samples(case["expected"]["observations"])
            expected = case["expected"]["derived"]
            self.assertEqual(derived["tags"], [], case_id)
            self.assertIsNone(derived["aggregates"]["route_stability"], case_id)
            self.assertEqual(derived["aggregates"]["gb6_single_samples"], expected["aggregates"]["gb6_single_samples"], case_id)
            self.assertEqual(derived["aggregates"]["gb6_single_median"], expected["aggregates"]["gb6_single_median"], case_id)
            self.assertNotIn("#线路稳定", derived["tags"])

    def test_geekbench_major_versions_stay_in_separate_buckets(self):
        buckets = benchmark_buckets(self.cases["FX-009"]["expected"]["observations"])
        self.assertEqual(buckets[("geekbench", 5, "single_core")], [1100])
        self.assertEqual(buckets[("geekbench", 6, "single_core")], [1400])
        self.assertNotIn(("geekbench", None, "single_core"), buckets)
        separated = benchmark_buckets([{
            "benchmarks": [
                {"suite": "geekbench", "version_major": 6, "metric": "single_core", "score": 1},
                {"suite": "geekbench", "version_major": 7, "metric": "single_core", "score": 2},
            ]
        }])
        self.assertEqual(set(separated), {("geekbench", 6, "single_core"), ("geekbench", 7, "single_core")})

    def test_missing_currency_stays_null(self):
        missing = normalize_price({"amount": 9, "currency": None, "billing_period_months": 1, "term_role": "renewal"})
        self.assertIsNone(missing["currency"])
        self.assertEqual(missing["status"], "unknown")
        self.assertIsNone(missing["monthly_equivalent"])
        guessed = normalize_price({
            "amount": 0.99, "currency": "USD", "billing_period_months": 1, "term_role": "renewal",
            "note": "未写币种，按模板约定默认USD",
        })
        self.assertIsNone(guessed["currency"])
        self.assertNotEqual(guessed["currency"], "USD")
        explicit = normalize_price({"amount": 10, "currency": "usd", "billing_period_months": 1, "term_role": "renewal"})
        self.assertEqual(explicit["currency"], "USD")
        self.assertEqual(explicit["monthly_equivalent"], 10)
        renewal = self.cases["FX-006"]["expected"]["plans"][0]["prices"]
        self.assertEqual(normalize_price(renewal[0])["term_role"], "first_term")
        self.assertEqual(normalize_price(renewal[1])["monthly_equivalent"], 12)
        self.assertEqual(normalize_price(renewal[2])["currency"], "CNY")

    def test_affiliate_slot_is_empty_and_ignores_source_text(self):
        self.assertIsNone(affiliate_url())
        self.assertIsNone(affiliate_url({}))
        self.assertIsNone(affiliate_url({"affiliate_url": None}))
        excerpt = self.cases["FX-001"]["raw"] + "\nhttps://example.com/buy?aff=1"
        self.assertIsNone(affiliate_from_source(excerpt))
        self.assertIsNone(affiliate_from_source(excerpt, {}))

    def test_multi_plan_and_keep_both_are_not_adapted_into_vps_analysis(self):
        multi = vps_analysis_adaptation("FX-002")
        conflict = vps_analysis_adaptation("FX-003")
        self.assertFalse(multi["adapted"])
        self.assertFalse(conflict["adapted"])
        self.assertIsNone(multi["selected_plan_id"])
        self.assertIsNone(multi["monthly_price"])
        self.assertIsNone(conflict["memory_mb"])
        self.assertEqual(len(self.cases["FX-002"]["expected"]["plans"]), 2)
        self.assertIsNone(self.cases["FX-003"]["expected"]["plans"][0]["fields"]["memory_mb"])
        self.assertEqual(self.cases["FX-003"]["expected"]["observations"][0]["conflicts"][0]["resolution"], "keep_both")
        prepared = apply_explicit_times(self.cases["FX-003"]["expected"])
        self.assertIsNone(prepared["plans"][0]["fields"]["memory_mb"])
        self.assertTrue(vps_analysis_adaptation("FX-001")["adapted"])
        self.assertIn("两个套餐", multi["reason"])
        self.assertIn("keep_both", conflict["reason"])


if __name__ == "__main__":
    unittest.main()
