"""手写多套餐、keep_both 和静态 HTML 验收，不执行 JavaScript。

接口缺口记录：本测试选择 public-dto/v2 的 conflicts.values 公开候选结构，
页级路径采用 offers/FX-002.html 和 offers/FX-003.html。
扫描只是子串/键名检查，不能证明所有可能隐私泄漏均被识别。
"""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from vps_pipeline import contract_v2 as c
from vps_pipeline.public_dto import build_public_site, scan_public_output
from tests.test_contract_v2 import load, ROOT
from tests.test_public_dto import expected_dto, FORBIDDEN_KEYS
from tests.test_public_dto_pages import VisibleBody

CANARIES = {
    'FX-002': ('pk_synth_do_not_publish_FX002','fixture_author_b',
               '套餐A：1核 1G 20G','套餐B：2核 4G 40G','capture/tab-fx002.txt'),
    'FX-003': ('pk_synth_do_not_publish_FX003','fixture_author_c',
               '内存 2GB','Memory: 4.0 GiB','assets/synth-img-mem.png',
               'capture/tab-fx003.txt','rule_text','ocr_expected_input'),
}
SUMMARIES = {
    'FX-002':'同帖含月付与年付两套餐，不得压成一条 plan。',
    'FX-003':'正文与图片内存数值冲突，已保留双方证据，未选定唯一 memory_mb。',
}


class ContractV2PagesTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.out=Path(t.name)/'site'

    def assert_clean(self, text, name):
        for marker in (*CANARIES[name], 'extractor', 'confidence', 'private_key'):
            self.assertNotIn(marker,text)
        for key in (*FORBIDDEN_KEYS,'asset_ref','extractor','confidence'):
            self.assertIsNone(re.search(r'"'+re.escape(key)+r'"\s*:',text),key)

    def test_fx002_projection_exact_two_plans_prices_and_locations(self):
        d=load('FX-002'); before=copy.deepcopy(d)
        self.assertEqual(len(d['plans']),2)
        self.assertEqual([p['plan_id'] for p in d['plans']],['synth-002-plan-a','synth-002-plan-b'])
        dto=c.project_review_document_to_public_dto(d)
        self.assertEqual(d,before)
        self.assertEqual(dto['schema_version'],'public-dto/v2')
        self.assertEqual(len(dto['offers']),2)
        for o, oid, label, cpu, mem, disk, amount, months, monthly in (
            (dto['offers'][0],'FX-002-A','A',1,1024,20,5,1,5),
            (dto['offers'][1],'FX-002-B','B',2,4096,40,24,12,2)):
            with self.subTest(offer=oid):
                self.assertEqual(o['offer_id'],oid)
                self.assertRegex(o['offer_id'],r'^[A-Za-z0-9_-]+$')
                self.assertEqual(o['plan_label'],label)
                self.assertEqual(o['post_id'],'synth-002')
                self.assertEqual(o['canonical_url'],'https://synthetic.example/post/synth-002')
                self.assertEqual(o['vendor_raw'],'双鸡云')
                self.assertEqual(o['location'],{'raw':'亚洲/东京','continent':'亚洲','city':'东京','country':'JP'})
                self.assertEqual((o['vcpu'],o['memory_mb'],o['disk_total_value'],o['disk_total_unit']),
                                 (cpu,mem,disk,'GB'))
                self.assertEqual(o['price'],{'amount':amount,'currency':'USD','billing_period_months':months,
                    'term_role':'renewal','monthly_equivalent':monthly,'price_status':'known'})
                self.assertIsNone(o['review_date'])
                self.assertIsNone(o['tested_at_beijing'])
                self.assertEqual(o['summary_text'],SUMMARIES['FX-002'])
                self.assertIs(o['limited_claim'],True)
        self.assertIsNone(c.validate_public_dto_compatible(dto))
        self.assert_clean(json.dumps(dto,ensure_ascii=False),'FX-002')

    def test_fx002_generated_multi_filename(self):
        self.assertEqual(c.suggested_export_filename(load('FX-002')),{
            'suggested_filename':'MULTI_东京_unknownDate__synth-002','collision_suffix':'synth-002'})

    def test_fx003_projection_preserves_null_and_both_candidates(self):
        d=load('FX-003')
        self.assertIsNone(d['plans'][0]['fields']['memory_mb'])
        original=d['observations'][0]['conflicts'][0]
        self.assertEqual(original['resolution'],'keep_both')
        self.assertEqual([(v['source'],v['raw'],v['normalized_mb_candidate']) for v in original['values']],
                         [('text','2GB',2048),('ocr','4.0 GiB',4096)])
        dto=c.project_review_document_to_public_dto(d)
        self.assertEqual(dto['schema_version'],'public-dto/v2')
        self.assertEqual(len(dto['offers']),1)
        o=dto['offers'][0]
        self.assertEqual(o['offer_id'],'FX-003')
        self.assertEqual(o['post_id'],'synth-003')
        self.assertEqual(o['canonical_url'],'https://synthetic.example/post/synth-003')
        self.assertIsNone(o['memory_mb'])
        self.assertIn('memory: keep_both',o['conflict_flags'])
        self.assertEqual(o['conflicts'],[{'field':'memory','resolution':'keep_both','values':[
            {'source':'text','raw':'2GB','normalized_mb_candidate':2048},
            {'source':'ocr','raw':'4.0 GiB','normalized_mb_candidate':4096}]}])
        self.assertEqual(o['summary_text'],SUMMARIES['FX-003'])
        self.assertIs(o['limited_claim'],True)
        self.assertIsNone(c.validate_public_dto_compatible(dto))
        self.assert_clean(json.dumps(dto,ensure_ascii=False),'FX-003')

    def test_fx003_generated_unknown_filename(self):
        self.assertEqual(c.suggested_export_filename(load('FX-003')),{
            'suggested_filename':'unknownPrice_unknownLoc_unknownCfg_unknownDate__synth-003',
            'collision_suffix':'synth-003'})

    def build_review(self,name):
        d=load(name)
        # Validating first makes PHASE 1 fail on the missing function rather than S1's input shape.
        c.validate_review_document_v2(d)
        build_public_site(d,self.out)
        return json.loads((self.out/'data.json').read_text())

    def test_fx002_same_detail_body_and_list_show_both_packages(self):
        dto=self.build_review('FX-002')
        self.assertEqual([o['offer_id'] for o in dto['offers']],['FX-002-A','FX-002-B'])
        detail=VisibleBody((self.out/'offers/FX-002.html').read_text())
        index=VisibleBody((self.out/'index.html').read_text())
        for body in (detail,index):
            for fact in ('FX-002','A','B','双鸡云','东京','1','2','1024','4096','20','40','GB','5','24','USD','12'):
                with self.subTest(page='detail' if body is detail else 'index',fact=fact):
                    self.assertIn(fact,body.text)
            self.assertRegex(body.text,r'月付|周期\s*[:：]?\s*1\b|1\s*个月')
            self.assertRegex(body.text,r'年付|周期\s*[:：]?\s*12\b|12\s*个月')
            self.assertRegex(body.text,r'月均\s*[:：]?\s*2\b|月均[^\d]{0,10}2\b')
        self.assertIn('offers/FX-002.html',index.links)
        self.assertIn('https://synthetic.example/post/synth-002',detail.links)

    def test_fx003_visible_conflict_unselected_memory_and_candidates(self):
        dto=self.build_review('FX-003')
        self.assertIsNone(dto['offers'][0]['memory_mb'])
        body=VisibleBody((self.out/'offers/FX-003.html').read_text())
        for fact in ('FX-003','keep_both','2048','4096'):
            self.assertIn(fact,body.text)
        self.assertRegex(body.text,r'内存|memory')
        self.assertRegex(body.text,r'冲突')
        self.assertRegex(body.text,r'未选定|null|无')

    def test_public_builds_strip_internal_canaries_everywhere(self):
        for name in ('FX-002','FX-003'):
            with self.subTest(name=name):
                d=load(name)
                self.assertIs(d['synthetic'],True)
                self.assertIn('人工构造，非真实帖子',d['notice'])
                internal=json.dumps(d,ensure_ascii=False)
                for marker in CANARIES[name]: self.assertIn(marker,internal)
                self.build_review(name)
                scanned=set()
                for p in self.out.rglob('*'):
                    if p.is_file():
                        scanned.add(p.relative_to(self.out).as_posix())
                        self.assert_clean(p.read_text(encoding='utf-8'),name)
                self.assertTrue({'index.html','data.json','offers/'+name+'.html'} <= scanned)
                self.assertIsNone(scan_public_output(self.out))

    def test_existing_fx001_still_builds_exact_v1(self):
        d=json.loads((ROOT/'tests/fixtures/public-dto/FX-001.internal.json').read_text())
        build_public_site(d,self.out)
        self.assertEqual(json.loads((self.out/'data.json').read_text()),expected_dto())
        self.assertIn('FX-001',VisibleBody((self.out/'offers/FX-001.html').read_text()).text)
