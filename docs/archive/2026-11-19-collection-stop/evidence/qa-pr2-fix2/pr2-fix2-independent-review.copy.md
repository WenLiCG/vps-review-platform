---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 2 fix2 独立只读复验

仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/2`，分支 `s1-public-dto-v1`。

本文件只给质量结论。没有推送，没有改 PR，没有评论。

## 结论

**fail**

D5、D2、D4 的指定行为在合成数据上成立，diff 只有两个文件，两遍全量都是 `Ran 306 tests` / `OK`。失败点是变异 (iv)：去掉“替换失败时把备份改回去”之后，全量测试仍然 `OK`，这条回滚没有被测试抓住。

| 项 | 状态 |
| --- | --- |
| 实时 head 仍是 `d8c41af4` | passed |
| 1. diff 只有两个文件 | passed |
| 2. D5 失败不发布、成功权限正确 | passed |
| 3. 替换失败回滚与 umask 恢复 | passed |
| 4. D2 非普通标记在写入前拒绝 | passed |
| 5. D4 普通文件与符号链接 `--out` | passed |
| 6. 全量两遍 306 OK | passed |
| 7. 六次变异 | failed（(iv) missed） |
| 8. PR 描述中的残留风险 | passed |
| D1、D3 | skipped（本轮不重测） |

## 环境与检出

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`，`/usr/bin/python3`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`

开始前：

```text
git ls-remote https://github.com/WenLiCG/vps-review-platform.git refs/heads/s1-public-dto-v1 refs/heads/main
f7b35842c94d2ab77e3d2bd23f559cafc8b41929	refs/heads/main
d8c41af4301e53304faad44df062435b0021666b	refs/heads/s1-public-dto-v1
```

GitHub pull request 的 head SHA 也是 `d8c41af4301e53304faad44df062435b0021666b`。没有 blocked。

全量用独立目录，不用上一轮检出，也不用交付包：

```text
git clone --local /workspace /tmp/pr2-fix2/head
git -C /tmp/pr2-fix2/head checkout --detach d8c41af4301e53304faad44df062435b0021666b
git -C /tmp/pr2-fix2/head rev-parse HEAD
git -C /tmp/pr2-fix2/head rev-parse 'HEAD^{tree}'
```

| 项 | SHA |
| --- | --- |
| head | `d8c41af4301e53304faad44df062435b0021666b` |
| head tree | `0ba3198adc74019372cbff6667246e1beb6e7e9b`（与声称一致） |
| 上一 head | `de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57` |
| 上一 head tree | `233142911a7fae5ea92331aa6d37317a8400188e` |
| base main | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` |

探针和全量之后 `git status --porcelain` 仍为空。

探针第一次把 FIFO 标记当普通文件去读，进程停在读端。这是探针自己的问题，已杀掉，没有当成产品失败。修正为不对 FIFO 做 `read` 之后重跑，下面的摘录来自这次重跑。产品测试没有另行失败重试。

## 1. diff `de9ea46a..d8c41af4`

状态：**passed**。

```text
M	tests/test_public_dto_pages.py
M	vps_pipeline/public_dto.py
```

`2 files changed, 219 insertions(+), 50 deletions(-)`。diff sha256 `2572672fe845c709991ed941ca7240f2b1a6606e7ee770464370235891238c3e`。

```diff
diff --git a/tests/test_public_dto_pages.py b/tests/test_public_dto_pages.py
index 11fce0d..1f706b0 100644
--- a/tests/test_public_dto_pages.py
+++ b/tests/test_public_dto_pages.py
@@ -5,6 +5,7 @@ n-gram/子串扫描会有误报漏报，不能当作完整证明。
 import html
 from html.parser import HTMLParser
 import json
+import os
 from pathlib import Path
 import re
 import subprocess
@@ -62,6 +63,18 @@ class PublicDTOPagesTests(unittest.TestCase):
     def build(self, internal=None):
         build_public_site(load_internal() if internal is None else internal, self.out)
 
+    def test_new_output_directory_permissions_respect_umask(self):
+        known_umask = 0o022
+        self.assertFalse(self.out.exists())
+        previous_umask = os.umask(known_umask)
+        try:
+            self.build()
+            self.assertEqual(self.out.stat().st_mode & 0o777,
+                             0o777 & ~known_umask,
+                             'published output must use normal mkdir permissions')
+        finally:
+            os.umask(previous_umask)
+
     def test_list_prerenders_offer_and_detail_link_with_filter_shell(self):
         self.build()
         source = (self.out / 'index.html').read_text(encoding='utf-8')
@@ -189,10 +202,21 @@ class PublicDTONegativePagesTests(unittest.TestCase):
         from unittest.mock import patch
         from vps_pipeline import public_dto
 
+        siblings_before = set(self.out.parent.iterdir())
+        self.assertFalse(self.out.exists())
+
         def reject_completed_output(path):
-            self.assertEqual(Path(path).resolve(), self.out.resolve())
-            for relative in ('data.json', 'index.html', 'offers/FX-001.html', 'style.css'):
-                self.assertTrue((Path(path) / relative).is_file(), relative + ' must exist before scan')
+            scanned = Path(path).resolve()
+            for relative in ('data.json', 'index.html', 'offers/FX-001.html',
+                             'style.css', '.public-dto-build'):
+                with self.subTest(completed_file=relative):
+                    self.assertTrue((scanned / relative).is_file(), relative + ' must exist before scan')
+            with self.subTest(check='scan_uses_temporary_directory'):
+                self.assertNotEqual(scanned, self.out.resolve(),
+                                    'scan must gate a temporary site before publishing to --out')
+            with self.subTest(check='temporary_directory_is_sibling'):
+                self.assertEqual(scanned.parent, self.out.parent.resolve())
+                self.assertTrue(scanned.is_dir())
             raise ValueError('synthetic build gate rejection')
 
         with patch.object(public_dto, 'scan_public_output', side_effect=reject_completed_output) as scan:
@@ -200,6 +224,109 @@ class PublicDTONegativePagesTests(unittest.TestCase):
                                         msg='build must propagate production scan rejection'):
                 public_dto.build_public_site(load_internal(), self.out)
             scan.assert_called_once()
+        with self.subTest(check='unpublished_output'):
+            self.assertFalse(self.out.exists(), 'scan rejection must not publish --out')
+        with self.subTest(check='no_temporary_or_backup_residue'):
+            self.assertEqual(set(self.out.parent.iterdir()), siblings_before,
+                             'scan rejection must leave no temporary or backup entries')
+
+    def output_file_snapshot(self):
+        return {path.relative_to(self.out).as_posix(): path.read_bytes()
+                for path in self.out.rglob('*') if path.is_file()}
+
+    def assert_failed_build_preserves_parent(self, siblings_before):
+        self.assertEqual(set(self.out.parent.iterdir()), siblings_before,
+                         'failed build must leave no temporary or backup entries in out.parent')
+
+    def run_contaminated_build_cli(self, input_path):
+        return subprocess.run(
+            [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', 'build',
+             '--input', str(input_path), '--out', str(self.out)],
+            cwd=ROOT, capture_output=True, text=True, timeout=30,
+        )
+
+    def test_build_image_url_rejection_leaves_new_output_absent(self):
+        internal = load_internal()
+        internal['summary']['text'] = 'https://cdn.synthetic.example/original/fx001-hero.png'
+        siblings_before = set(self.out.parent.iterdir())
+        self.assertFalse(self.out.exists())
+        with self.assertRaisesRegex(ValueError, r'(?i)(forbidden|image|url|原图|图片)'):
+            build_public_site(internal, self.out)
+        with self.subTest(check='output_absent'):
+            self.assertFalse(self.out.exists(), 'rejected image URL must not create --out')
+        with self.subTest(check='no_temporary_or_backup_residue'):
+            self.assert_failed_build_preserves_parent(siblings_before)
+
+    def test_build_image_url_rejection_removes_new_parent_directories(self):
+        root = self.out.parent
+        out = root / 'a' / 'b' / 'site'
+        internal = load_internal()
+        internal['summary']['text'] = 'https://cdn.synthetic.example/original/fx001-hero.png'
+        self.assertTrue(root.is_dir())
+        self.assertFalse((root / 'a').exists())
+        self.assertFalse((root / 'a' / 'b').exists())
+        children_before = set(root.iterdir())
+
+        with self.assertRaisesRegex(ValueError, r'(?i)(forbidden|image|url|原图|图片)'):
+            build_public_site(internal, out)
+
+        with self.subTest(check='new_parents_removed'):
+            self.assertFalse((root / 'a').exists(),
+                             'scan rejection must remove parents created by this build')
+        with self.subTest(check='existing_root_preserved_without_residue'):
+            self.assertTrue(root.is_dir(), 'existing temporary root must survive rejection')
+            self.assertEqual(set(root.iterdir()), children_before,
+                             'scan rejection must leave no new entries in existing root')
+
+    def test_cli_build_image_url_rejection_leaves_new_output_absent(self):
+        internal = load_internal()
+        internal['summary']['text'] = 'https://cdn.synthetic.example/original/fx001-hero.png'
+        input_path = self.out.parent / 'contaminated-input.json'
+        input_path.write_text(json.dumps(internal, ensure_ascii=False), encoding='utf-8')
+        siblings_before = set(self.out.parent.iterdir())
+        self.assertFalse(self.out.exists())
+        result = self.run_contaminated_build_cli(input_path)
+        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
+        self.assertRegex(result.stdout + result.stderr, r'(?i)(forbidden|image|url|原图|图片)')
+        with self.subTest(check='output_absent'):
+            self.assertFalse(self.out.exists(), 'CLI image URL rejection must not create --out')
+        with self.subTest(check='no_temporary_or_backup_residue'):
+            self.assert_failed_build_preserves_parent(siblings_before)
+
+    def test_build_nul_rejection_preserves_existing_output_bytes(self):
+        build_public_site(load_internal(), self.out)
+        before = self.output_file_snapshot()
+        self.assertIn('.public-dto-build', before)
+        siblings_before = set(self.out.parent.iterdir())
+        internal = load_internal()
+        internal['summary']['text'] = 'synthetic public summary\x00must be rejected'
+        with self.assertRaisesRegex(ValueError, r'(?i)(forbidden|nul)'):
+            build_public_site(internal, self.out)
+        with self.subTest(check='existing_site_byte_identical'):
+            self.assertTrue(self.out.is_dir())
+            self.assertEqual(self.output_file_snapshot(), before,
+                             'NUL rejection must preserve every existing file and its bytes')
+        with self.subTest(check='no_temporary_or_backup_residue'):
+            self.assert_failed_build_preserves_parent(siblings_before)
+
+    def test_cli_build_nul_rejection_preserves_existing_output_bytes(self):
+        build_public_site(load_internal(), self.out)
+        before = self.output_file_snapshot()
+        self.assertIn('.public-dto-build', before)
+        internal = load_internal()
+        internal['summary']['text'] = 'synthetic public summary\x00must be rejected'
+        input_path = self.out.parent / 'contaminated-input.json'
+        input_path.write_text(json.dumps(internal, ensure_ascii=False), encoding='utf-8')
+        siblings_before = set(self.out.parent.iterdir())
+        result = self.run_contaminated_build_cli(input_path)
+        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
+        self.assertRegex(result.stdout + result.stderr, r'(?i)(forbidden|nul)')
+        with self.subTest(check='existing_site_byte_identical'):
+            self.assertTrue(self.out.is_dir())
+            self.assertEqual(self.output_file_snapshot(), before,
+                             'CLI NUL rejection must preserve every existing file and its bytes')
+        with self.subTest(check='no_temporary_or_backup_residue'):
+            self.assert_failed_build_preserves_parent(siblings_before)
 
     def test_leak_scan_cli_fails_on_injected_evidence_then_passes_on_clean_output(self):
         build_public_site(load_internal(), self.out)
diff --git a/vps_pipeline/public_dto.py b/vps_pipeline/public_dto.py
index af0a2d5..d357dd7 100644
--- a/vps_pipeline/public_dto.py
+++ b/vps_pipeline/public_dto.py
@@ -7,10 +7,12 @@ from copy import deepcopy
 from html import escape, unescape
 import json
 import math
+import os
 from pathlib import Path
 import re
 import shutil
 import stat
+import tempfile
 from urllib.parse import urlsplit
 
 ROOT = Path(__file__).resolve().parents[1]
@@ -249,54 +251,94 @@ def build_public_site(internal_record: dict, out_dir: str | Path) -> None:
     if out.exists() and any(out.iterdir()) and marker_mode is None:
         raise ValueError('output directory is not a public-dto build output; '
                          'refusing to delete existing files')
-    out.mkdir(parents=True, exist_ok=True)
-    for child in out.iterdir():
-        if child.is_dir() and not child.is_symlink():
-            shutil.rmtree(child)
+    target = out
+    out = None
+    created_parents = []
+    published = False
+    try:
+        missing_parents = []
+        parent = target.parent
+        while not parent.exists():
+            missing_parents.append(parent)
+            parent = parent.parent
+        for parent in reversed(missing_parents):
+            try:
+                parent.mkdir()
+            except FileExistsError:
+                if not parent.is_dir():
+                    raise
+            else:
+                created_parents.append(parent)
+        out = Path(tempfile.mkdtemp(dir=target.parent, prefix=f'.{target.name}-build-'))
+        current_umask = os.umask(0)
+        os.umask(current_umask)
+        out.chmod(0o777 & ~current_umask)
+        (out / 'offers').mkdir()
+        cards = []
+        for offer in offers:
+            t = lambda key: _text(offer[key])
+            name = f'{offer["offer_id"]} · {offer["vendor_raw"]} · {offer["plan_label"]}'
+            cards.append(
+                f'<article class="result-card"><h2><a href="offers/{t("offer_id")}.html">'
+                f'{_text(name)}</a></h2><p>{t("vcpu")} vCPU · {t("memory_mb")} MB · '
+                f'{t("disk_total_value")} {t("disk_total_unit")} {t("disk_type")}</p>'
+                f'<p>{_text(offer["price"]["amount"])} {_text(offer["price"]["currency"])}</p>'
+                f'<p>{t("summary_text")}</p></article>')
+            labels = {
+                'offer_id': '样例标识', 'post_id': '帖子编号', 'vendor_raw': '商家',
+                'plan_label': '套餐', 'vcpu': 'vCPU', 'memory_mb': '内存 MB',
+                'disk_total_value': '磁盘容量', 'disk_total_unit': '磁盘单位',
+                'disk_type': '磁盘类型', 'traffic_value': '流量', 'traffic_unit': '流量单位',
+                'port_speed_mbps': '端口 Mbps', 'published_date': '发布日期',
+                'published_tz': '发布时区', 'review_date': '测评日期',
+                'review_date_precision': '日期精度', 'tested_at_beijing': '测试时间（北京）',
+                'limited_claim': '有限结论', 'aff_url': '推广链接',
+            }
+            body = '<a href="../index.html">返回列表</a>'
+            body += f'<article class="result-card detail-content"><h1>{_text(name)}</h1>'
+            body += _rows((label, offer[key]) for key, label in labels.items())
+            body += '<h2>地点</h2>' + _rows(offer['location'].items())
+            body += '<h2>价格快照</h2>' + _rows(offer['price'].items())
+            body += '<h2>观测摘要</h2>' + _rows(offer['observations_summary'].items())
+            body += '<h2>冲突标记</h2>' + _text(', '.join(offer['conflict_flags'] or []) or None)
+            body += f'<h2>简评</h2><p>{t("summary_text")}</p><h2>原帖</h2>'
+            body += _source_link(offer['canonical_url']) + '</article>'
+            (out / 'offers' / f'{offer["offer_id"]}.html').write_text(
+                _page(name, body, '../style.css'), encoding='utf-8')
+        body = ('<div class="page-heading"><h1>套餐筛选</h1></div>'
+                '<section class="searchbar"><label class="search">搜索套餐'
+                '<input type="search" placeholder="商家、套餐或编号" aria-label="搜索套餐">'
+                '</label></section><p>筛选界面预览 · 当前展示全部合成样例</p>'
+                '<section class="results" aria-label="套餐列表">' + ''.join(cards) + '</section>')
+        (out / 'index.html').write_text(_page('套餐筛选 · 合成样例', body), encoding='utf-8')
+        (out / 'data.json').write_text(json.dumps(dto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
+        shutil.copyfile(ROOT / 'website/dist/style.css', out / 'style.css')
+        (out / '.public-dto-build').write_text('public-dto/v1 build output\n', encoding='utf-8')
+        scan_public_output(out)
+        if target.exists():
+            backup = Path(tempfile.mkdtemp(dir=target.parent,
+                                           prefix=f'.{target.name}-backup-'))
+            backup.rmdir()
+            os.rename(target, backup)
+            try:
+                os.rename(out, target)
+                published = True
+            except BaseException:
+                os.rename(backup, target)
+                raise
+            shutil.rmtree(backup)
         else:
-            child.unlink()
-    (out / 'offers').mkdir()
-    cards = []
-    for offer in offers:
-        t = lambda key: _text(offer[key])
-        name = f'{offer["offer_id"]} · {offer["vendor_raw"]} · {offer["plan_label"]}'
-        cards.append(
-            f'<article class="result-card"><h2><a href="offers/{t("offer_id")}.html">'
-            f'{_text(name)}</a></h2><p>{t("vcpu")} vCPU · {t("memory_mb")} MB · '
-            f'{t("disk_total_value")} {t("disk_total_unit")} {t("disk_type")}</p>'
-            f'<p>{_text(offer["price"]["amount"])} {_text(offer["price"]["currency"])}</p>'
-            f'<p>{t("summary_text")}</p></article>')
-        labels = {
-            'offer_id': '样例标识', 'post_id': '帖子编号', 'vendor_raw': '商家',
-            'plan_label': '套餐', 'vcpu': 'vCPU', 'memory_mb': '内存 MB',
-            'disk_total_value': '磁盘容量', 'disk_total_unit': '磁盘单位',
-            'disk_type': '磁盘类型', 'traffic_value': '流量', 'traffic_unit': '流量单位',
-            'port_speed_mbps': '端口 Mbps', 'published_date': '发布日期',
-            'published_tz': '发布时区', 'review_date': '测评日期',
-            'review_date_precision': '日期精度', 'tested_at_beijing': '测试时间（北京）',
-            'limited_claim': '有限结论', 'aff_url': '推广链接',
-        }
-        body = '<a href="../index.html">返回列表</a>'
-        body += f'<article class="result-card detail-content"><h1>{_text(name)}</h1>'
-        body += _rows((label, offer[key]) for key, label in labels.items())
-        body += '<h2>地点</h2>' + _rows(offer['location'].items())
-        body += '<h2>价格快照</h2>' + _rows(offer['price'].items())
-        body += '<h2>观测摘要</h2>' + _rows(offer['observations_summary'].items())
-        body += '<h2>冲突标记</h2>' + _text(', '.join(offer['conflict_flags'] or []) or None)
-        body += f'<h2>简评</h2><p>{t("summary_text")}</p><h2>原帖</h2>'
-        body += _source_link(offer['canonical_url']) + '</article>'
-        (out / 'offers' / f'{offer["offer_id"]}.html').write_text(
-            _page(name, body, '../style.css'), encoding='utf-8')
-    body = ('<div class="page-heading"><h1>套餐筛选</h1></div>'
-            '<section class="searchbar"><label class="search">搜索套餐'
-            '<input type="search" placeholder="商家、套餐或编号" aria-label="搜索套餐">'
-            '</label></section><p>筛选界面预览 · 当前展示全部合成样例</p>'
-            '<section class="results" aria-label="套餐列表">' + ''.join(cards) + '</section>')
-    (out / 'index.html').write_text(_page('套餐筛选 · 合成样例', body), encoding='utf-8')
-    (out / 'data.json').write_text(json.dumps(dto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
-    shutil.copyfile(ROOT / 'website/dist/style.css', out / 'style.css')
-    (out / '.public-dto-build').write_text('public-dto/v1 build output\n', encoding='utf-8')
-    scan_public_output(out)
+            os.rename(out, target)
+            published = True
+    finally:
+        if out is not None and out.exists():
+            shutil.rmtree(out)
+        if not published:
+            for parent in reversed(created_parents):
+                try:
+                    parent.rmdir()
+                except OSError:
+                    break
 
 
 def main():
```

## 2. D5

状态：**passed**。构建先在 `--out` 同级写临时目录并扫描，通过之后才 `rename`。扫描失败删掉临时目录；本次新建且为空的父目录也会删掉。位置：`/tmp/pr2-fix2/head/vps_pipeline/public_dto.py` 第 254–341 行。

探针 `/tmp/pr2-fix2/probes.py`，日志 sha256 `a49d5899ad5b501ace1d7f10738640fcbfe1f9916b6260509c6d2b2eb7f86f9b`。合成图片 URL 与摘要中的 NUL 各跑 (a)(b)(c)。命令形态是 `python3 -m vps_pipeline.public_dto build --input <合成 json> --out <目录>`。

```text
D5 image a exit=1 out_exists=False residue=[] visible=absent umask_same=True
D5 image b good_exit=0 fail_exit=1 bytes_mode_mtime_same=True residue=[] visible=visible=False schema-accepts
D5 image c exit=1 missing_exists=False nested_exists=False siblings_same=True visible=absent
D5 nul a exit=1 out_exists=False residue=[] visible=absent
D5 nul b fail_exit=1 bytes_mode_mtime_same=True residue=[] visible=visible=False schema-accepts
D5 nul c exit=1 missing_exists=False nested_exists=False siblings_same=True visible=absent
```

(a) 不新建 `--out`。(c) 不留下新建的父目录。(b) 旧目录每个文件的 sha256、mode、mtime 与失败前一致，没有新增文件，同级没有 `*-build-*` 或 `*-backup-*`。(b) 上 `validate_public_dto` 接受的是原来的合格 `data.json`，里面没有这次被拒的图片 URL 或 NUL 摘要。被拒内容只出现在错误信息里的临时目录路径，那个临时目录随后不存在。

成功路径，进程 umask 先设为 `0o022`：

```text
SUCCESS a exit=0 mode=0o755 expected=0o755 not_0700=True residue=[] umask_same=True matches_clean=True
SUCCESS b exit=0 mode=0o755 expected=0o755 not_0700=True residue=[] umask_same=True matches_previous_bytes=True
UMASK_AFTER 0o22
```

(a)(b) 都成功，文件内容与另一次干净构建一致，没有临时或备份目录。`--out` 是 `0o755`，也就是 `0o777 & ~0o022`，不是 `0o700`。

## 3. 替换窗口与失败回滚

状态：**passed**。源码在第 273–275 行执行 `os.umask(0)` 后立刻把原值写回去，再用读到的 umask 做 `chmod`。成功构建和扫描失败之后，进程的 `os.umask` 都与构建前相同。

模拟“临时目录 rename 成 `--out`”失败：

```text
RENAME_FAIL OSError: simulated publish rename failure
RENAME_FAIL bytes_same=True mode_mtime_same=True residue=[] umask_same=True out_exists=True
```

旧目录逐字节还在，mode 与 mtime 不变，备份没有留下。

模拟删除备份失败时的实际行为：

```text
BACKUP_DELETE OSError: simulated backup delete failure
BACKUP_DELETE out_exists=True residue=['.site-backup-8t0gdbqx'] umask_same=True out_has_index=True
BACKUP_DELETE siblings ['.site-backup-8t0gdbqx', 'site']
```

第二步 rename 已经成功，新站点在 `--out`，函数随后抛 `OSError`，同级备份目录留着。这是删备份失败时的实际结果，不是扫描失败路径。正常删除备份时没有这个残留。

## 4. D2

状态：**passed**。标记的 `lstat` 判断仍在创建临时目录和 `rename` 之前。四种标记都没有调用 `mkdtemp` 或 `rename`。

```text
D2 symlink_file ValueError: output build marker must be a regular file
D2 symlink_file mkdtemp=0 rename=0 snap_same=True residue=[] marker_link=True external_same=True precious=True
D2 symlink_dir mkdtemp=0 rename=0 snap_same=True inside_same=True
D2 directory mkdtemp=0 rename=0 snap_same=True marker_dir=True nested=True
D2 fifo mkdtemp=0 rename=0 snap_same=True fifo=True
```

用户文件、标记、链接目标的 sha256、mode、mtime 在拒绝前后一致，没有临时目录。

## 5. D4

状态：**passed**。

```text
D4 file exit=1 nde=False tail=ValueError: output is not a directory; refusing to overwrite bytes_same=True residue=[]
D4 symlink exit=1 nde=False tail=ValueError: output path must not contain a symlink link_remains=True precious_same=True index=False residue=[]
```

普通文件含 `\x00\xff`，字节不变，CLI 不是 `NotADirectoryError`。`--out` 为符号链接时仍在写文件之前拒绝，目标里没有 `index.html`。

## 6. 全量

状态：**passed**。与声称的 306 OK 一致。目录 `/tmp/pr2-fix2/head`。

```text
python3 -m unittest discover -s tests
```

| 遍 | 外层秒 | 退出码 | sha256 |
| --- | --- | --- | --- |
| 1 | 6.046343 | 0 | `13d9cab832b353c8f897ec4fd58f56f9fdc987823214c374f4c425e5a36daf75` |
| 2 | 7.019918 | 0 | `f807a484d7b489a10947bf8d89d7307dce2bb435e3fafc2f244f9307239dcf17` |

耗时换成常量后，两遍 sha256 都是 `84826fc336f7d277c39e1670067b8e15bc0a529683cc96e08d0f59449e37e5d7`。跑完 tree 仍是 `0ba3198adc74019372cbff6667246e1beb6e7e9b`。

第 1 遍完整输出：

```text
..................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 306 tests in 5.816s

OK
```

第 2 遍完整输出：

```text
..................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 306 tests in 6.885s

OK
```

## 7. 变异

状态：**failed**。(iv) missed，其余 captured。每个副本从 `/tmp/pr2-fix2/head` 复制，只改 `vps_pipeline/public_dto.py`，跑 `python3 -m unittest discover -s tests`，然后删除。没有提交。除 (iv) 外都是一次失败，没有重试。

| 变异 | 结果 | 退出码 | 外层秒 | 汇总 | sha256 |
| --- | --- | --- | --- | --- | --- |
| (i) 恢复原地写入后再扫描 | captured | 1 | 5.875004 | `Ran 306 tests in 5.745s` / `FAILED (failures=11)` | `97e4ebc7c2783f63c1a54ec760932188f7ee9cfb9c85971fa9d3f3e4bbbca064` |
| (ii) 扫描失败不删临时目录 | captured | 1 | 5.699025 | `Ran 306 tests in 5.571s` / `FAILED (failures=7)` | `500594fea640556691e218a645b0b58e29daf1fe6783a5df9fa885dab630333b` |
| (iii) 去掉 chmod | captured | 1 | 5.828720 | `Ran 306 tests in 5.701s` / `FAILED (failures=1)` | `2ce37bd90c1a16cfe4110543fb77eaf1c6ef4754ceb87d4893f9cc15dd524b34` |
| (iv) 替换失败不还原备份 | missed | 0 | 6.399624 | `Ran 306 tests in 6.271s` / `OK` | `60527c0117ad24a71c316d44f38df2a60d8cdbc2d4fe943327693307ccfe9d25` |
| (v) 去掉父目录清理 | captured | 1 | 6.541159 | `Ran 306 tests in 6.394s` / `FAILED (failures=2)` | `181e373d35d636e2ebce1c8450e86b5378bfb5dc0319b1b9f534ff628d432293` |
| (vi) D2 的 `lstat` 改回 `is_file` | captured | 1 | 6.234469 | `Ran 306 tests in 6.086s` / `FAILED (failures=12)` | `ff3c413071fa77104ee260cfdde63aac818e3194b59c1b4dddca09ef022b40e0` |

(i)(ii) 失败测试包括 `test_build_image_url_rejection_leaves_new_output_absent`、`test_build_nul_rejection_preserves_existing_output_bytes`、`test_build_calls_production_leak_scan_on_completed_output` 以及对应 CLI。(iii) 只有 `test_new_output_directory_permissions_respect_umask`：`AssertionError: 448 != 493`，也就是 `0o700 != 0o755`。(v) 失败的是 `test_build_image_url_rejection_removes_new_parent_directories`。(vi) 失败的是 `test_build_refuses_nonregular_marker_without_deleting_existing_files` 和 `test_cli_build_refuses_symlink_marker_and_preserves_user_files`。

(iv) 没有失败测试。现有套件没有模拟第二步 `os.rename` 失败，所以拿掉 `os.rename(backup, target)` 之后仍是 306 OK。手工 mock 能证明当前实现会还原，但回归网抓不住把这段删掉。

## 8. PR 描述

状态：**passed**。fix2 一节写了这四件事：

- TOCTOU：标记检查和随后的备份/替换之间仍有竞态，本轮不修。正文里还有上一轮的 “residual risk — TOCTOU between marker check and delete is not fixed”。
- 替换窗口：旧 `--out` 已改名为备份、新目录还没改到位时，`--out` 暂时不存在。
- 跨文件系统：`os.rename` 仍可能 `EXDEV`，不回退为复制。
- umask：`chmod` 为 `0o777 & ~当前 umask`，不再是 `0700`；“读取 umask 后立即恢复原值”。源码的读法是 `os.umask(0)` 然后立刻写回原值。描述没有把临时值写成“置 0”这几个字，但写了读取后立即恢复。

## 新缺陷

没有新的产品行为缺陷达到本轮 D5/D2/D4 的失败线。删备份失败时的残留和异常是第 3 节记录的实际行为：新目录已经换上，调用方仍收到 `OSError`，备份目录留在同级。正常路径会删掉备份。

测试缺口：变异 (iv) missed。严重度按回归网缺口记，不单列成运行时数据损坏；当前未变异的代码在 mock 下会把备份改回。

## 未覆盖

- D1、D3 本轮 skipped。
- 真正的跨文件系统 `EXDEV` 没有在两块盘上重放，只核对了描述和“第二步 rename 失败会还原”的 mock。
- 并发 TOCTOU 没有做。
- 替换窗口中间 `--out` 不存在的那几毫秒没有用并发读者去撞。
- 子目录和普通文件的权限没有逐个要求；只核对了 `--out` 目录本身是 `0o755`。
