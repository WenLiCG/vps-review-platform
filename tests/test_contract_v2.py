"""S2 PHASE 1，所有期望手写，输入仅为结构化合成数据。

规格缺口：离线 FX-008A/B/011 的北京零点和 inferred_weak 与 PM D2 冲突；
本测试采用 D2：日精度、unknown、北京时间 null，但仍可筛选且文件名保留日期。
接口约定：suggested_export_filename 接受整个文档；结构化公开冲突使用 conflicts，
values 仅保留 source/raw/normalized_mb_candidate，不含 evidence 或 asset_ref。
清单缺口：status 未给枚举，合成不完整清单采用 incomplete，不推断其他状态枚举。
"""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from vps_pipeline import contract_v2 as c
from vps_pipeline.public_dto import project_to_public_dto, validate_public_dto, _validate
from tests.test_public_dto import expected_dto
from tests.test_public_dto_pages import VisibleBody

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/contract-v2'


def load(name):
    return json.loads((FIXTURES / (name + '.json')).read_text(encoding='utf-8'))


class ContractV2Tests(unittest.TestCase):
    def test_version_constants(self):
        self.assertEqual(c.CONTRACT_V2_VERSION, 'contract/v2')
        self.assertEqual(c.REVIEW_DOCUMENT_SCHEMA_VERSION, 'review-document/v2')
        self.assertEqual(c.PUBLIC_DTO_V1_VERSION, 'public-dto/v1')
        self.assertEqual(c.PUBLIC_DTO_V2_VERSION, 'public-dto/v2')
        self.assertEqual(c.CAPTURE_MANIFEST_SCHEMA_VERSION, 'capture-manifest/v1')
        self.assertEqual(c.PRICE_SEMANTICS_VERSION, 'price-semantics/v2')

    def test_document_and_schema_versions(self):
        # No PHASE 1 fake document/schema: assertion records what PHASE 2 must deliver.
        doc = ROOT / 'docs/CONTRACT-v2.md'
        self.assertTrue(doc.is_file(), 'PHASE 2 must implement docs/CONTRACT-v2.md')
        text = doc.read_text(encoding='utf-8')
        for version, path in (
            (c.REVIEW_DOCUMENT_SCHEMA_VERSION, 'schemas/review-document/v2/review-document.schema.json'),
            (c.PUBLIC_DTO_V1_VERSION, 'schemas/public-dto/v1/public-dto.schema.json'),
            (c.PUBLIC_DTO_V2_VERSION, 'schemas/public-dto/v2/public-dto.schema.json'),
            (c.CAPTURE_MANIFEST_SCHEMA_VERSION, 'schemas/capture-manifest/v1/capture-manifest.schema.json'),
            (c.PRICE_SEMANTICS_VERSION, 'schemas/price-semantics/v2/price-semantics.json'),
        ):
            with self.subTest(path=path):
                self.assertIn(version, text)
                self.assertIn(path, text)
                self.assertTrue((ROOT / path).is_file(), path)
                schema = json.loads((ROOT / path).read_text())
                self.assertEqual(schema['properties']['schema_version']['const'], version)
                if version != c.PRICE_SEMANTICS_VERSION:
                    self.assertIs(schema['additionalProperties'], False)
        for phrase in ('contract/v2', '1.0.0-offline', 'unknown', 'renewal', '汇率'):
            self.assertIn(phrase, text)

    def test_d2_a_date_only_explicit(self):
        n = c.normalize_tested_at(load('FX-008A')['observations'][0]['tested_at_raw'])
        self.assertEqual(n['tested_at_raw'], '2025-06-03')
        self.assertEqual(n['review_date'], '2025-06-03')
        self.assertRegex(n['review_date'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertNotIn('T', n['review_date'])
        self.assertEqual(n['review_date_precision'], 'day')
        self.assertEqual(n['tz_confidence'], 'unknown')
        self.assertEqual(n['review_date_tz'], 'unknown')
        self.assertIsNone(n['tested_at_beijing'])
        self.assertNotEqual(n['tested_at_beijing'], '2025-06-03T00:00:00+08:00')
        self.assertEqual(n['filename_date_segment'], '20250603')

    def test_d2_a_date_only_participates_in_filter(self):
        for start, end, expected in (('2025-06-03','2025-06-03',True),
                ('2025-06-01','2025-06-30',True), ('2025-07-01','2025-07-31',False)):
            with self.subTest(start=start):
                self.assertIs(c.matches_review_date_filter('2025-06-03',start,end),expected)

    def test_d2_b_missing_date_never_uses_published_at(self):
        d = load('FX-004')
        self.assertEqual(d['source']['published_at'], '2025-09-10T20:00:00+08:00')
        self.assertIsNone(d['observations'][0]['tested_at_raw'])
        n = c.normalize_tested_at(None)
        self.assertIsNone(n['tested_at_beijing'])
        self.assertIsNone(n['review_date'])
        self.assertEqual(n['filename_date_segment'], 'unknownDate')
        f = c.suggested_export_filename(d)
        self.assertEqual(f['suggested_filename'], 'unknownPrice_unknownLoc_2C2G40G_unknownDate__synth-004')
        self.assertNotIn('20250910',f['suggested_filename'])
        self.assertIs(c.matches_review_date_filter(None,'2025-09-01','2025-09-30'),False)

    def test_d2_c_explicit_utc_crosses_day(self):
        self.assertEqual(load('FX-005')['observations'][0]['tested_at_raw'],'2025-06-03T17:30:00Z')
        n = c.normalize_tested_at('2025-06-03T17:30:00Z')
        self.assertIsNotNone(n['tested_at_beijing'])
        self.assertEqual(n['tested_at_beijing'],'2025-06-04T01:30:00+08:00')
        self.assertEqual(n['tz_confidence'],'explicit')
        self.assertEqual(n['filename_date_segment'],'20250604')
        self.assertEqual(c.suggested_export_filename(load('FX-005'))['suggested_filename'],
                         'unknownPrice_unknownLoc_unknownCfg_20250604')

    def test_fx008ab_generated_filenames_and_corrected_dates(self):
        results=[]
        for name, suffix, expected in (
            ('FX-008A','synth-008a','10USD-mo_伦敦_2C4G100G_20250603__synth-008a'),
            ('FX-008B','synth-008b','10USD-mo_伦敦_2C4G100G_20250603__synth-008b')):
            with self.subTest(name=name):
                d=load(name)
                n=c.normalize_tested_at(d['observations'][0]['tested_at_raw'])
                self.assertIsNone(n['tested_at_beijing'])
                self.assertEqual(n['tz_confidence'],'unknown')
                self.assertEqual(n['review_date_tz'],'unknown')
                self.assertEqual(n['review_date'],'2025-06-03')
                self.assertEqual(n['review_date_precision'],'day')
                f=c.suggested_export_filename(d)
                self.assertEqual(f['suggested_filename'],expected)
                self.assertEqual(f['collision_suffix'],suffix)
                self.assertEqual(d['source']['source_post_id'],suffix)
                results.append(f['suggested_filename'])
        self.assertEqual(len(results),2, 'both filename generation calls must succeed')
        self.assertEqual(results[0].split('__')[0],results[1].split('__')[0])
        self.assertNotEqual(results[0],results[1])

    def test_fx008ab_public_facts_handwritten(self):
        for name, post in (('FX-008A','synth-008a'),('FX-008B','synth-008b')):
            with self.subTest(name=name):
                dto=c.project_review_document_to_public_dto(load(name))
                self.assertEqual(len(dto['offers']),1)
                o=dto['offers'][0]
                self.assertEqual(o['post_id'],post)
                self.assertEqual((o['vcpu'],o['memory_mb'],o['disk_total_value'],o['disk_total_unit']),
                                 (2,4096,100,'GB'))
                self.assertEqual(o['location'],{'raw':'欧洲/伦敦','continent':'欧洲','city':'伦敦','country':'GB'})
                self.assertEqual(o['price'],{'amount':10,'currency':'USD','billing_period_months':1,
                    'term_role':'renewal','monthly_equivalent':10,'price_status':'known'})
                self.assertEqual(o['review_date'],'2025-06-03')
                self.assertEqual(o['review_date_precision'],'day')
                self.assertEqual(o['review_date_tz'],'unknown')
                self.assertIsNone(o['tested_at_beijing'])

    def test_fx011_derive_no_stability_from_one_independent_sample(self):
        d=load('FX-011')
        obs=d['observations']; policy=d['derived']['sample_policy']
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]['routes'][0]['route_tags'],['CMIN2'])
        self.assertEqual(policy,{'min_samples_for_stability_tag':5,'dedupe_by_run_id':True})
        self.assertEqual(c.derive_stability_tags(obs,policy),[])
        self.assertEqual(c.derive_stability_tags(obs*5,policy),[], 'duplicate run_id must not manufacture five samples')
        self.assertEqual(d['derived']['tags'],[])
        self.assertIsNone(d['derived']['aggregates']['route_stability'])
        self.assertEqual(d['derived']['aggregates']['gb6_single_samples'],0)
        self.assertFalse(any('稳定' in tag for tag in c.derive_stability_tags(obs,policy)))

    def test_fx011_date_and_generated_filename(self):
        d=load('FX-011'); n=c.normalize_tested_at(d['observations'][0]['tested_at_raw'])
        self.assertEqual(n['review_date'],'2025-01-14')
        self.assertEqual(n['review_date_precision'],'day')
        self.assertIsNone(n['tested_at_beijing'])
        self.assertEqual(n['tz_confidence'],'unknown')
        self.assertEqual(n['review_date_tz'],'unknown')
        self.assertEqual(c.suggested_export_filename(d),{
            'suggested_filename':'unknownPrice_unknownLoc_unknownCfg_20250114__synth-011',
            'collision_suffix':'synth-011'})

    def test_price_monthly_handwritten(self):
        for amount,period,expected in ((24,12,2),(5,1,5),(24,None,None),(24,0,None),
                                       (24,-1,None),(24,1.5,None),(24,True,None)):
            with self.subTest(period=period):
                self.assertEqual(c.monthly_equivalent(amount,period),expected)

    def test_price_range_requires_currency_and_period_without_exchange(self):
        for currency,period,expected in (('USD',12,True),('CNY',1,True),
                                        (None,12,False),('unknown',1,False),('USD',None,False),('USD',0,False)):
            with self.subTest(currency=currency,period=period):
                self.assertIs(c.price_eligible_for_range_filter({'amount':24,'currency':currency,
                    'billing_period_months':period,'term_role':'renewal'}),expected)
        self.assertEqual(c.monthly_equivalent(24,12),2)  # currency independent, no FX conversion
        self.assertFalse(hasattr(c,'EXCHANGE_RATES'))

    def test_review_schema_valid_offline_and_v2(self):
        for version in ('1.0.0-offline','review-document/v2'):
            with self.subTest(version=version):
                d=load('FX-002'); d['schema_version']=version
                self.assertIsNone(c.validate_review_document_v2(d))

    def test_review_schema_rejects_missing_version_and_invalid_terms(self):
        for mutation in ('missing_version','wrong_version','bad_term','bad_status'):
            with self.subTest(mutation=mutation):
                d=load('FX-002')
                if mutation=='missing_version': del d['schema_version']
                elif mutation=='wrong_version': d['schema_version']='review-document/v0'
                elif mutation=='bad_term': d['plans'][0]['prices'][0]['term_role']='forever'
                else: d['plans'][0]['prices'][0]['price_status']='forever'
                with self.assertRaises(ValueError): c.validate_review_document_v2(d)

    def test_capture_manifest_valid_with_explicit_missing_tabs(self):
        d=load('capture-manifest')
        self.assertEqual([t['status'] for t in d['tabs']],['captured','missing','not_present'])
        self.assertIsNone(c.validate_capture_manifest(d))

    def test_capture_manifest_rejects_every_missing_required_field(self):
        for key in load('capture-manifest'):
            if key in ('notice','synthetic'): continue
            with self.subTest(key=key):
                d=load('capture-manifest'); del d[key]
                with self.assertRaises(ValueError): c.validate_capture_manifest(d)

    def test_capture_manifest_invalid_enum_unknown_keys_version_hash(self):
        for case in ('version','tab_status','sha_missing','sha_bad','image_hash','unknown_root','unknown_tab','unknown_image'):
            with self.subTest(case=case):
                d=load('capture-manifest')
                if case=='version': d['schema_version']='capture-manifest/v0'
                elif case=='tab_status': d['tabs'][0]['status']='done'
                elif case=='sha_missing': del d['tabs'][0]['sha256']
                elif case=='sha_bad': d['tabs'][0]['sha256']='g'*64
                elif case=='image_hash': d['images'][0]['sha256']='abc'
                else: (d if case=='unknown_root' else d['tabs'][0] if case=='unknown_tab' else d['images'][0])['unexpected']=True
                with self.assertRaises(ValueError): c.validate_capture_manifest(d)


class ExistingV1CompatibilityTests(unittest.TestCase):
    def test_existing_files_exact_v1_and_schema(self):
        internal=json.loads((ROOT/'tests/fixtures/public-dto/FX-001.internal.json').read_text())
        data=json.loads((ROOT/'website/public-dto-v1/data.json').read_text())
        schema=json.loads((ROOT/'schemas/public-dto/v1/public-dto.schema.json').read_text())
        self.assertEqual(project_to_public_dto(internal),expected_dto())
        self.assertEqual(data,expected_dto())
        self.assertEqual(data['schema_version'],'public-dto/v1')
        self.assertEqual(data['offers'][0]['offer_id'],'FX-001')
        self.assertEqual(data['offers'][0]['tested_at_beijing'],'2025-06-03T21:00:00+08:00')
        self.assertEqual(schema['title'],'public-dto/v1')
        self.assertEqual(schema['properties']['schema_version']['const'],'public-dto/v1')
        for dto in (data,expected_dto()):
            self.assertIsNone(validate_public_dto(dto))
            self.assertIsNone(_validate(dto,schema,'$'))

    def test_new_compatible_validator_reads_existing_v1(self):
        d=json.loads((ROOT/'website/public-dto-v1/data.json').read_text())
        self.assertIsNone(c.validate_public_dto_compatible(d))

    def test_existing_html_visible_and_analysis_contract_unchanged(self):
        detail=VisibleBody((ROOT/'website/public-dto-v1/offers/FX-001.html').read_text())
        for fact in ('FX-001','示例云','London Mini','2025-06-03T21:00:00+08:00'):
            self.assertIn(fact,detail.text)
        index=VisibleBody((ROOT/'website/public-dto-v1/index.html').read_text())
        self.assertIn('FX-001',index.text)
        self.assertIn('offers/FX-001.html',index.links)
        for path in ('skills/vps-review-analyze/references/contract.md',
                     'skills/vps-review-analyze/references/fields.json','tests/test_analysis.py'):
            self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT),path)
        self.assertIn('vps-analysis/1',(ROOT/'skills/vps-review-analyze/references/contract.md').read_text())
