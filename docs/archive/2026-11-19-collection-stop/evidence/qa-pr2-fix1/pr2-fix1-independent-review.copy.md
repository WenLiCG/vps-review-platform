---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 2 fix1 独立只读复验

仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/2`，分支 `s1-public-dto-v1`。

本文件是质量结论，不是合并决定。没有推送，没有改 PR，没有评论。

## 结论

**fail**

D1、D2、D3、D4 的指定行为成立，diff 只有三个文件，两遍全量都是 `Ran 300 tests` / `OK`，六次变异都被全量测试抓住，PR 描述写了 TOCTOU 残留。失败点是扫描失败后的残留：构建或扫描退出码为 1，但页面和 `data.json` 会留在原地；对摘要中的图片 URL，以及 HTML 中带原始 NUL 而 JSON 已转义的情况，`validate_public_dto` 仍接受 `data.json`。直接按静态文件读取会得到完整页面，标记内容与成功构建相同，不能当作完成标志。

| 项 | 状态 |
| --- | --- |
| 实时 head 仍是 `de9ea46a` | passed |
| 1. diff 只有三个文件 | passed |
| 2. D1 扫描不再跳过 NUL / 非法 UTF-8 | passed |
| 3. D2 非普通标记拒绝且不删文件 | passed |
| 4. D3 冲突置 null 并写字段与条数 | passed |
| 5. D4 `--out` 为普通文件时拒绝 | passed |
| 6. 全量 discover 两遍 300 OK | passed |
| 7. 六次变异均被抓住 | passed |
| 8. PR 描述中的 TOCTOU | passed |
| B. 扫描失败残留不会被当成合格输出 | failed |

## 环境与检出

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`，`/usr/bin/python3`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`

开始前 `git ls-remote https://github.com/WenLiCG/vps-review-platform.git refs/heads/s1-public-dto-v1 refs/heads/main`：

```text
f7b35842c94d2ab77e3d2bd23f559cafc8b41929	refs/heads/main
de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57	refs/heads/s1-public-dto-v1
```

GitHub pull request 对象的 head SHA 也是 `de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57`，base 是 `f7b35842c94d2ab77e3d2bd23f559cafc8b41929`。没有 blocked。

全量回归没有复用先前的检出，也没有使用交付包。独立目录由本地仓库克隆后再分离头指针：

```text
git clone --local /workspace /tmp/pr2-fix1/head
git -C /tmp/pr2-fix1/head checkout --detach de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57
git -C /tmp/pr2-fix1/head rev-parse HEAD
git -C /tmp/pr2-fix1/head rev-parse 'HEAD^{tree}'
```

| 项 | SHA |
| --- | --- |
| head | `de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57` |
| head tree | `233142911a7fae5ea92331aa6d37317a8400188e`（与声称一致） |
| 前一个 head | `1586ebefd6450c0a38775f90e9e0f3baf6085f0e` |
| main / base | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` |
| base tree | `ffe2b7a0a0bb8bbf629d10b987aeed3668ce750d` |

`git status --porcelain` 在探针和全量测试之后仍为空。前一个 head 与 base 另有独立检出 `/tmp/pr2-fix1/prev`、`/tmp/pr2-fix1/base`，只用于对照，全量测试只在 `/tmp/pr2-fix1/head` 跑。

本轮命令一次完成，没有失败后的重试。

## 1. diff `1586ebef..de9ea46a`

状态：**passed**。`git diff --name-status` 只有三行，都是 `M`：

```text
M	tests/test_public_dto.py
M	tests/test_public_dto_pages.py
M	vps_pipeline/public_dto.py
```

`git diff --stat`：`3 files changed, 238 insertions(+), 12 deletions(-)`。diff 文件 sha256 `092f1856f0b982672dd6582fb20ef7fdf6fc7e6c03bafe09980e3ec55cc32f59`。

完整 diff：

```diff
diff --git a/tests/test_public_dto.py b/tests/test_public_dto.py
index ed61074..d499892 100644
--- a/tests/test_public_dto.py
+++ b/tests/test_public_dto.py
@@ -144,6 +144,98 @@ class PublicDTOProjectionTests(unittest.TestCase):
         self.assertEqual(dto['offers'][0]['summary_text'], '人工撰写的另一条有限简评。')
 
 
+
+    def test_distinct_prices_and_scores_are_conflicts_and_preserve_input(self):
+        null_price = {'amount': None, 'currency': None, 'billing_period_months': None,
+                      'term_role': None, 'monthly_equivalent': None, 'price_status': None}
+        for price_conflict, score_conflict, existing in (
+            (True, False, []), (False, True, []), (True, True, []),
+            (True, False, ['pre-existing']),
+        ):
+            with self.subTest(price=price_conflict, score=score_conflict, existing=existing):
+                internal = copy.deepcopy(load_internal())
+                internal['conflict_flags'] = list(existing)
+                if price_conflict:
+                    price = copy.deepcopy(internal['prices'][0])
+                    price['amount'] = 99
+                    internal['prices'].append(price)
+                if score_conflict:
+                    score = copy.deepcopy(internal['observations'][0])
+                    score['value'] = 1
+                    internal['observations'].append(score)
+                before = copy.deepcopy(internal)
+                offer = project_to_public_dto(internal)['offers'][0]
+                self.assertEqual(internal, before, 'projection must not mutate input')
+                with self.subTest(check='price'):
+                    self.assertEqual(offer['price'], null_price if price_conflict
+                                     else expected_dto()['offers'][0]['price'])
+                with self.subTest(check='score'):
+                    self.assertEqual(offer['observations_summary']['geekbench6_single'],
+                                     None if score_conflict else 1420)
+                flags = list(existing)
+                if price_conflict:
+                    flags.append('price: 2 values')
+                if score_conflict:
+                    flags.append('geekbench6_single: 2 values')
+                with self.subTest(check='flags'):
+                    self.assertIsInstance(offer['conflict_flags'], list)
+                    self.assertCountEqual(offer['conflict_flags'], flags)
+
+    def test_identical_public_values_are_not_conflicts(self):
+        for kind in ('prices', 'observations', 'both'):
+            with self.subTest(duplicates=kind):
+                internal = copy.deepcopy(load_internal())
+                for collection in ('prices', 'observations'):
+                    if kind in (collection, 'both'):
+                        duplicate = copy.deepcopy(internal[collection][0])
+                        # Private metadata differences do not change public values.
+                        duplicate['evidence'] = {'quote': 'duplicate synthetic source'}
+                        internal[collection].append(duplicate)
+                before = copy.deepcopy(internal)
+                self.assertEqual(project_to_public_dto(internal), expected_dto())
+                self.assertEqual(internal, before)
+
+    def test_conflict_counts_distinct_values_rather_than_records(self):
+        internal = copy.deepcopy(load_internal())
+        for collection, field, value in (('prices', 'amount', 99),
+                                         ('observations', 'value', 1)):
+            changed = copy.deepcopy(internal[collection][0])
+            changed[field] = value
+            internal[collection].extend([changed, copy.deepcopy(changed),
+                                         copy.deepcopy(internal[collection][0])])
+        before = copy.deepcopy(internal)
+        offer = project_to_public_dto(internal)['offers'][0]
+        self.assertEqual(internal, before)
+        self.assertCountEqual(offer['conflict_flags'],
+                              ['price: 2 values', 'geekbench6_single: 2 values'])
+
+    def test_conflicts_are_scoped_to_plan_id(self):
+        internal = copy.deepcopy(load_internal())
+        other_plan = copy.deepcopy(internal['plans'][0])
+        other_plan['plan_id'] = 'synthetic-other-plan'
+        internal['plans'].append(other_plan)
+        for amount, score in ((20, 2000), (30, 3000)):
+            price = copy.deepcopy(internal['prices'][0])
+            price.update(plan_id='synthetic-other-plan', amount=amount)
+            internal['prices'].append(price)
+            observation = copy.deepcopy(internal['observations'][0])
+            observation.update(plan_id='synthetic-other-plan', value=score)
+            internal['observations'].append(observation)
+        before = copy.deepcopy(internal)
+        offers = project_to_public_dto(internal)['offers']
+        self.assertEqual(internal, before)
+        self.assertEqual(offers[0], expected_dto()['offers'][0])
+        with self.subTest(check='other_price'):
+            self.assertEqual(offers[1]['price'], {
+                'amount': None, 'currency': None, 'billing_period_months': None,
+                'term_role': None, 'monthly_equivalent': None, 'price_status': None})
+        with self.subTest(check='other_score'):
+            self.assertIsNone(offers[1]['observations_summary']['geekbench6_single'])
+        with self.subTest(check='other_flags'):
+            self.assertCountEqual(offers[1]['conflict_flags'],
+                                  ['price: 2 values', 'geekbench6_single: 2 values'])
+
+
 class PublicDTOWhitelistNegativeTests(unittest.TestCase):
     def test_whitelist_rejects_injected_evidence_image_url_field_and_unknown_then_passes_when_removed(self):
         for key, value in (
diff --git a/tests/test_public_dto_pages.py b/tests/test_public_dto_pages.py
index 3691f48..11fce0d 100644
--- a/tests/test_public_dto_pages.py
+++ b/tests/test_public_dto_pages.py
@@ -444,3 +444,108 @@ class PublicDTONegativePagesTests(unittest.TestCase):
                 result = self.run_safe_cli('scan', self.out)
                 self.assertEqual(result.returncode, 0,
                                  injection + ' removal must restore clean CLI scan: ' + result.stdout + result.stderr)
+
+    def test_scan_rejects_nul_and_invalid_utf8_even_without_sensitive_keys(self):
+        from vps_pipeline.public_dto import scan_public_output
+
+        build_public_site(load_internal(), self.out)
+        path = self.out / 'data.json'
+        clean = path.read_bytes()
+        dto = json.loads(clean)
+        dto['offers'][0]['evidence'] = {'quote': 'synthetic evidence'}
+        evidence = json.dumps(dto, ensure_ascii=False).encode('utf-8')
+        for case, contaminated in (
+            ('evidence_with_nul', evidence + b'\x00'),
+            ('evidence_with_invalid_utf8', evidence + b'\xff'),
+            ('pure_invalid_utf8', b'\xff'),
+            ('clean_json_with_invalid_utf8', clean + b'\xff'),
+            ('clean_json_with_nul', clean + b'\x00'),
+        ):
+            for scope, target in (('directory', self.out), ('file', path)):
+                with self.subTest(case=case, scope=scope):
+                    path.write_bytes(contaminated)
+                    try:
+                        with self.assertRaises(ValueError):
+                            scan_public_output(target)
+                    finally:
+                        path.write_bytes(clean)
+        self.assertIsNone(scan_public_output(self.out))
+
+    def test_cli_scan_rejects_evidence_with_nul(self):
+        build_public_site(load_internal(), self.out)
+        path = self.out / 'data.json'
+        dto = json.loads(path.read_bytes())
+        dto['offers'][0]['evidence'] = {'quote': 'synthetic evidence'}
+        path.write_bytes(json.dumps(dto, ensure_ascii=False).encode('utf-8') + b'\x00')
+        result = self.run_safe_cli('scan', self.out)
+        self.assertNotEqual(result.returncode, 0, 'NUL must not hide evidence from CLI scan')
+
+    def test_build_refuses_nonregular_marker_without_deleting_existing_files(self):
+        for kind in ('symlink', 'directory'):
+            with self.subTest(marker=kind):
+                out = self.out.parent / kind
+                contents = self.prepare_precious_files(out)
+                marker = out / '.public-dto-build'
+                target = self.out.parent / (kind + '-external-marker')
+                target_bytes = b'public-dto/v1 build output\n'
+                target.write_bytes(target_bytes)
+                if kind == 'symlink':
+                    marker.symlink_to(target)
+                else:
+                    marker.mkdir()
+                with self.subTest(check='refusal'):
+                    with self.assertRaises(ValueError):
+                        build_public_site(load_internal(), out)
+                self.assert_precious_files_unchanged(out, contents)
+                with self.subTest(check='marker_preserved'):
+                    if kind == 'symlink':
+                        self.assertTrue(marker.is_symlink())
+                        self.assertEqual(marker.readlink(), target)
+                    else:
+                        self.assertTrue(marker.is_dir())
+                self.assertEqual(target.read_bytes(), target_bytes)
+                for relative in ('index.html', 'data.json'):
+                    with self.subTest(site_file=relative):
+                        self.assertFalse((out / relative).exists())
+
+    def test_cli_build_refuses_symlink_marker_and_preserves_user_files(self):
+        contents = self.prepare_precious_files(self.out)
+        target = self.out.parent / 'external-marker'
+        target_bytes = b'public-dto/v1 build output\n'
+        target.write_bytes(target_bytes)
+        marker = self.out / '.public-dto-build'
+        marker.symlink_to(target)
+        result = self.run_safe_cli('build', self.out)
+        with self.subTest(check='exit_status'):
+            self.assertNotEqual(result.returncode, 0)
+        self.assert_precious_files_unchanged(self.out, contents)
+        with self.subTest(check='marker_preserved'):
+            self.assertTrue(marker.is_symlink())
+            self.assertEqual(marker.readlink(), target)
+        self.assertEqual(target.read_bytes(), target_bytes)
+        for relative in ('index.html', 'data.json'):
+            with self.subTest(site_file=relative):
+                self.assertFalse((self.out / relative).exists())
+
+    def test_build_refuses_regular_file_out_with_explicit_value_error(self):
+        content = b'precious regular file output\x00\xff\n'
+        self.out.write_bytes(content)
+        try:
+            with self.assertRaisesRegex(ValueError,
+                    r'(?i)(not a directory|regular file|普通文件|不是目录|拒绝)'):
+                build_public_site(load_internal(), self.out)
+        finally:
+            self.assertTrue(self.out.is_file())
+            self.assertEqual(self.out.read_bytes(), content)
+
+    def test_cli_build_refuses_regular_file_out_with_explicit_message(self):
+        content = b'precious regular file output\x00\xff\n'
+        self.out.write_bytes(content)
+        result = self.run_safe_cli('build', self.out)
+        self.assertTrue(self.out.is_file())
+        self.assertEqual(self.out.read_bytes(), content)
+        self.assertNotEqual(result.returncode, 0)
+        self.assertRegex(result.stdout + result.stderr,
+                         r'(?i)(not a directory|regular file|普通文件|不是目录|拒绝)')
+        self.assertNotIn('NotADirectoryError', result.stdout + result.stderr,
+                         'CLI must expose an explicit refusal, not a filesystem traceback')
diff --git a/vps_pipeline/public_dto.py b/vps_pipeline/public_dto.py
index c5f3b78..af0a2d5 100644
--- a/vps_pipeline/public_dto.py
+++ b/vps_pipeline/public_dto.py
@@ -10,6 +10,7 @@ import math
 from pathlib import Path
 import re
 import shutil
+import stat
 from urllib.parse import urlsplit
 
 ROOT = Path(__file__).resolve().parents[1]
@@ -105,12 +106,15 @@ def scan_public_output(path: str | Path) -> None:
     for file in files:
         if not file.is_file():
             continue
+        raw = file.read_bytes()
+        if re.search(rb'"evidence"\s*:', raw):
+            raise ValueError(f'{file}: forbidden evidence key')
+        if b'\x00' in raw:
+            raise ValueError(f'{file}: forbidden NUL byte')
         try:
-            source = file.read_text(encoding='utf-8-sig')
-        except UnicodeDecodeError:
-            continue
-        if '\x00' in source:
-            continue
+            source = raw.decode('utf-8-sig')
+        except UnicodeDecodeError as exc:
+            raise ValueError(f'{file}: invalid UTF-8') from exc
 
         def inspect_pairs(pairs):
             for key, value in pairs:
@@ -144,11 +148,27 @@ def project_to_public_dto(internal_record: dict) -> dict:
     offers = []
     for plan in internal_record.get('plans', []):
         plan_id = plan.get('plan_id')
-        price = next((p for p in internal_record.get('prices', [])
-                      if plan_id is not None and p.get('plan_id') == plan_id), {})
-        score = next((o.get('value') for o in internal_record.get('observations', [])
-                      if plan_id is not None and o.get('plan_id') == plan_id
-                      and o.get('metric') == 'geekbench6_single'), None)
+        prices = []
+        for item in internal_record.get('prices', []):
+            if plan_id is not None and item.get('plan_id') == plan_id:
+                public_price = {key: item.get(key) for key in PRICE['properties']}
+                if public_price not in prices:
+                    prices.append(public_price)
+        scores = []
+        for item in internal_record.get('observations', []):
+            if (plan_id is not None and item.get('plan_id') == plan_id
+                    and item.get('metric') == 'geekbench6_single'):
+                if item.get('value') not in scores:
+                    scores.append(item.get('value'))
+        price = prices[0] if len(prices) == 1 else {}
+        score = scores[0] if len(scores) == 1 else None
+        flags = internal_record.get('conflict_flags')
+        for field, values in (('price', prices), ('geekbench6_single', scores)):
+            if len(values) > 1:
+                flags = list(flags or [])
+                flag = f'{field}: {len(values)} values'
+                if flag not in flags:
+                    flags.append(flag)
         summary = internal_record.get('summary') or {}
         location = plan.get('location') or {}
         offer = {
@@ -159,7 +179,7 @@ def project_to_public_dto(internal_record: dict) -> dict:
             'location': {key: location.get(key) for key in LOCATION['properties']},
             'price': {key: price.get(key) for key in PRICE['properties']},
             'observations_summary': {'geekbench6_single': score},
-            'conflict_flags': internal_record.get('conflict_flags'),
+            'conflict_flags': flags,
             'summary_text': summary.get('text'),
             'limited_claim': summary.get('limited_claim'),
         }
@@ -217,7 +237,16 @@ def build_public_site(internal_record: dict, out_dir: str | Path) -> None:
     offers = dto['offers']
     if len(offers) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+', offers[0]['offer_id']):
         raise ValueError('S1 requires one offer with a safe filename identifier')
-    if out.exists() and any(out.iterdir()) and not (out / '.public-dto-build').is_file():
+    if out.exists() and not out.is_dir():
+        raise ValueError('output is not a directory; refusing to overwrite')
+    marker = out / '.public-dto-build'
+    try:
+        marker_mode = marker.lstat().st_mode
+    except FileNotFoundError:
+        marker_mode = None
+    if marker_mode is not None and not stat.S_ISREG(marker_mode):
+        raise ValueError('output build marker must be a regular file')
+    if out.exists() and any(out.iterdir()) and marker_mode is None:
         raise ValueError('output directory is not a public-dto build output; '
                          'refusing to delete existing files')
     out.mkdir(parents=True, exist_ok=True)
```

## 2. D1

状态：**passed**。`scan_public_output` 先读字节，先找 `b'"evidence"\s*:'`，再拒绝 `b'\x00'`，再 `utf-8-sig` 解码；非法 UTF-8 抛 `ValueError`，不再 `continue`。位置：`/tmp/pr2-fix1/head/vps_pipeline/public_dto.py` 第 109–117 行。

探针 `/tmp/pr2-fix1/probes.py`，日志 sha256 `e29631067f1490b120fac8ae998fe439ae744531ed6af6f41ddcb876ab8a30fd`。摘录：

```text
D1 data_nul REJECT OUT/data.json: forbidden NUL byte
D1 data_bad_utf8 REJECT OUT/data.json: invalid UTF-8
D1 data_bom ALLOWED
D1 data_empty REJECT OUT/data.json: invalid public DTO JSON
D1 data_evidence_tail_binary REJECT OUT/data.json: forbidden evidence key
D1 nul_sidecar REJECT OUT/notes.bin: forbidden NUL byte
D1 bad_utf8_sidecar REJECT OUT/notes.bin: invalid UTF-8
D1 bom_valid_json ALLOWED size=16
D1 empty_sidecar ALLOWED size=0
D1 large_clean ALLOWED size=2097152
D1 large_evidence_tail REJECT OUT/large.bin: forbidden evidence key
D1 nul_then_evidence REJECT OUT/mix.bin: forbidden evidence key
D1 evidence_then_bad REJECT OUT/mix.bin: forbidden evidence key
D1 restored_clean ALLOWED
```

NUL 和非法 UTF-8 被拒绝，不是跳过。带 BOM 的合法 JSON、2 MiB 的普通文本、0 字节的非 JSON 文件照常通过。0 字节的 `data.json` 按非法 JSON 拒绝。二进制尾部的 `"evidence"` 会拒绝，包括前面有 NUL 或非法字节的情况。

合法 UTF-8 文件里一段既不是 `evidence` 键、也不是图片 URL 的记号，扫描允许通过（`D1 plain_sensitive_token ALLOWED`）。这不是本项要修的跳过逻辑，列为未覆盖。

## 3. D2

状态：**passed**。标记用 `lstat`，只接受 `S_ISREG`。符号链接、目录、FIFO 在删除之前抛 `output build marker must be a regular file`。位置：同文件第 242–248 行。

```text
D2 symlink_file ValueError: output build marker must be a regular file
D2 symlink_file precious_unchanged=True site_written=False external_intact=True marker_symlink=True
D2 symlink_dir ValueError: output build marker must be a regular file
D2 symlink_dir precious_unchanged=True inside_intact=True marker_symlink=True
D2 directory ValueError: output build marker must be a regular file
D2 directory precious_unchanged=True marker_still_dir=True nested=True
D2 fifo ValueError: output build marker must be a regular file
D2 fifo precious_unchanged=True marker_still_fifo=True
D2 regular ALLOWED stale_gone=False marker=True index=True
```

`stale_gone=False` 表示重建后 `stale.txt` 已不存在。用户文件、标记本身、符号链接目标和目录内文件都还在；普通文件标记会清空并重建。

`--out` 本身是符号链接时，CLI 在标记判断之前就拒绝，退出码 1，尾部 `ValueError: output path must not contain a symlink`。链接还在，目标里的原文件未改，没有写出 `index.html`。这条路径检查仍是 `is_symlink()`，不是这次的 `lstat` 标记判断。

## 4. D3

状态：**passed**。同一 `plan_id` 上，公开价格元组或 `geekbench6_single` 的值去重后多于 1 个，则对应输出为 null，并追加 `price: N values` 或 `geekbench6_single: N values`。完全相同的重复，即使多了 evidence，也不算冲突。输入记录不被改写。位置：同文件第 151–171 行。

```text
D3 case=distinct_price
price 全 null，score=1420，flags=["price: 2 values"]，evidence_in_public=False，input_unchanged=True
D3 case=distinct_score
price 保持 10 USD，score=None，flags=["geekbench6_single: 2 values"]
D3 case=both
price 全 null，score=None，flags=["price: 2 values", "geekbench6_single: 2 values"]
D3 case=identical_price_with_evidence
公开价格仍是 10 USD，flags=[]，evidence_in_public=False
D3 case=identical_score_with_evidence
score=1420，flags=[]，input_obs_count=2，input_has_evidence_key=True
D3 case=currency_differs
price 全 null，score=1420，flags=["price: 2 values"]
D3 case=billing_unit_differs
price 全 null，flags=["price: 2 values"]
D3 case=price_conflict_score_same
price 全 null，score=1420，flags 只有 price
D3 case=preexisting_flag
flags=["pre-existing", "price: 2 values"]
D3 case=historical_other_metric
input_unchanged=True，input_obs_count=2，input_has_evidence_key=True，evidence_in_public=False
```

货币不同或计费周期不同，不会挑其中一条，而是整组 price 置 null，并用 `price: 2 values` 记下字段和不同值个数。标志里没有把两种货币原文再写一遍。证据和另一条历史观测留在输入里，没有进公开 JSON。公开摘要仍然只有 `geekbench6_single`，这是原有白名单，不是这次把历史观测从输入里删掉。

## 5. D4

状态：**passed**。已存在且不是目录的 `--out` 抛 `ValueError: output is not a directory; refusing to overwrite`，发生在 `iterdir` 之前。位置：同文件第 240–241 行。

```text
D4 file cli_exit=1 tail=ValueError: output is not a directory; refusing to overwrite
bytes_unchanged=True still_file=True
D4 missing cli_exit=0 index=True data=True marker=True data_valid=True
```

原文件字节含 `\x00\xff`，拒绝后不变。不存在的路径会正常建成站点。

## 6. 全量回归

状态：**passed**。与作者声称的 300 OK 一致。命令在 `/tmp/pr2-fix1/head`：

```text
python3 -m unittest discover -s tests
```

| 遍 | 外层秒 | 退出码 | sha256 |
| --- | --- | --- | --- |
| 1 | 6.141160 | 0 | `6f12409df5e97f19d4ee25ae4d553b9ed1661ea29349728c53ac62a589e3dd28` |
| 2 | 6.696632 | 0 | `299e63c0e0081465426a9e08b77b0cc3ea4607674f08b8e2a86bb4f27ea76061` |

把 `Ran 300 tests in Xs` 的耗时换成常量后，两遍 sha256 都是 `984faed135643da5a9f2d357d0819a552228a6ab282ba89f88ce80a4075cb765`。

第 1 遍完整输出：

```text
............................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 300 tests in 5.878s

OK
```

第 2 遍完整输出：

```text
............................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 300 tests in 6.512s

OK
```

跑完后 head 仍是 `de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57`，tree 仍是 `233142911a7fae5ea92331aa6d37317a8400188e`。

## 7. 变异

状态：**passed**。每次从 `/tmp/pr2-fix1/head` 复制到 `/tmp/pr2-fix1-mut-*`，只改副本里的 `vps_pipeline/public_dto.py`，跑 `python3 -m unittest discover -s tests`，然后删除副本。没有提交。六次都是退出码 1，没有 missed，没有重试。

| 变异 | 退出码 | 外层秒 | 汇总 | sha256 |
| --- | --- | --- | --- | --- |
| 撤回 D1（NUL / 非法 UTF-8 再跳过） | 1 | 5.748727 | `Ran 300 tests in 5.622s` / `FAILED (failures=11)` | `cf2bbab99af3f840de48ccafbbce0fcd0308287c05c6bb4fb19606b4a6c04f29` |
| 撤回 D2（标记改回 `is_file` 门闩） | 1 | 6.795427 | `Ran 300 tests in 6.658s` / `FAILED (failures=12)` | `4f5b2cc5aa634409001b8e66458d9de8a64a54f3f4599524d1a2dd1ce56e41f7` |
| 撤回 D3（恢复取第一条） | 1 | 6.630130 | `Ran 300 tests in 6.486s` / `FAILED (failures=13)` | `78f7109f20c37ad4cb70c9b7ffe5378a965fbd91824eadf4b666d9d11e406772` |
| 撤回 D4（去掉非目录拒绝） | 1 | 6.193847 | `Ran 300 tests in 6.011s` / `FAILED (failures=1, errors=1)` | `005dc89993bf83bb018b2bad57e89217e02056d8b76f461064c488fd30ac23c4` |
| D3 的 null 改回取第一条，冲突标志仍写 | 1 | 6.324004 | `Ran 300 tests in 6.172s` / `FAILED (failures=7)` | `d1a9e007a5523d5cece5353579d08e22e40e01ccf0fda4e799dbeba00447cc37` |
| D2 的 `lstat` 改回 `is_file()` | 1 | 6.230681 | `Ran 300 tests in 6.053s` / `FAILED (failures=12)` | `d0e1ec46f7e3fd316476ecf4c966874ab50df3078e6840571cebc9dae10b6f81` |

D1 摘录：`AssertionError: 0 == 0 : NUL must not hide evidence from CLI scan`，以及 `ValueError not raised`。失败测试是 `test_cli_scan_rejects_evidence_with_nul` 和 `test_scan_rejects_nul_and_invalid_utf8_even_without_sensitive_keys`。

D4 摘录：API 得到 `NotADirectoryError`；CLI 断言 `NotADirectoryError unexpectedly found`。失败测试是 `test_build_refuses_regular_file_out_with_explicit_value_error` 和 `test_cli_build_refuses_regular_file_out_with_explicit_message`。

把 `lstat` 改回 `is_file()` 后，指向文件的标记符号链接不再拒绝，`precious.txt must survive refusal` 失败，CLI 退出码变成 0。

## 8. TOCTOU

状态：**passed**。PR 正文在 “S1 fix1” 一节有这句：

```text
residual risk — TOCTOU between marker check and delete is not fixed (intentional per PM)
```

代码仍是先 `lstat` 标记，通过后再 `mkdir` 并删除子项，中间没有锁。这和“未修、按 PM 保留”一致。本次没有做并发替换试验，见未覆盖项。

## B. 扫描失败后的残留

状态：**failed**。详见缺陷 D5。

探针日志 `/tmp/pr2-fix1/logs/residue.log`，sha256 `a9ab9a05e04ca481610e329c0f724dab17f8cb676d27f272069da1ea23d94f26`。构建不产生 Markdown。每次失败后目录里都是这 6 项：`.public-dto-build`、`data.json`、`index.html`、`offers/`、`offers/FX-001.html`、`style.css`。

| 场景 | CLI | 留下的文件是否完整 | schema 校验 `data.json` |
| --- | --- | --- | --- |
| 新目录，摘要含合成图片 URL，`build` | 退出码 1，`forbidden original image URL` | 标记 27 字节且与成功构建相同；两个 HTML 都以 `</html>` 结束；JSON 可解析；CSS 非空 | 接受 |
| 新目录，公开字符串含 NUL，`build` | 退出码 1，`index.html: forbidden NUL byte` | 同上，HTML 完整，JSON 可解析（NUL 被转成 `\u0000`） | 接受 |
| 新目录先成功构建，再把 `data.json` 尾部改成非法 UTF-8，`scan` | 退出码 1，`invalid UTF-8` | 标记和两个 HTML、CSS 仍是成功构建的字节；`data.json` 不能按 UTF-8 解码 | 读不了 |
| 已有合格目录，`data.json` 加 NUL，`scan` | 退出码 1，`forbidden NUL byte` | HTML 与 CSS 仍是合格构建的 sha256；`data.json` 不能解析 | 读不了 |
| 已有合格目录，详情页尾部加非法 UTF-8，`scan` | 退出码 1，`invalid UTF-8` | `data.json` 与 `index.html` 仍是合格字节；详情页不再以 `</html>` 结束 | 接受 |
| 已有合格目录，`data.json` 写入 `evidence`，`scan` | 退出码 1，`forbidden evidence key` | HTML 与 CSS 仍是合格字节；JSON 可解析 | 拒绝，`unknown properties` |

CLI 输入本身必须是合法 UTF-8，所以“全新目录的 build”不会自行写出非法 UTF-8。非法 UTF-8 是在新目录的成功产物上改文件后再 `scan`。NUL 和图片 URL 则是 `build` 自己的扫描失败。

对带标记的污染目录再用合法输入 `build`：退出码 0，污染注释消失，六个文件的 sha256 回到合格构建。再次构建是清空重写，不是把残留原样当成合格内容发布。

`scan` 在上述失败场景退出码都是 1。

直接静态读取失败目录（摘要含图片 URL）：

```text
HTTP_INDEX 200
HTTP_DATA 200
HTTP_OFFER 200
INDEX_HAS_URL 1
DATA_HAS_URL 1
```

仓库内检索：`README.md`、`scripts/` 和其他 `vps_pipeline` 模块都没有读取 `.public-dto-build` 或这次 `--out`。会碰这个目录的只有 `public_dto` 的 `build` / `scan`，以及测试。已提交的 `website/public-dto-v1/` 没有标记文件，其 `data.json`、两个 HTML 和 `style.css` 的 sha256 与一次成功构建相同，它是干净样例，不是失败残留的读取方。

## 新缺陷

### D5 扫描失败后的站点文件仍可被直接当成页面读取

- 严重度：中
- 位置：`/tmp/pr2-fix1/head/vps_pipeline/public_dto.py`，`build_public_site` 在第 296–299 行先写完 `data.json`、页面、CSS 和 `.public-dto-build`，然后才 `scan_public_output`。失败不删除这些文件。标记文本固定为 `public-dto/v1 build output\n`，与成功构建相同。
- 复现：用 FX-001 内部记录，把摘要改成含 `https://cdn.synthetic.example/original/fx001-hero.png` 的句子，对一个新目录执行 `python3 -m vps_pipeline.public_dto build --input <该 json> --out <新目录>`。退出码为 1。目录里仍有完整 `index.html`、`offers/FX-001.html`、`data.json` 和标记。对 `data.json` 调用 `validate_public_dto` 不抛错。用静态文件服务读取该目录，三个 URL 都是 HTTP 200，页面和 JSON 里都有这张图片 URL。
- 影响：非零退出码没有把目录留在“不可当站点读”的状态。只看标记、只做 schema 校验，或直接打开页面，都会看到这次扫描已经拒绝的内容。仓库里没有发布脚本自动做这件事；风险在于失败目录本身已经是一套完整静态站。
- 对照：再次用合法输入构建同一目录会整目录替换，不会保留污染页。`scan` 会拒绝。

## 未覆盖

- 合法 UTF-8 里、既不是 `evidence` 键也不是图片 URL 的敏感字符串。扫描不负责这件事。
- 并发下标记检查和删除之间的 TOCTOU。描述已核对，没有做竞态试验。
- 仓库外的发布系统、CI 拷贝 `--out` 的步骤。仓库内没有这种脚本。
- 变异只跑了全量测试，没有再跑一遍 D1–D4 手工探针。
- 构建不产生 Markdown，因此没有 Markdown 残留可列。
