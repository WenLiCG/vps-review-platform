"""Static page contracts and leak scan skeleton.

n-gram/子串扫描会有误报漏报，不能当作完整证明。
"""
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from vps_pipeline.public_dto import build_public_site, validate_public_dto
from tests.test_public_dto import CANARIES, FORBIDDEN_KEYS, FIXTURE, ROOT, expected_dto, load_internal


class VisibleBody(HTMLParser):
    """Collect body text without counting script/style data as visible facts."""
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.hidden = 0
        self.parts = []
        self.links = []
        self.search = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'body':
            self.in_body = True
        if tag in ('script', 'style'):
            self.hidden += 1
        if self.in_body and tag == 'a':
            self.links.append(attrs.get('href'))
        if self.in_body and tag == 'input' and attrs.get('type') in ('search', 'text'):
            self.search = True

    def handle_endtag(self, tag):
        if tag == 'body':
            self.in_body = False
        if tag in ('script', 'style'):
            self.hidden -= 1

    def handle_data(self, data):
        if self.in_body and not self.hidden:
            self.parts.append(data)

    @property
    def text(self):
        return ' '.join(self.parts)


class PublicDTOPagesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name) / 'site'

    def build(self, internal=None):
        build_public_site(load_internal() if internal is None else internal, self.out)

    def test_list_prerenders_offer_and_detail_link_with_filter_shell(self):
        self.build()
        source = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('lang="zh-CN"', source)
        body = VisibleBody(source)
        for fact in ('FX-001', '示例云', 'London Mini', '2', '40', 'NVMe', '10', 'USD'):
            self.assertIn(fact, body.text)
        self.assertIn('offers/FX-001.html', body.links)
        self.assertTrue(body.search, '列表页需要搜索框')

    def test_detail_prerenders_public_facts_dates_summary_and_source(self):
        self.build()
        source = (self.out / 'offers/FX-001.html').read_text(encoding='utf-8')
        self.assertIn('lang="zh-CN"', source)
        body = VisibleBody(source)
        for fact in ('FX-001', '示例云', 'London Mini', '2', '4096', '40', 'GB',
                     'NVMe', '1', 'TB', '1000', '伦敦', '10', 'USD', '1420',
                     '2025-06-04', '2025-06-03', '+08:00',
                     '2025-06-03T21:00:00+08:00', '无',
                     expected_dto()['offers'][0]['summary_text']):
            with self.subTest(fact=fact):
                self.assertIn(fact, body.text)
        self.assertIn('https://synthetic.example/post/synth-001', body.links)

    def test_build_writes_valid_exact_public_data_and_copies_stylesheet(self):
        self.build()
        data = json.loads((self.out / 'data.json').read_text(encoding='utf-8'))
        self.assertEqual(data, expected_dto())
        self.assertIsNone(validate_public_dto(data))
        self.assertEqual((self.out / 'style.css').read_bytes(),
                         (ROOT / 'website/dist/style.css').read_bytes())

    def test_cli_build_succeeds_and_produces_both_pages_and_valid_data(self):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', 'build',
             '--input', str(FIXTURE), '--out', str(self.out)],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.out / 'index.html').is_file(), 'CLI must actually build index.html')
        self.assertTrue((self.out / 'offers/FX-001.html').is_file())
        data = json.loads((self.out / 'data.json').read_text(encoding='utf-8'))
        validate_public_dto(data)
        self.assertEqual(data, expected_dto())

    def test_vendor_html_metacharacters_are_escaped_on_both_pages(self):
        internal = load_internal()
        attack = '<script>alert(1)</script>&"'
        internal['vendor_raw'] = attack
        self.build(internal)
        for relative in ('index.html', 'offers/FX-001.html'):
            with self.subTest(page=relative):
                source = (self.out / relative).read_text(encoding='utf-8')
                self.assertIn(html.escape(attack, quote=True), source)
                self.assertNotIn('<script>alert(1)</script>', source)
                self.assertIn(attack, VisibleBody(source).text)

    def test_entire_build_output_has_no_internal_canaries_or_private_json_keys(self):
        """扫描骨架：n-gram/子串扫描会有误报漏报，不能当作完整证明。"""
        self.build()
        scanned = set()
        for path in self.out.rglob('*'):
            if not path.is_file():
                continue
            try:
                source = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            scanned.add(path.relative_to(self.out).as_posix())
            with self.subTest(file=path.relative_to(self.out)):
                for marker in (*CANARIES, '971510'):
                    self.assertNotIn(marker, source)
                for key in FORBIDDEN_KEYS:
                    self.assertIsNone(re.search(r'"' + re.escape(key) + r'"\s*:', source))
        self.assertTrue({'index.html', 'offers/FX-001.html', 'data.json', 'style.css'} <= scanned)
