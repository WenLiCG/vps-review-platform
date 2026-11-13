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


class PublicDTONegativePagesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name) / 'site'

    def test_leak_scan_fails_on_injected_evidence_field_and_original_image_url_then_passes_when_removed(self):
        from vps_pipeline.public_dto import scan_public_output

        build_public_site(load_internal(), self.out)
        image_url = 'https://cdn.synthetic.example/original/fx001-hero.png'
        for injection, relative in (
            ('evidence', 'data.json'),
            ('original_image_url', 'data.json'),
            ('original_image_url', 'index.html'),
        ):
            path = self.out / relative
            clean = path.read_text(encoding='utf-8')
            if injection == 'evidence':
                dto = json.loads(clean)
                dto['offers'][0]['evidence'] = {'quote': '2核'}
                contaminated = json.dumps(dto, ensure_ascii=False)
                reason = r'(?i)evidence'
            elif relative.endswith('.json'):
                dto = json.loads(clean)
                # Inject content in an allowed field: scanning must inspect values.
                dto['offers'][0]['summary_text'] += ' ' + image_url
                contaminated = json.dumps(dto, ensure_ascii=False)
                reason = r'(?i)(image|url|原图|图片|fx001-hero)'
            else:
                contaminated = clean + '<img src="' + image_url + '">'
                reason = r'(?i)(image|url|原图|图片|fx001-hero)'
            for scope in ('directory', 'file'):
                target = self.out if scope == 'directory' else path
                with self.subTest(injection=injection, file=relative, scope=scope, state='injected'):
                    path.write_text(contaminated, encoding='utf-8')
                    try:
                        with self.assertRaisesRegex(ValueError, r'\S', msg=f'{injection} in {relative} must fail scan') as caught:
                            scan_public_output(target)
                        self.assertIn(relative, str(caught.exception), 'scan error must identify leaking file')
                        self.assertRegex(str(caught.exception), reason, 'scan error must explain leak reason')
                    finally:
                        path.write_text(clean, encoding='utf-8')
                with self.subTest(injection=injection, file=relative, scope=scope, state='removed'):
                    self.assertIsNone(scan_public_output(target), 'removing injection must restore clean output')

    def test_build_calls_production_leak_scan_on_completed_output(self):
        from unittest.mock import patch
        from vps_pipeline import public_dto

        def reject_completed_output(path):
            self.assertEqual(Path(path).resolve(), self.out.resolve())
            for relative in ('data.json', 'index.html', 'offers/FX-001.html', 'style.css'):
                self.assertTrue((Path(path) / relative).is_file(), relative + ' must exist before scan')
            raise ValueError('synthetic build gate rejection')

        with patch.object(public_dto, 'scan_public_output', side_effect=reject_completed_output) as scan:
            with self.assertRaisesRegex(ValueError, 'synthetic build gate rejection',
                                        msg='build must propagate production scan rejection'):
                public_dto.build_public_site(load_internal(), self.out)
            scan.assert_called_once()

    def test_leak_scan_cli_fails_on_injected_evidence_then_passes_on_clean_output(self):
        build_public_site(load_internal(), self.out)
        path = self.out / 'data.json'
        clean = path.read_text(encoding='utf-8')
        dto = json.loads(clean)
        dto['evidence'] = {'quote': '2核'}
        path.write_text(json.dumps(dto, ensure_ascii=False), encoding='utf-8')
        command = [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', 'scan', '--dir', str(self.out)]
        try:
            with self.subTest(state='injected'):
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0, 'CLI scan must reject evidence')
                self.assertIn('data.json', result.stdout + result.stderr, 'CLI scan must identify leaking file')
                self.assertIn('evidence', (result.stdout + result.stderr).lower(), 'CLI scan must explain evidence leak')
        finally:
            path.write_text(clean, encoding='utf-8')
        with self.subTest(state='removed'):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, 'clean CLI scan must succeed: ' + result.stdout + result.stderr)

    def assert_matches_fresh_build(self):
        fresh = self.out.parent / 'fresh'
        build_public_site(load_internal(), fresh)
        actual_files = {p.relative_to(self.out) for p in self.out.rglob('*') if p.is_file()}
        fresh_files = {p.relative_to(fresh) for p in fresh.rglob('*') if p.is_file()}
        self.assertEqual(actual_files, fresh_files, 'rebuild file set must match fresh build without stale files')
        for relative in sorted(fresh_files):
            with self.subTest(file=str(relative)):
                actual, expected = self.out / relative, fresh / relative
                if relative.suffix == '.css':
                    self.assertEqual(actual.read_bytes(), expected.read_bytes(), 'CSS bytes must match fresh build')
                else:
                    self.assertEqual(actual.read_text(encoding='utf-8'), expected.read_text(encoding='utf-8'),
                                     'text content must match fresh build')

    def add_stale_output(self):
        for relative in ('stale.txt', 'stale.html', 'offers/OLD.html'):
            (self.out / relative).write_text('synthetic stale output', encoding='utf-8')

    def test_build_twice_into_same_directory_succeeds_and_matches_fresh_build(self):
        build_public_site(load_internal(), self.out)
        self.add_stale_output()
        build_public_site(load_internal(), self.out)
        self.assert_matches_fresh_build()

    def test_cli_build_twice_into_same_directory_succeeds_and_matches_fresh_build(self):
        command = [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', 'build',
                   '--input', str(FIXTURE), '--out', str(self.out)]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.add_stale_output()
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 0, 'second CLI build must succeed: ' + second.stdout + second.stderr)
        self.assert_matches_fresh_build()

    # S1-SAFE PHASE 1: append-only contracts; production behavior is unchanged.
    def prepare_precious_files(self, out):
        contents = {'precious.txt': b'precious S1 SAFE unique bytes\n',
                    'keep/notes.txt': '不可删除的 S1 SAFE 笔记\n'.encode('utf-8')}
        for relative, content in contents.items():
            path = out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return contents

    def assert_precious_files_unchanged(self, out, contents):
        for relative, content in contents.items():
            with self.subTest(preserved=relative):
                self.assertTrue((out / relative).is_file(), relative + ' must survive refusal')
                self.assertEqual((out / relative).read_bytes(), content,
                                 relative + ' contents must remain unchanged')

    def run_safe_cli(self, action, out):
        command = [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', action]
        command += (['--input', str(FIXTURE), '--out', str(out)] if action == 'build'
                    else ['--dir', str(out)])
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)

    def test_build_refuses_nonempty_directory_without_marker_and_leaves_existing_files(self):
        contents = self.prepare_precious_files(self.out)
        self.assertFalse((self.out / '.public-dto-build').exists())
        with self.subTest(check='refusal'):
            with self.assertRaisesRegex(ValueError, r'(?i)(output|directory|目录).*(refus|not|拒绝|不是)',
                                        msg='unmarked nonempty output must be refused before deletion'):
                build_public_site(load_internal(), self.out)
        self.assert_precious_files_unchanged(self.out, contents)
        self.assertFalse((self.out / 'index.html').exists(), 'refusal must not write a site')

    def test_cli_build_refuses_nonempty_directory_without_marker(self):
        contents = self.prepare_precious_files(self.out)
        result = self.run_safe_cli('build', self.out)
        with self.subTest(check='exit_status'):
            self.assertNotEqual(result.returncode, 0, 'CLI build must reject unmarked nonempty output')
        self.assert_precious_files_unchanged(self.out, contents)

    def test_build_rebuilds_when_marker_present(self):
        from vps_pipeline.public_dto import scan_public_output

        build_public_site(load_internal(), self.out)
        marker = self.out / '.public-dto-build'
        with self.subTest(check='successful_build_marker'):
            self.assertTrue(marker.is_file(), 'successful build must write .public-dto-build')
            marker_content = marker.read_text(encoding='utf-8')
            self.assertTrue(marker_content.strip(), 'build marker must contain a nonempty public identifier')
            for canary in CANARIES:
                self.assertNotIn(canary, marker_content)
            for key in FORBIDDEN_KEYS:
                self.assertNotIn(key, marker_content)
            self.assertIsNone(scan_public_output(self.out), 'scan must allow the build marker')
            self.assertIsNone(scan_public_output(marker), 'scan must allow the marker file itself')
        self.add_stale_output()
        build_public_site(load_internal(), self.out)
        for relative in ('stale.txt', 'stale.html', 'offers/OLD.html'):
            self.assertFalse((self.out / relative).exists(), 'marked rebuild must remove ' + relative)
        self.assert_matches_fresh_build()
        with self.subTest(check='rebuilt_marker'):
            self.assertTrue(marker.is_file(), 'rebuild must preserve a build marker')
            self.assertEqual(marker.read_bytes(), (self.out.parent / 'fresh/.public-dto-build').read_bytes(),
                             'rebuilt and fresh marker contents must match')

    def test_build_refuses_symlink_out_and_path_containing_symlink(self):
        for case in ('out_is_symlink', 'path_contains_symlink'):
            with self.subTest(case=case):
                base = self.out.parent / case
                target = base / 'target'
                actual_out = target if case == 'out_is_symlink' else target / 'subdir'
                contents = self.prepare_precious_files(actual_out)
                link = base / 'link'
                link.symlink_to(target, target_is_directory=True)
                out = link if case == 'out_is_symlink' else link / 'subdir'
                with self.subTest(check='refusal'):
                    with self.assertRaisesRegex(ValueError, r'(?i)(symlink|symbolic|符号链接)',
                                                msg='symlink output paths must be refused'):
                        build_public_site(load_internal(), out)
                self.assertTrue(link.is_symlink(), 'refusal must preserve the symlink')
                self.assert_precious_files_unchanged(actual_out, contents)

    def assert_protected_output_refused_without_mutation(self, out):
        from contextlib import ExitStack
        from unittest.mock import patch

        # Tripwires raise AssertionError, never ValueError: attempting mutation
        # must fail this test, while keeping real repository/dist files safe.
        with ExitStack() as guards:
            for name in ('mkdir', 'unlink', 'rmdir', 'write_text', 'write_bytes', 'touch',
                         'rename', 'replace', 'symlink_to'):
                guards.enter_context(patch.object(Path, name, side_effect=AssertionError(
                    'unsafe output reached filesystem mutation before refusal: ' + name)))
            for name in ('rmtree', 'copyfile'):
                guards.enter_context(patch('vps_pipeline.public_dto.shutil.' + name,
                    side_effect=AssertionError('unsafe output reached filesystem mutation before refusal: ' + name)))
            with self.assertRaisesRegex(ValueError, r'\S', msg='protected output must be refused before mutation'):
                build_public_site(load_internal(), out)

    def test_build_refuses_repo_root_and_ancestor(self):
        key = ROOT / 'vps_pipeline/public_dto.py'
        before = key.read_bytes()
        for case, out in (('repo_root', ROOT), ('ancestor', ROOT.parent)):
            with self.subTest(case=case):
                try:
                    self.assert_protected_output_refused_without_mutation(out)
                finally:
                    self.assertTrue(key.is_file(), 'repository production module must survive refusal')
                    self.assertEqual(key.read_bytes(), before)

    def test_build_refuses_out_inside_website_dist(self):
        dist = ROOT / 'website/dist'
        before = {path.relative_to(dist): path.read_bytes()
                  for path in dist.rglob('*') if path.is_file()}
        child = dist / '__s1_safe_refusal_must_not_create__'
        self.assertFalse(child.exists(), 'dist refusal test requires a nonexistent child path')
        for case, out in (('dist', dist), ('dist_child', child)):
            with self.subTest(case=case):
                try:
                    self.assert_protected_output_refused_without_mutation(out)
                finally:
                    after = {path.relative_to(dist): path.read_bytes()
                             for path in dist.rglob('*') if path.is_file()}
                    self.assertEqual(after, before, 'all existing dist files must remain byte-identical')
                    self.assertFalse(child.exists(), 'refusal must not create a directory inside dist')

    def test_cli_build_refusal_exit_nonzero_for_unsafe_out(self):
        for case in ('unmarked_nonempty', 'symlink'):
            with self.subTest(case=case):
                target = self.out.parent / case / 'target'
                contents = self.prepare_precious_files(target)
                out = target
                if case == 'symlink':
                    out = target.parent / 'link'
                    out.symlink_to(target, target_is_directory=True)
                result = self.run_safe_cli('build', out)
                with self.subTest(check='exit_status'):
                    self.assertNotEqual(result.returncode, 0, 'CLI build must refuse unsafe output: ' + case)
                self.assert_precious_files_unchanged(target, contents)

    def safe_scan_injections(self, clean):
        for injection in ('evidence', 'image_url_value', 'unexpected_extra'):
            dto = json.loads(clean)
            offer = dto['offers'][0]
            if injection == 'evidence':
                offer['evidence'] = {'quote': '2核'}
            elif injection == 'image_url_value':
                offer['summary_text'] += ' https://cdn.synthetic.example/original/fx001-hero.png'
            else:
                offer['unexpected_extra'] = 'nope'
            yield injection, json.dumps(dto, ensure_ascii=False)

    def test_scan_rejects_injected_evidence_image_url_value_and_unknown_field_then_passes_when_removed(self):
        from vps_pipeline.public_dto import scan_public_output

        build_public_site(load_internal(), self.out)
        path = self.out / 'data.json'
        clean = path.read_text(encoding='utf-8')
        self.assertIsNone(scan_public_output(self.out))
        for injection, contaminated in self.safe_scan_injections(clean):
            for scope, target in (('directory', self.out), ('file', path)):
                with self.subTest(injection=injection, scope=scope, state='injected'):
                    path.write_text(contaminated, encoding='utf-8')
                    try:
                        with self.assertRaisesRegex(ValueError, r'\S',
                                msg=injection + ' injection must fail direct scan'):
                            scan_public_output(target)
                    finally:
                        path.write_text(clean, encoding='utf-8')
                with self.subTest(injection=injection, scope=scope, state='removed'):
                    self.assertIsNone(scan_public_output(target), injection + ' removal must restore clean scan')

    def test_cli_scan_exit_nonzero_for_each_injection_and_zero_after_removal(self):
        build_public_site(load_internal(), self.out)
        path = self.out / 'data.json'
        clean = path.read_text(encoding='utf-8')
        for injection, contaminated in self.safe_scan_injections(clean):
            with self.subTest(injection=injection, state='injected'):
                path.write_text(contaminated, encoding='utf-8')
                try:
                    result = self.run_safe_cli('scan', self.out)
                    self.assertNotEqual(result.returncode, 0, injection + ' injection must fail CLI scan')
                finally:
                    path.write_text(clean, encoding='utf-8')
            with self.subTest(injection=injection, state='removed'):
                result = self.run_safe_cli('scan', self.out)
                self.assertEqual(result.returncode, 0,
                                 injection + ' removal must restore clean CLI scan: ' + result.stdout + result.stderr)

    def test_scan_rejects_nul_and_invalid_utf8_even_without_sensitive_keys(self):
        from vps_pipeline.public_dto import scan_public_output

        build_public_site(load_internal(), self.out)
        path = self.out / 'data.json'
        clean = path.read_bytes()
        dto = json.loads(clean)
        dto['offers'][0]['evidence'] = {'quote': 'synthetic evidence'}
        evidence = json.dumps(dto, ensure_ascii=False).encode('utf-8')
        for case, contaminated in (
            ('evidence_with_nul', evidence + b'\x00'),
            ('evidence_with_invalid_utf8', evidence + b'\xff'),
            ('pure_invalid_utf8', b'\xff'),
            ('clean_json_with_invalid_utf8', clean + b'\xff'),
            ('clean_json_with_nul', clean + b'\x00'),
        ):
            for scope, target in (('directory', self.out), ('file', path)):
                with self.subTest(case=case, scope=scope):
                    path.write_bytes(contaminated)
                    try:
                        with self.assertRaises(ValueError):
                            scan_public_output(target)
                    finally:
                        path.write_bytes(clean)
        self.assertIsNone(scan_public_output(self.out))

    def test_cli_scan_rejects_evidence_with_nul(self):
        build_public_site(load_internal(), self.out)
        path = self.out / 'data.json'
        dto = json.loads(path.read_bytes())
        dto['offers'][0]['evidence'] = {'quote': 'synthetic evidence'}
        path.write_bytes(json.dumps(dto, ensure_ascii=False).encode('utf-8') + b'\x00')
        result = self.run_safe_cli('scan', self.out)
        self.assertNotEqual(result.returncode, 0, 'NUL must not hide evidence from CLI scan')

    def test_build_refuses_nonregular_marker_without_deleting_existing_files(self):
        for kind in ('symlink', 'directory'):
            with self.subTest(marker=kind):
                out = self.out.parent / kind
                contents = self.prepare_precious_files(out)
                marker = out / '.public-dto-build'
                target = self.out.parent / (kind + '-external-marker')
                target_bytes = b'public-dto/v1 build output\n'
                target.write_bytes(target_bytes)
                if kind == 'symlink':
                    marker.symlink_to(target)
                else:
                    marker.mkdir()
                with self.subTest(check='refusal'):
                    with self.assertRaises(ValueError):
                        build_public_site(load_internal(), out)
                self.assert_precious_files_unchanged(out, contents)
                with self.subTest(check='marker_preserved'):
                    if kind == 'symlink':
                        self.assertTrue(marker.is_symlink())
                        self.assertEqual(marker.readlink(), target)
                    else:
                        self.assertTrue(marker.is_dir())
                self.assertEqual(target.read_bytes(), target_bytes)
                for relative in ('index.html', 'data.json'):
                    with self.subTest(site_file=relative):
                        self.assertFalse((out / relative).exists())

    def test_cli_build_refuses_symlink_marker_and_preserves_user_files(self):
        contents = self.prepare_precious_files(self.out)
        target = self.out.parent / 'external-marker'
        target_bytes = b'public-dto/v1 build output\n'
        target.write_bytes(target_bytes)
        marker = self.out / '.public-dto-build'
        marker.symlink_to(target)
        result = self.run_safe_cli('build', self.out)
        with self.subTest(check='exit_status'):
            self.assertNotEqual(result.returncode, 0)
        self.assert_precious_files_unchanged(self.out, contents)
        with self.subTest(check='marker_preserved'):
            self.assertTrue(marker.is_symlink())
            self.assertEqual(marker.readlink(), target)
        self.assertEqual(target.read_bytes(), target_bytes)
        for relative in ('index.html', 'data.json'):
            with self.subTest(site_file=relative):
                self.assertFalse((self.out / relative).exists())

    def test_build_refuses_regular_file_out_with_explicit_value_error(self):
        content = b'precious regular file output\x00\xff\n'
        self.out.write_bytes(content)
        try:
            with self.assertRaisesRegex(ValueError,
                    r'(?i)(not a directory|regular file|普通文件|不是目录|拒绝)'):
                build_public_site(load_internal(), self.out)
        finally:
            self.assertTrue(self.out.is_file())
            self.assertEqual(self.out.read_bytes(), content)

    def test_cli_build_refuses_regular_file_out_with_explicit_message(self):
        content = b'precious regular file output\x00\xff\n'
        self.out.write_bytes(content)
        result = self.run_safe_cli('build', self.out)
        self.assertTrue(self.out.is_file())
        self.assertEqual(self.out.read_bytes(), content)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stdout + result.stderr,
                         r'(?i)(not a directory|regular file|普通文件|不是目录|拒绝)')
        self.assertNotIn('NotADirectoryError', result.stdout + result.stderr,
                         'CLI must expose an explicit refusal, not a filesystem traceback')
