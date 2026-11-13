"""S2 fix1 RED: literal expectations; only in-memory synthetic fixture copies."""
import copy
from pathlib import Path
import tempfile
import unittest

from vps_pipeline import contract_v2 as c
from vps_pipeline.public_dto import build_public_site
from tests.test_contract_v2 import load, ROOT
from tests.test_public_dto_pages import VisibleBody


def single_fx002():
    doc = copy.deepcopy(load('FX-002'))
    doc['plans'] = doc['plans'][:1]
    doc['notice'] = '人工构造，非真实帖子；S2 fix1 内存合成用例'
    return doc


class S2Fix1RedTests(unittest.TestCase):
    def assert_detail(self, doc, marker):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build_public_site(doc, out)
            visible = VisibleBody((out / 'offers/FX-002.html').read_text(
                encoding='utf-8')).text
            self.assertIn(marker, visible)

    def test_price_amount_keep_both_end_to_end(self):
        doc = single_fx002()
        prices_before = copy.deepcopy(doc['plans'][0]['prices'])
        doc['observations'][0]['conflicts'] = [{
            'field': 'amount', 'resolution': 'keep_both',
            'values': [{'source': 'text', 'raw': '5 USD',
                        'normalized_mb_candidate': None},
                       {'source': 'ocr', 'raw': '8 USD',
                        'normalized_mb_candidate': None}],
        }]
        self.assertTrue(doc['synthetic'])
        self.assertIn('人工构造，非真实帖子', doc['notice'])
        self.assertEqual(len(doc['plans']), 1)
        self.assertEqual(doc['plans'][0]['prices'], prices_before)
        self.assertEqual(prices_before[0]['amount'], 5)
        self.assertIsNone(c.validate_review_document_v2(doc))
        dto = c.project_review_document_to_public_dto(doc)
        self.assertEqual(dto['schema_version'], 'public-dto/v2')
        price = dto['offers'][0]['price']
        self.assertIsNone(price['amount'])
        self.assertEqual(price['price_status'], 'unresolved_conflict')
        self.assertIsNone(price['monthly_equivalent'])
        self.assertEqual(price['currency'], 'USD')
        self.assertEqual(price['billing_period_months'], 1)
        self.assertEqual(price['term_role'], 'renewal')
        self.assertIsNone(c.validate_public_dto_compatible(dto))
        self.assert_detail(doc, '价格未选定')

    def test_port_keep_both_end_to_end(self):
        doc = single_fx002()
        doc['plans'][0]['fields']['port_mbps'] = 1000
        doc['observations'][0]['conflicts'] = [{
            'field': 'port', 'resolution': 'keep_both',
            'values': [{'source': 'text', 'raw': '1000 Mbps',
                        'normalized_mb_candidate': None},
                       {'source': 'ocr', 'raw': '2000 Mbps',
                        'normalized_mb_candidate': None}],
        }]
        self.assertEqual(doc['plans'][0]['fields']['port_mbps'], 1000)
        self.assertIsNone(c.validate_review_document_v2(doc))
        dto = c.project_review_document_to_public_dto(doc)
        self.assertEqual(dto['schema_version'], 'public-dto/v2')
        self.assertIsNone(dto['offers'][0]['port_speed_mbps'])
        self.assertIsNone(c.validate_public_dto_compatible(dto))
        self.assert_detail(doc, '端口未选定')

    def test_d2_document_supersedes_offline_rules(self):
        text = (ROOT / 'docs/CONTRACT-v2.md').read_text(encoding='utf-8')
        d2 = text.split('## D2 日期', 1)[1].split('\n## ', 1)[0]
        for token in ('DATA_CONTRACT.md', '72', '74', 'FX-008A',
                      'FX-008B', 'FX-011', 'inferred_weak'):
            with self.subTest(token=token):
                self.assertIn(token, d2)
        self.assertRegex(d2, r'作废|取代|废止')

    def test_timezone_free_full_timestamp_preserves_clock_evidence(self):
        doc = single_fx002()
        doc['observations'][0]['tested_at_raw'] = '2025-06-03T17:30:00'
        before = copy.deepcopy(doc)
        normalized = c.normalize_tested_at('2025-06-03T17:30:00')
        self.assertEqual(normalized['review_date'], '2025-06-03')
        self.assertEqual(normalized['review_date_precision'], 'day')
        self.assertIsNone(normalized['tested_at_beijing'])
        self.assertEqual(normalized['tz_confidence'], 'unknown')
        self.assertEqual(normalized['review_date_tz'], 'unknown')
        self.assertEqual(normalized['tested_at_raw'], '2025-06-03T17:30:00')
        self.assertIn('17:30:00', normalized['tested_at_raw'])
        self.assertIsNone(c.validate_review_document_v2(doc))
        dto = c.project_review_document_to_public_dto(doc)
        self.assertIsNone(c.validate_public_dto_compatible(dto))
        offer = dto['offers'][0]
        self.assertEqual(offer['review_date'], '2025-06-03')
        self.assertEqual(offer['review_date_precision'], 'day')
        self.assertIsNone(offer['tested_at_beijing'])
        self.assertEqual(offer['review_date_tz'], 'unknown')
        self.assertEqual(doc, before)
        evidence = doc['observations'][0]
        self.assertEqual(evidence['tz_confidence'], 'unknown')
        self.assertEqual(evidence['tested_at_raw'], '2025-06-03T17:30:00')
        self.assertIn('17:30:00', evidence['tested_at_raw'])
