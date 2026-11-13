"""PHASE 1 RED: 手写通用 keep_both 期望，不修改既有夹具或实现。

KEEP_BOTH_PUBLIC_FIELDS 采用冲突别名到公开字段路径集合的显式映射；
价格子字段使用 price.amount 等点路径。文档须逐行列明别名、目标与中文标签。
磁盘 raw 是事实；normalized_mb_candidate=null 不表示磁盘的规范化单位。
"""
import copy
import json
import re
from pathlib import Path
import tempfile
import unittest

from vps_pipeline import contract_v2 as c
from vps_pipeline.public_dto import build_public_site, scan_public_output
from tests.test_public_dto_pages import VisibleBody

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/contract-v2/FX-S2-DISK.json'
ASSET_CANARY = 'assets/synth-s2-disk-private.png'

# 权威任务书中的别名、公开字段路径、页面标签；期望不从实现推导。
MAPPING_ROWS = (
    (('memory', 'memory_mb'), ('memory_mb',), '内存'),
    (('disk', 'disk_value', 'disk_total_value'),
     ('disk_total_value', 'disk_total_unit'), '磁盘'),
    (('disk_unit', 'disk_total_unit'), ('disk_total_unit',), '磁盘单位'),
    (('disk_type',), ('disk_type',), '磁盘类型'),
    (('port', 'port_mbps', 'port_speed_mbps'), ('port_speed_mbps',), '端口'),
    (('vcpu',), ('vcpu',), 'vCPU'),
    (('traffic', 'traffic_value'), ('traffic_value', 'traffic_unit'), '流量'),
    (('traffic_unit',), ('traffic_unit',), '流量单位'),
    (('price',),
     ('price.amount', 'price.currency', 'price.billing_period_months',
      'price.term_role', 'price.monthly_equivalent'), '价格'),
    (('amount',), ('price.amount', 'price.monthly_equivalent'), '价格'),
    (('currency',), ('price.currency',), '价格'),
    # 月均由金额和周期派生；周期冲突时也清空月均。
    (('billing_period_months',),
     ('price.billing_period_months', 'price.monthly_equivalent'), '价格'),
    (('term_role',), ('price.term_role',), '价格'),
    (('monthly_equivalent',), ('price.monthly_equivalent',), '价格'),
)


def load_disk():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


class KeepBothContractTests(unittest.TestCase):
    def test_fixture_valid_with_deliberately_selected_disk(self):
        doc = load_disk()
        self.assertIs(doc['synthetic'], True)
        self.assertIn('人工构造，非真实帖子', doc['notice'])
        self.assertEqual(doc['sample_id'], 'FX-S2-DISK')
        self.assertEqual(doc['source']['source_post_id'], 'synth-s2-disk')
        self.assertEqual(doc['source']['url'],
                         'https://synthetic.example/post/synth-s2-disk')
        self.assertEqual(len(doc['plans']), 1)
        self.assertEqual(doc['plans'][0]['fields']['disk_value'], 40)
        self.assertEqual(doc['plans'][0]['fields']['disk_unit'], 'GB')
        self.assertIsNone(c.validate_review_document_v2(doc))

    def test_projection_clears_disk_value_and_unit(self):
        offer = c.project_review_document_to_public_dto(load_disk())['offers'][0]
        for field in ('disk_total_value', 'disk_total_unit'):
            with self.subTest(field=field):
                self.assertIsNone(offer[field])

    def test_projection_preserves_candidates_and_flag_without_internal_asset(self):
        doc = load_disk()
        before = copy.deepcopy(doc)
        dto = c.project_review_document_to_public_dto(doc)
        self.assertEqual(doc, before)
        self.assertEqual(len(dto['offers']), 1)
        offer = dto['offers'][0]
        self.assertIn('disk: keep_both', offer['conflict_flags'])
        conflicts = [item for item in offer['conflicts'] if item['field'] == 'disk']
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['resolution'], 'keep_both')
        self.assertCountEqual([item['raw'] for item in conflicts[0]['values']],
                              ['40GB', '80GB'])
        self.assertCountEqual([item['source'] for item in conflicts[0]['values']],
                              ['text', 'ocr'])
        public = json.dumps(dto, ensure_ascii=False)
        self.assertNotIn('asset_ref', public)
        self.assertNotIn(ASSET_CANARY, public)

    def test_detail_page_marks_disk_unselected_and_retains_candidates(self):
        doc = load_disk()
        c.validate_review_document_v2(doc)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            build_public_site(doc, out)
            visible = VisibleBody((out / 'offers/FX-S2-DISK.html').read_text(
                encoding='utf-8')).text
            for fact in ('FX-S2-DISK', 'keep_both', '40GB', '80GB'):
                self.assertIn(fact, visible)
            for path in out.rglob('*'):
                if path.is_file():
                    public = path.read_text(encoding='utf-8')
                    self.assertNotIn('asset_ref', public)
                    self.assertNotIn(ASSET_CANARY, public)
            self.assertIsNone(scan_public_output(out))
            self.assertIn('磁盘未选定', visible)

    def test_unmapped_conflict_field_fails_closed(self):
        doc = copy.deepcopy(load_disk())
        doc['observations'][0]['conflicts'][0]['field'] = 'fictional_widget'
        c.validate_review_document_v2(doc)
        with self.assertRaisesRegex(ValueError, r'fictional_widget'):
            c.project_review_document_to_public_dto(doc)

    def test_explicit_mapping_constant_covers_all_required_aliases(self):
        self.assertTrue(hasattr(c, 'KEEP_BOTH_PUBLIC_FIELDS'),
                        'contract_v2 must expose KEEP_BOTH_PUBLIC_FIELDS')
        mapping = c.KEEP_BOTH_PUBLIC_FIELDS
        self.assertIsInstance(mapping, dict)
        for alias, targets in mapping.items():
            with self.subTest(no_null_price_status_for=alias):
                self.assertNotIn('price.price_status', targets)
        for aliases, targets, _label in MAPPING_ROWS:
            for alias in aliases:
                with self.subTest(alias=alias):
                    self.assertIn(alias, mapping)
                    for target in targets:
                        self.assertIn(target, mapping[alias])
                    if targets[0].startswith('price.'):
                        self.assertCountEqual(mapping[alias], targets)
                        if alias == 'amount':
                            self.assertEqual(mapping[alias][0], 'price.amount')

    def test_contract_documents_explicit_mapping_table(self):
        text = (ROOT / 'docs/CONTRACT-v2.md').read_text(encoding='utf-8')
        self.assertIn('keep_both', text)
        table_rows = [line for line in text.splitlines()
                      if line.lstrip().startswith('|')]
        for aliases, targets, label in MAPPING_ROWS:
            with self.subTest(aliases=aliases):
                if targets[0].startswith('price.'):
                    # 分别检查别名列与置空目标列，拒绝整组清空旧表。
                    for alias in aliases:
                        matching = [row.split('|') for row in table_rows
                                    if alias in re.findall(r'`([^`]+)`',
                                                          row.split('|')[1])]
                        self.assertTrue(matching, f'missing price alias: {alias}')
                        for cells in matching:
                            self.assertCountEqual(
                                re.findall(r'`([^`]+)`', cells[2]), targets)
                            self.assertIn(label, cells[3])
                    continue
                # 非价格行继续保留原有别名、目标和中文标签断言。
                tokens = (*aliases, *(target.split('.')[-1] for target in targets), label)
                self.assertTrue(any(all(token in row for token in tokens)
                                    for row in table_rows),
                                f'missing keep_both mapping row: {tokens}')

    def test_contract_documents_unresolved_price_conflict_status(self):
        text = (ROOT / 'docs/CONTRACT-v2.md').read_text(encoding='utf-8')
        self.assertIn('unresolved_conflict', text)
