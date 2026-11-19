---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 2 fix3 独立只读复验

仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/2`，分支 `s1-public-dto-v1`。

本文件只给质量结论。没有推送，没有改 PR，没有评论。

## 结论

**pass**

D6 的测试打在第二次 rename 上，旧目录会还原。删备份失败时构建成功、CLI 为 0，stderr 带备份绝对路径。扫描失败和第二次 rename 失败仍然非 0。五次变异都被全量抓住，没有 missed。两遍都是 `Ran 309 tests` / `OK`。

| 项 | 状态 |
| --- | --- |
| 实时 head 仍是 `5a06d684` | passed |
| 1. diff 只有两个文件，代码改动与声称提交一致 | passed |
| 2. D6 第二次 rename 失败会还原 | passed |
| 3. 删备份失败只警告且不掩盖另两类失败 | passed |
| 4. 五项变异都被抓住 | passed |
| 5. 全量两遍 309 OK | passed |
| 6. PR 正文写了残留备份风险 | passed |
| D1–D5 | skipped |

## 环境与检出

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`，`/usr/bin/python3`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`

```text
git ls-remote https://github.com/WenLiCG/vps-review-platform.git refs/heads/s1-public-dto-v1 refs/heads/main
f7b35842c94d2ab77e3d2bd23f559cafc8b41929	refs/heads/main
5a06d684381ab8e74adfc2dcc129ed9ff163c410	refs/heads/s1-public-dto-v1
```

Pull request head SHA 同样是 `5a06d684381ab8e74adfc2dcc129ed9ff163c410`。没有 blocked。

独立检出，不用上一轮目录：

```text
git clone --local /workspace /tmp/pr2-fix3/head
git -C /tmp/pr2-fix3/head checkout --detach 5a06d684381ab8e74adfc2dcc129ed9ff163c410
git -C /tmp/pr2-fix3/head rev-parse HEAD
git -C /tmp/pr2-fix3/head rev-parse 'HEAD^{tree}'
```

| 项 | SHA |
| --- | --- |
| head | `5a06d684381ab8e74adfc2dcc129ed9ff163c410` |
| head tree | `b8f38499f01f8ffd4e787a828bf8109dc192c88b` |
| 上一 head | `d8c41af4301e53304faad44df062435b0021666b` |
| 上一 head tree | `0ba3198adc74019372cbff6667246e1beb6e7e9b` |
| 中间提交 | `cdafac462253da85edb2820a227019a5606fdb9d` |
| 中间提交 tree | `f377207fec878e25e52dbd4dbefff9cd913dbca4` |

`cdafac4` 的父提交是 `d8c41af4`，只改 `tests/test_public_dto_pages.py`，新增 3 个测试方法。`5a06d684` 的父提交是 `cdafac4`，相对它只改 `vps_pipeline/public_dto.py`，`1 file changed, 6 insertions(+), 1 deletion(-)`。

## 1. diff `d8c41af4..5a06d684`

状态：**passed**。

```text
M	tests/test_public_dto_pages.py
M	vps_pipeline/public_dto.py
```

合计 `2 files changed, 103 insertions(+), 1 deletion(-)`。diff sha256 `868b7b62672c363b94f19a4b5a81c22b1789e7058801832bcf1dff92ed2b565d`。

生产代码只把成功替换之后的 `shutil.rmtree(backup)` 包进 `except OSError`，向 stderr 打印 `warning: could not delete backup directory: <绝对路径>`，然后继续返回。第二次 rename 的 `except BaseException` 仍会把备份改回并重新抛出。扫描在替换之前，失败不会走到这段警告。

```diff
diff --git a/tests/test_public_dto_pages.py b/tests/test_public_dto_pages.py
index 1f706b0..911dd7d 100644
--- a/tests/test_public_dto_pages.py
+++ b/tests/test_public_dto_pages.py
@@ -238,6 +238,103 @@ class PublicDTONegativePagesTests(unittest.TestCase):
         self.assertEqual(set(self.out.parent.iterdir()), siblings_before,
                          'failed build must leave no temporary or backup entries in out.parent')
 
+    def test_build_second_rename_failure_restores_old_output(self):
+        from unittest.mock import patch
+
+        build_public_site(load_internal(), self.out)
+        (self.out / 'old-site-sentinel.bin').write_bytes(b'D6 old site only\x00\xff\n')
+        self.out.chmod(0o750)
+        mode_before = self.out.stat().st_mode & 0o777
+        files_before = self.output_file_snapshot()
+        self.assertIn('.public-dto-build', files_before)
+        siblings_before = set(self.out.parent.iterdir())
+        real_rename = os.rename
+        failure = OSError('synthetic replace failure')
+        failed_once = False
+
+        def fail_build_publish_once(src, dst, *args, **kwargs):
+            nonlocal failed_once
+            source = Path(src)
+            if (not failed_once and Path(dst) == self.out
+                    and source.parent == self.out.parent
+                    and source.name.startswith(f'.{self.out.name}-build-')):
+                failed_once = True
+                raise failure
+            return real_rename(src, dst, *args, **kwargs)
+
+        with patch('vps_pipeline.public_dto.os.rename', side_effect=fail_build_publish_once):
+            with self.assertRaisesRegex(OSError, 'synthetic replace failure') as caught:
+                build_public_site(load_internal(), self.out)
+        self.assertTrue(failed_once, 'must exercise the second rename failure')
+        self.assertIs(caught.exception, failure, 'must propagate the original OSError')
+        self.assertTrue(self.out.is_dir())
+        self.assertEqual(self.out.stat().st_mode & 0o777, mode_before)
+        self.assertEqual(self.output_file_snapshot(), files_before)
+        self.assert_failed_build_preserves_parent(siblings_before)
+
+    def assert_backup_delete_failure_is_success(self, cli=False):
+        from contextlib import redirect_stderr, redirect_stdout
+        from io import StringIO
+        from unittest.mock import patch
+        from vps_pipeline import public_dto
+
+        build_public_site(load_internal(), self.out)
+        sentinel = 'old-site-sentinel.bin'
+        (self.out / sentinel).write_bytes(b'backup delete old site only\x00\xff\n')
+        old_files = self.output_file_snapshot()
+        real_rmtree = public_dto.shutil.rmtree
+        attempted_backups = []
+
+        def fail_backup_delete(path, *args, **kwargs):
+            candidate = Path(path).resolve()
+            if (candidate.parent == self.out.parent.resolve()
+                    and candidate.name.startswith(f'.{self.out.name}-backup-')):
+                attempted_backups.append(candidate)
+                raise OSError('synthetic backup delete failure')
+            return real_rmtree(path, *args, **kwargs)
+
+        stderr, stdout = StringIO(), StringIO()
+        with patch('vps_pipeline.public_dto.shutil.rmtree', side_effect=fail_backup_delete), \
+                redirect_stderr(stderr), redirect_stdout(stdout):
+            if cli:
+                input_path = self.out.parent / 'clean-input.json'
+                input_path.write_text(json.dumps(load_internal()), encoding='utf-8')
+                argv = ['public_dto', 'build', '--input', str(input_path), '--out', str(self.out)]
+                with patch.object(sys, 'argv', argv):
+                    try:
+                        result = public_dto.main()
+                    except SystemExit as exited:
+                        self.assertIn(exited.code, (None, 0), 'published CLI build must exit successfully')
+                    else:
+                        self.assertIn(result, (None, 0))
+            else:
+                self.assertIsNone(build_public_site(load_internal(), self.out))
+
+        self.assertTrue(attempted_backups, 'must attempt to delete the old backup')
+        self.assertTrue(self.out.is_dir())
+        self.assertFalse((self.out / sentinel).exists(), 'new site must replace the old site')
+        self.assertEqual(self.output_file_snapshot(),
+                         {name: data for name, data in old_files.items() if name != sentinel})
+        for relative in ('index.html', 'data.json', '.public-dto-build'):
+            self.assertTrue((self.out / relative).is_file(), relative)
+        backups = list(self.out.parent.glob(f'.{self.out.name}-backup-*'))
+        self.assertEqual(len(backups), 1, 'failed cleanup must leave the old backup observable')
+        backup = backups[0]
+        self.assertTrue(backup.is_dir())
+        self.assertEqual({p.relative_to(backup).as_posix(): p.read_bytes()
+                          for p in backup.rglob('*') if p.is_file()}, old_files)
+        self.assertIn(backup.resolve(), attempted_backups)
+        self.assertRegex(stderr.getvalue(), r'(?i)(warn|warning|警告)')
+        self.assertIn(str(backup.resolve()), stderr.getvalue())
+        self.assertNotRegex(stdout.getvalue(), r'(?i)(warn|warning|警告)')
+        self.assertEqual(list(self.out.parent.glob(f'.{self.out.name}-build-*')), [])
+
+    def test_build_backup_delete_failure_warns_and_returns_success(self):
+        self.assert_backup_delete_failure_is_success()
+
+    def test_cli_build_backup_delete_failure_warns_and_exits_zero(self):
+        self.assert_backup_delete_failure_is_success(cli=True)
+
     def run_contaminated_build_cli(self, input_path):
         return subprocess.run(
             [sys.executable, '-B', '-m', 'vps_pipeline.public_dto', 'build',
diff --git a/vps_pipeline/public_dto.py b/vps_pipeline/public_dto.py
index d357dd7..ab07421 100644
--- a/vps_pipeline/public_dto.py
+++ b/vps_pipeline/public_dto.py
@@ -12,6 +12,7 @@ from pathlib import Path
 import re
 import shutil
 import stat
+import sys
 import tempfile
 from urllib.parse import urlsplit
 
@@ -326,7 +327,11 @@ def build_public_site(internal_record: dict, out_dir: str | Path) -> None:
             except BaseException:
                 os.rename(backup, target)
                 raise
-            shutil.rmtree(backup)
+            try:
+                shutil.rmtree(backup)
+            except OSError:
+                print(f'warning: could not delete backup directory: {backup.resolve()}',
+                      file=sys.stderr)
         else:
             os.rename(out, target)
             published = True
```

## 2. D6

状态：**passed**。

`test_build_second_rename_failure_restores_old_output` 在 `tests/test_public_dto_pages.py` 里 patch `vps_pipeline.public_dto.os.rename`。失败条件是：目标等于 `--out`，源在同级，且名字以 `.{out.name}-build-` 开头。这是临时目录改名为 `--out` 的那一次，不是旧目录改成备份，也不是备份改回去。它要求 `failed_once` 为真、抛出的是原来的 `OSError` 对象、目录 mode 不变、文件字节快照不变、同级没有临时或备份目录。

独立 mock（不是这套测试）在子进程里数了 rename：`first,second,restore`。第二次抛 `OSError: independent second rename failure`，旧目录 mode 仍是 `0o750`，文件 sha256 不变，sentinel 还在，`BACKUPS []`，`BUILDS []`，stderr 没有 warning。日志 `/tmp/pr2-fix3/logs/probe.log`，sha256 `a5f47849babd491d29beb9b6cf3c9063e8eb8b7f29889f03a578f351a14ae3ec`。

```text
KIND second-rename
EXC OSError: independent second rename failure
CODE 1
MODE 0o750 BEFORE 0o750
BYTES_SAME True
SENTINEL True
BACKUPS []
BUILDS []
RENAMES first,second,restore
HAS_WARN False
```

变异 (iv) 去掉 `os.rename(backup, target)` 后，全量失败。外层 7.911737 秒，退出码 1，sha256 `a38674a67fe8d0173e05d75e8bdb2d75505020899c60978c1ae1b403b55981fe`。

```text
FAIL: test_build_second_rename_failure_restores_old_output
AssertionError: False is not true
Ran 309 tests in 7.662s
FAILED (failures=1)
```

失败点是 `self.assertTrue(self.out.is_dir())`：备份没有改回去，`--out` 不在了。

## 3. 删备份失败

状态：**passed**。位置：`/tmp/pr2-fix3/head/vps_pipeline/public_dto.py` 第 330–334 行。

仓库测试 `test_build_backup_delete_failure_warns_and_returns_success` 和 `test_cli_build_backup_delete_failure_warns_and_exits_zero` 都在全量里通过。独立子进程另外 patch 了 `shutil.rmtree`，只让备份目录删除失败：

```text
KIND backup-api
CODE 0
SENTINEL False
BACKUPS ['.site-backup-_3cit44j']
STDERR warning: could not delete backup directory: /tmp/pr2-fix3/work/backup-api/.site-backup-_3cit44j
PATH_IN_STDERR True

KIND backup-cli
CODE 0
SENTINEL False
STDERR warning: could not delete backup directory: /tmp/pr2-fix3/work/backup-cli/.site-backup-lre6rw_x
PATH_IN_STDERR True
```

`main()` 没有非 0 退出。新站点换上后旧 sentinel 不在 `--out` 里，备份目录留在同级，警告里的路径是该目录的绝对路径。

同一套“删备份会失败”的 patch 下，扫描失败和第二次 rename 失败都没有被收成成功：

```text
KIND scan-still-fails
EXC ValueError: .../data.json: forbidden original image URL
CODE 1
BYTES_SAME True
HAS_WARN False

KIND rename-still-fails
EXC OSError: independent second rename failure
CODE 1
RENAMES first,second,restore
BYTES_SAME True
HAS_WARN False
```

不打 patch 的真实 CLI，摘要含合成图片 URL 时退出码 1，`--out` 没有留下：

```text
REAL_CLI_SCAN exit=1 out_exists=False
tail=ValueError: ... forbidden original image URL
```

## 4. 变异

状态：**passed**。没有 missed。副本从 `/tmp/pr2-fix3/head` 复制，只改 `vps_pipeline/public_dto.py`，命令是 `python3 -B -m unittest discover -s tests`，跑完删除。没有提交，没有重试。

| 变异 | 结果 | 退出码 | 外层秒 | 汇总 | sha256 | 抓住它的测试 |
| --- | --- | --- | --- | --- | --- | --- |
| (iv) 去掉 `os.rename(backup, target)` | captured | 1 | 7.911737 | `FAILED (failures=1)` | `a38674a67fe8d0173e05d75e8bdb2d75505020899c60978c1ae1b403b55981fe` | `test_build_second_rename_failure_restores_old_output` |
| 警告之后再抛异常 | captured | 1 | 7.652771 | `FAILED (errors=2)` | `3c5b4edf85fd3627a889d4df2b37bb47fa00f3d204617e9e9e44eefe33c25752` | 两个删备份测试 |
| 去掉 stderr 警告 | captured | 1 | 7.754342 | `FAILED (failures=2)` | `ca073260fe7a6346b1369fd220db41a3163856388636df16d1c0c661d9956bfe` | 同上，`Regex didn't match` |
| 警告里没有备份路径 | captured | 1 | 7.427316 | `FAILED (failures=2)` | `5816fea705fd3f6e6c43d9f3dcfd29c47b701f5300188049998b652fb1a64ce1` | 同上，路径不在 stderr |
| 吞掉第二次 rename 的 `OSError` | captured | 1 | 7.468676 | `FAILED (failures=1)` | `59ff5a820b4cee449aeda2499023b3bf5ef7654a6b5d38192cd45f6b4f680f28` | D6 测试，`OSError not raised` |

去掉警告的摘录：`AssertionError: Regex didn't match: '(?i)(warn|warning|警告)' not found in ''`。没有路径的摘录：`'/tmp/.../.site-backup-...' not found in 'warning: could not delete backup directory\n'`。

## 5. 全量

状态：**passed**。与预期 309 OK 一致。目录 `/tmp/pr2-fix3/head`。

```text
python3 -B -m unittest discover -s tests
```

| 遍 | 外层秒 | 退出码 | sha256 |
| --- | --- | --- | --- |
| 1 | 7.389781 | 0 | `c4981c29ca5abe86fb9fd5902d79b42797bf5f3489e9a54db684d2caa66e7b83` |
| 2 | 7.738310 | 0 | `4ec5f428a2894b2c772c9be3807487e3ce0f677346fa8d7c5654fd3e39daf26c` |

耗时换成常量后两遍 sha256 都是 `c3120043762b11fb70b6bfdb187dfe711979374d96af1f8efe17f8fb0e62a7d3`。跑完 head 与 tree 未变。

第 1 遍：

```text
.....................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 309 tests in 7.140s

OK
```

第 2 遍：

```text
.....................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 309 tests in 7.533s

OK
```

## 6. PR 正文

状态：**passed**。有 “S1 fix3” 一节。残留风险写明：删除备份失败时会在 `--out` 同级留下旧站点备份目录，stderr 会打印路径；这是本轮接受的行为。另有一句：旧站备份目录留在 `--out` 旁边，路径打到 stderr。

## 首次失败与重试

产品命令和五次变异都是一次完成。独立探针第一次把“第二次 rename 仍然失败”的触发条件写成只在 `second-rename` 场景生效，`rename-still-fails` 因此误走了成功替换。这是探针错误，不是产品失败。改正条件后重跑，该场景 `CODE 1`，序列是 `first,second,restore`，没有 warning。报告摘录用的是重跑日志。

## 未覆盖

- D1–D5 本轮 skipped，没有重跑。
- 跨文件系统 `EXDEV`、替换窗口的并发读者、umask 短暂为 0、TOCTOU 没有重做。
- `shutil.rmtree` 若抛出 `OSError` 以外的异常，现有 `except OSError` 不会接住。这次没有构造这类异常。
- 备份删到一半再失败（目录还在但内容不完整）没有单独构造。
