"""PHASE 1 contract tests with handwritten public expectations."""
import copy
import json
from pathlib import Path
import unittest

from vps_pipeline.public_dto import project_to_public_dto, validate_public_dto

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/public-dto/FX-001.internal.json'
CANARIES = (
    'pk_synth_do_not_publish_FX001',
    'https://cdn.synthetic.example/original/fx001-hero.png',
    'INTERNAL RAW BODY MARKER FX001-SECRET-BODY',
    'sk_live_synth_fx001_not_for_public',
    'fixture_author_a', 'capture/tab-basic.txt',
)
FORBIDDEN_KEYS = (
    'evidence', 'field_evidence', 'quote', 'private_key', 'privateKey',
    'capture_file', 'screenshot', 'original_image_url', 'raw_excerpt',
    'raw_body', 'author', 'secrets', 'evidenceRefs', 'evidenceImages',
    'evidenceFileId', 'locator', 'extra',
)


def load_internal():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def expected_dto():
    # Deliberately independent of the fixture and production projection.
    return {'schema_version': 'public-dto/v1', 'offers': [{
        'offer_id': 'FX-001', 'post_id': 'synth-001',
        'canonical_url': 'https://synthetic.example/post/synth-001', 'aff_url': None,
        'vendor_raw': '示例云', 'plan_label': 'London Mini',
        'location': {'raw': '欧洲/伦敦', 'continent': '欧洲', 'city': '伦敦', 'country': 'GB'},
        'vcpu': 2, 'memory_mb': 4096, 'disk_total_value': 40,
        'disk_total_unit': 'GB', 'disk_type': 'NVMe', 'traffic_value': 1,
        'traffic_unit': 'TB', 'port_speed_mbps': 1000,
        'price': {'amount': 10, 'currency': 'USD', 'billing_period_months': 1,
                  'term_role': 'renewal', 'monthly_equivalent': 10, 'price_status': 'known'},
        'observations_summary': {'geekbench6_single': 1420}, 'conflict_flags': [],
        'summary_text': '基于已抽取字段：伦敦 2C4G40G，续费约 10 USD/月，GB6 单核 1420。',
        'limited_claim': True, 'published_date': '2025-06-04', 'published_tz': '+08:00',
        'review_date': '2025-06-03', 'review_date_precision': 'day',
        'tested_at_beijing': '2025-06-03T21:00:00+08:00',
    }]}


class PublicDTOValidationTests(unittest.TestCase):
    def test_handwritten_valid_dto(self):
        self.assertIsNone(validate_public_dto(expected_dto()))

    def test_unknown_keys_rejected_at_every_object_level(self):
        for level in ('root', 'offer', 'location', 'price', 'observations_summary'):
            for key in FORBIDDEN_KEYS:
                with self.subTest(level=level, key=key):
                    dto = expected_dto()
                    offer = dto['offers'][0]
                    target = dto if level == 'root' else offer if level == 'offer' else offer[level]
                    target[key] = 'unapproved'
                    with self.assertRaisesRegex(ValueError, r'\S'):
                        validate_public_dto(dto)

    def test_missing_required_fields_rejected(self):
        for level in ('root', 'offer', 'location', 'price', 'observations_summary'):
            base = expected_dto()
            offer = base['offers'][0]
            target = base if level == 'root' else offer if level == 'offer' else offer[level]
            for key in list(target):
                with self.subTest(level=level, key=key):
                    dto = copy.deepcopy(base)
                    item = dto if level == 'root' else dto['offers'][0] if level == 'offer' else dto['offers'][0][level]
                    del item[key]
                    with self.assertRaisesRegex(ValueError, r'\S'):
                        validate_public_dto(dto)

    def test_wrong_types_rejected(self):
        for key, value in [('vcpu', '2'), ('vcpu', True), ('memory_mb', []),
                           ('price', []), ('location', 'London'), ('aff_url', False),
                           ('limited_claim', 'true'), ('conflict_flags', {}),
                           ('observations_summary', []), ('vendor_raw', 123)]:
            with self.subTest(key=key, value=value):
                dto = expected_dto()
                dto['offers'][0][key] = value
                with self.assertRaisesRegex(ValueError, r'\S'):
                    validate_public_dto(dto)
        for key, value in [('offers', {}), ('schema_version', 1)]:
            with self.subTest(key=key):
                dto = expected_dto()
                dto[key] = value
                with self.assertRaisesRegex(ValueError, r'\S'):
                    validate_public_dto(dto)

    def test_aff_url_must_be_null(self):
        dto = expected_dto()
        dto['offers'][0]['aff_url'] = 'https://synthetic.example/aff'
        with self.assertRaisesRegex(ValueError, r'\S'):
            validate_public_dto(dto)

    def test_wrong_schema_version_rejected(self):
        dto = expected_dto()
        dto['schema_version'] = 'public-dto/v0'
        with self.assertRaisesRegex(ValueError, r'\S'):
            validate_public_dto(dto)


class PublicDTOProjectionTests(unittest.TestCase):
    def test_projection_matches_handwritten_expectation_and_preserves_input(self):
        internal = load_internal()
        before = copy.deepcopy(internal)
        dto = project_to_public_dto(internal)
        self.assertEqual(internal, before)
        self.assertEqual(dto, expected_dto())
        self.assertIsNone(validate_public_dto(dto))

    def test_fixture_contains_all_canaries_and_projection_removes_them(self):
        internal = load_internal()
        self.assertTrue(internal['synthetic'])
        self.assertIn('人工构造，非真实帖子', internal['notice'])
        source = json.dumps(internal, ensure_ascii=False)
        for marker in CANARIES:
            self.assertIn(marker, source)
        self.assertEqual(internal['plans'][0]['field_evidence']['vcpu']['quote'], '2核')
        public = json.dumps(project_to_public_dto(internal), ensure_ascii=False)
        for marker in CANARIES:
            self.assertNotIn(marker, public)
        for key in FORBIDDEN_KEYS:
            self.assertNotIn('"' + key + '":', public)

    def test_missing_internal_values_become_null_without_guessing(self):
        internal = load_internal()
        del internal['plans'][0]['memory_mb']
        del internal['plans'][0]['disk_type']
        dto = project_to_public_dto(internal)
        self.assertIsNone(dto['offers'][0]['memory_mb'])
        self.assertIsNone(dto['offers'][0]['disk_type'])
        validate_public_dto(dto)

    def test_original_summary_is_preserved(self):
        internal = load_internal()
        internal['summary']['text'] = '人工撰写的另一条有限简评。'
        dto = project_to_public_dto(internal)
        self.assertEqual(dto['offers'][0]['summary_text'], '人工撰写的另一条有限简评。')



    def test_distinct_prices_and_scores_are_conflicts_and_preserve_input(self):
        null_price = {'amount': None, 'currency': None, 'billing_period_months': None,
                      'term_role': None, 'monthly_equivalent': None, 'price_status': None}
        for price_conflict, score_conflict, existing in (
            (True, False, []), (False, True, []), (True, True, []),
            (True, False, ['pre-existing']),
        ):
            with self.subTest(price=price_conflict, score=score_conflict, existing=existing):
                internal = copy.deepcopy(load_internal())
                internal['conflict_flags'] = list(existing)
                if price_conflict:
                    price = copy.deepcopy(internal['prices'][0])
                    price['amount'] = 99
                    internal['prices'].append(price)
                if score_conflict:
                    score = copy.deepcopy(internal['observations'][0])
                    score['value'] = 1
                    internal['observations'].append(score)
                before = copy.deepcopy(internal)
                offer = project_to_public_dto(internal)['offers'][0]
                self.assertEqual(internal, before, 'projection must not mutate input')
                with self.subTest(check='price'):
                    self.assertEqual(offer['price'], null_price if price_conflict
                                     else expected_dto()['offers'][0]['price'])
                with self.subTest(check='score'):
                    self.assertEqual(offer['observations_summary']['geekbench6_single'],
                                     None if score_conflict else 1420)
                flags = list(existing)
                if price_conflict:
                    flags.append('price: 2 values')
                if score_conflict:
                    flags.append('geekbench6_single: 2 values')
                with self.subTest(check='flags'):
                    self.assertIsInstance(offer['conflict_flags'], list)
                    self.assertCountEqual(offer['conflict_flags'], flags)

    def test_identical_public_values_are_not_conflicts(self):
        for kind in ('prices', 'observations', 'both'):
            with self.subTest(duplicates=kind):
                internal = copy.deepcopy(load_internal())
                for collection in ('prices', 'observations'):
                    if kind in (collection, 'both'):
                        duplicate = copy.deepcopy(internal[collection][0])
                        # Private metadata differences do not change public values.
                        duplicate['evidence'] = {'quote': 'duplicate synthetic source'}
                        internal[collection].append(duplicate)
                before = copy.deepcopy(internal)
                self.assertEqual(project_to_public_dto(internal), expected_dto())
                self.assertEqual(internal, before)

    def test_conflict_counts_distinct_values_rather_than_records(self):
        internal = copy.deepcopy(load_internal())
        for collection, field, value in (('prices', 'amount', 99),
                                         ('observations', 'value', 1)):
            changed = copy.deepcopy(internal[collection][0])
            changed[field] = value
            internal[collection].extend([changed, copy.deepcopy(changed),
                                         copy.deepcopy(internal[collection][0])])
        before = copy.deepcopy(internal)
        offer = project_to_public_dto(internal)['offers'][0]
        self.assertEqual(internal, before)
        self.assertCountEqual(offer['conflict_flags'],
                              ['price: 2 values', 'geekbench6_single: 2 values'])

    def test_conflicts_are_scoped_to_plan_id(self):
        internal = copy.deepcopy(load_internal())
        other_plan = copy.deepcopy(internal['plans'][0])
        other_plan['plan_id'] = 'synthetic-other-plan'
        internal['plans'].append(other_plan)
        for amount, score in ((20, 2000), (30, 3000)):
            price = copy.deepcopy(internal['prices'][0])
            price.update(plan_id='synthetic-other-plan', amount=amount)
            internal['prices'].append(price)
            observation = copy.deepcopy(internal['observations'][0])
            observation.update(plan_id='synthetic-other-plan', value=score)
            internal['observations'].append(observation)
        before = copy.deepcopy(internal)
        offers = project_to_public_dto(internal)['offers']
        self.assertEqual(internal, before)
        self.assertEqual(offers[0], expected_dto()['offers'][0])
        with self.subTest(check='other_price'):
            self.assertEqual(offers[1]['price'], {
                'amount': None, 'currency': None, 'billing_period_months': None,
                'term_role': None, 'monthly_equivalent': None, 'price_status': None})
        with self.subTest(check='other_score'):
            self.assertIsNone(offers[1]['observations_summary']['geekbench6_single'])
        with self.subTest(check='other_flags'):
            self.assertCountEqual(offers[1]['conflict_flags'],
                                  ['price: 2 values', 'geekbench6_single: 2 values'])


class PublicDTOWhitelistNegativeTests(unittest.TestCase):
    def test_whitelist_rejects_injected_evidence_image_url_field_and_unknown_then_passes_when_removed(self):
        for key, value in (
            ('evidence', {'quote': '2核'}),
            ('original_image_url', 'https://cdn.synthetic.example/original/fx001-hero.png'),
            ('unexpected_extra', 'nope'),
        ):
            with self.subTest(injection=key):
                dto = expected_dto()
                dto['offers'][0][key] = value
                with self.assertRaisesRegex(ValueError, r'\S', msg=f'{key} injection must be rejected'):
                    validate_public_dto(dto)
                del dto['offers'][0][key]
                self.assertEqual(dto, expected_dto())
                self.assertIsNone(validate_public_dto(dto), f'{key} removal must restore valid DTO')
