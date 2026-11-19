---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 2 独立只读复验

对照仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/2`。

固定候选：

- head `1586ebefd6450c0a38775f90e9e0f3baf6085f0e`（`origin/s1-public-dto-v1` 的 tip 与此相同）
- base `f7b35842c94d2ab77e3d2bd23f559cafc8b41929`（`main`）

本文件是质量建议。检出在独立临时目录完成，变异副本已删除，没有推送、没有改 PR、没有评论、没有部署。

## 结论建议

head 上作者声称的两组结果可以复核：定向套件 `Ran 31 tests` / `OK`，全库 `Ran 290 tests` / `OK`，两遍都是 skipped 0、退出码 0。base 全库是 `Ran 259 tests` / `OK`，差额正好 31。

公开投影对未知字段默认拒绝。时区缺失、价格缺失、多套餐这三种指定情形没有编造数量或时区；多套餐会保留成多条 offer，静态构建在 offer 数不是 1 时拒绝落盘。非空且无标记的目录、路径分量上的符号链接、落到非空无标记目录的 `..`、输出目录等于输入目录或其父目录、以及 `website/dist` 与仓库根和仓库父目录，都会拒绝，已有文件保持原样。

建议先处理下面两处，再做一次同样的复验：

1. 扫描在读到 NUL 或非法 UTF-8 时直接跳过该文件，因此 `data.json` 可以带上 `evidence` 而不被拒绝。严重度：中。
2. 名为 `.public-dto-build`、且 `Path.is_file()` 为真的符号链接（指向普通文件）会授权清空整个输出目录。这比“无关目录里手工放了标记文件会被清理”更宽。严重度：中。

五项变异都被现有公开 DTO 测试抓住（captured）。没有 missed。两项残留风险的正文现象都能复现；因为删除触发比这两条更宽，残留风险核对为 **failed**。

| 项 | 状态 |
| --- | --- |
| 1. 复跑作者声称结果 | passed |
| 2. 代码审查（含扫描旁路） | failed |
| 2.1 白名单投影，未知字段默认拒绝 | passed |
| 2.2 缺时区、缺价格、多套餐不臆造 | passed |
| 2.3 列出的目录拒绝路径 | passed |
| 3. 五项变异 | passed（五项均为 captured） |
| 4. 两项残留风险与描述一致且不更宽 | failed |
| SHA 核对 | passed（未 blocked） |

## 环境

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`，可执行文件 `/usr/bin/python3`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`
- 平台字符串 `Linux-6.12.113+-x86_64-with-glibc2.39`

## 检出与 SHA 核对

状态：**passed**。`git rev-parse HEAD` 与固定 SHA 一致，没有 blocked。

```text
git clone --local /workspace /tmp/pr2-verify/head
git -C /tmp/pr2-verify/head checkout --detach 1586ebefd6450c0a38775f90e9e0f3baf6085f0e
git -C /tmp/pr2-verify/head rev-parse HEAD
# 1586ebefd6450c0a38775f90e9e0f3baf6085f0e

git clone --local /workspace /tmp/pr2-verify/base
git -C /tmp/pr2-verify/base checkout --detach f7b35842c94d2ab77e3d2bd23f559cafc8b41929
git -C /tmp/pr2-verify/base rev-parse HEAD
# f7b35842c94d2ab77e3d2bd23f559cafc8b41929
```

两份工作树 `git status --porcelain` 都为空。`origin/s1-public-dto-v1` 解析为同一个 head SHA。base 是 head 的祖先。工作区 `/workspace` 保持在 base，未被这次复验改动。

审查用的源文件是 `/tmp/pr2-verify/head/vps_pipeline/public_dto.py`（commit `1586ebefd6450c0a38775f90e9e0f3baf6085f0e`）。

## 1. 复跑作者声称的结果

状态：**passed**。head 与“31 OK、290 OK”一致。每组 head 两遍、base 一遍。skipped 都是 0。没有重跑失败的用例；原始 sha256 在两遍之间不同，只因为 unittest 把耗时写进了 `Ran N tests in Xs`。把该耗时替换成常量后，两遍的标准化 sha256 相同。

外层耗时含解释器启动。用例耗时是 unittest 自报的那一行。sha256 覆盖完整 stdout+stderr。

命令（在对应检出目录中）：

```text
python3 -B -m unittest tests.test_public_dto tests.test_public_dto_pages
python3 -B -m unittest discover -s tests
```

| 运行 | 外层秒 | 用例行 | 退出码 | 用例数 | skipped | sha256 |
| --- | --- | --- | --- | --- | --- | --- |
| head 定向 1 | 0.635900 | `Ran 31 tests in 0.551s` / `OK` | 0 | 31 | 0 | `c974f44d04e7d923187d0bfdbad6c255029990fd324d59f94faf891237cd2cc1` |
| head 定向 2 | 0.565630 | `Ran 31 tests in 0.507s` / `OK` | 0 | 31 | 0 | `46a8cadd8cce724b21274070ba06468da8040d20e8482ec22a397165641f10bc` |
| base 定向对照 | 0.035518 | `Ran 2 tests in 0.000s` / `FAILED (errors=2)` | 1 | 2 | 0 | `deb89e2dad433ba584331511ae6c9ed7193392c1c2aab29377871580cf7349b2` |
| head discover 1 | 7.453392 | `Ran 290 tests in 7.224s` / `OK` | 0 | 290 | 0 | `2a8949060873f2e5a3e441e877d2422e17946882f1d4352c1947be8fd13f1e8c` |
| head discover 2 | 8.128749 | `Ran 290 tests in 7.904s` / `OK` | 0 | 290 | 0 | `f893ca0bafb344f2a4481945c117ac6442b160a9c77dd44c9f0e599b425ec0f7` |
| base discover 对照 | 7.383430 | `Ran 259 tests in 7.161s` / `OK` | 0 | 259 | 0 | `d49d2f406dd727c5dd661a4d843d3406650421ca21c24d9b680015b5a96b42ed` |

标准化 sha256（仅替换耗时数字）：

- head 定向两遍都是 `411e56ec109bb470eeccbeafa685d404d7f82548b34a71d0692460daa77f1c11`
- head discover 两遍都是 `0fddd0c553bc2c07ba81811ab21b3ceff50df8cbadfdcb5da4f6e15a3f883359`

head 定向摘录：

```text
...............................
----------------------------------------------------------------------
Ran 31 tests in 0.551s

OK
```

head discover 摘录：

```text
----------------------------------------------------------------------
Ran 290 tests in 7.224s

OK
```

base 定向摘录（对照成立：这两个模块是 head 新增的，base 上不存在）：

```text
ModuleNotFoundError: No module named 'tests.test_public_dto'
ModuleNotFoundError: No module named 'tests.test_public_dto_pages'
----------------------------------------------------------------------
Ran 2 tests in 0.000s

FAILED (errors=2)
```

base discover 摘录：

```text
----------------------------------------------------------------------
Ran 259 tests in 7.161s

OK
```

`290 - 259 = 31`，与定向套件的用例数一致。

## 2. 代码审查

总状态：**failed**。失败点是扫描旁路（缺陷 D1）。投影、缺值的三种指定情形、以及列出的目录拒绝路径本身是 passed。

行为探针脚本是 `/tmp/pr2-verify/behavior_probes.py`，完整 stdout 的 sha256 为 `c9e3b7ea71047e6af6315a6f529d07629f7e87061f585249021003e76a814f2e`（8692 字节）。补充探针 `/tmp/pr2-verify/logs/extra-probes.log` 的 sha256 为 `aeb440d76b09f94af4bf6d7855e78020988e25150e6fcf3ed0a9b27745fbfe51`。探针只写 `/tmp/pr2-verify/probes*`。探针结束后 head 仍是 `1586ebefd6450c0a38775f90e9e0f3baf6085f0e`，工作树干净。`website/dist` 与 `vps_pipeline/public_dto.py` 的字节未被这些拒绝路径改写。

### 2.1 白名单与默认拒绝

状态：**passed**（投影与校验）。扫描旁路另计为缺陷 D1，不把这一子项改成 passed 以外的总评。

`_validate` 对对象使用 `set(value) - properties.keys()`，多出来的键抛 `unknown properties`（`/tmp/pr2-verify/head/vps_pipeline/public_dto.py` 第 72–75 行）。这是默认拒绝，不是默认放行。`_object` 把全部 properties 标为 required，并写了 `additionalProperties: False`。

`project_to_public_dto` 只拷贝 `RECORD_FIELDS`、`PLAN_FIELDS`、location/price 的 schema 键、`geekbench6_single` 的数值、`conflict_flags`、`summary_text`、`limited_claim`。`aff_url` 固定写成 `None`。投影结束后再调用 `validate_public_dto`。

Python schema 与 `/tmp/pr2-verify/head/schemas/public-dto/v1/public-dto.schema.json` 的根键、offer 键一致。JSON Schema 在根、offer、location、price、observations_summary 上均为 `additionalProperties: false`。

探针摘录：

```text
SCHEMA_OFFER_KEYS_EQUAL True
ONLY_PY []
ONLY_JS []
BASE_PROJECTION_MATCH True
UNKNOWN_FIELD_DROPPED True
UNKNOWN_DTO_KEY_DEFAULT deny $.offers[0]: unknown properties
```

在内部记录上追加未知键、套餐备注、地点备注、价格内部 id、观测里的 evidence 对象后，这些字符串没有进入公开 JSON，DTO 仍能通过校验。夹具里的 canary 字符串和禁止公开的键名没有出现在正常投影里。报告不抄写这些 canary。

扫描是后闸，不是投影器的替代。`scan_public_output` 会拒绝 JSON 键 `evidence`，以及解码后文本里的 https 图片 URL；`data.json` 还会再跑 `validate_public_dto`，所以直接写进 `data.json` 的未知字段会被拒绝。正常构建写出的 UTF-8 `data.json` 走这条路径。

### 2.2 缺值不猜

状态：**passed**。同套餐多条价格、同一指标多条观测被静默取第一条，记为低严重度观察 D3，不推翻这三项。

| 情形 | 结果 |
| --- | --- |
| 删掉 `published_tz` | 键仍在，值为 `null`，没有补时区 |
| `prices` 为空，或 `plan_id` 对不上 | amount、currency、周期、term、月均价、`price_status` 全是 `null`，没有把状态写成 `unknown`/`missing`，也没有用金额除周期 |
| 两个套餐 | 投影出 2 条 offer，vcpu/地点/GB6 各自保留；记录级 `conflict_flags` 原样抄到每条；套餐内的 evidence 引用没有进公开 JSON。`build_public_site` 抛 `ValueError: S1 requires one offer with a safe filename identifier`，没有合成一张合并页 |
| `offer_id` 设为 `../escape` | 同上文件名校验拒绝，没有写出逃逸路径 |

摘录：

```text
TZ_MISSING value=None key_present=True
PRICE_EMPTY {"amount": null, "currency": null, "billing_period_months": null, "term_role": null, "monthly_equivalent": null, "price_status": null}
MULTI_PLAN_COUNT 2
MULTI_PLAN_LABELS London Mini,Tokyo Mini
MULTI_PLAN_VCPU 2,1
MULTI_PLAN_EVIDENCE_LEAK False
MULTI_PLAN_BUILD ValueError: S1 requires one offer with a safe filename identifier
```

没有 `plan_id` 时，价格和 GB6 都是空，不会误挂到别的套餐。

### 2.3 输出目录保护

状态：**passed**。机制分三层，都在删除和 `mkdir` 之前完成对列出场景的拒绝：

1. 对传入路径本身及其 `parents` 调用 `is_symlink()`，命中则 `output path must not contain a symlink`（第 208–211 行）。发生在 `resolve()` 之前。
2. `resolve()` 之后，若路径等于 `website/dist`、在其内部，或是它的祖先（因此包含仓库根和仓库父目录，也包含 `website/`），抛 `output must not overwrite website/dist`（第 213–215 行）。
3. 目录已存在、非空、且 `.public-dto-build` 不是 `is_file()`，抛 `refusing to delete existing files`（第 220–222 行）。通过之后才 `mkdir` 并清空子项（第 223–228 行）。子项若是符号链接，走 `unlink`，不 `rmtree`。

探针：

```text
NONEMPTY_NO_MARKER ValueError: ... refusing to delete existing files
NONEMPTY_NO_MARKER_FILES {"precious.txt": "KEEP-ME\n", "keep/notes.txt": "NOTES\n"}
SYMLINK_OUT ValueError: output path must not contain a symlink
SYMLINK_PARENT ValueError: output path must not contain a symlink
TRAVERSAL ValueError: ... refusing to delete existing files
TRAVERSAL_RESOLVED /tmp/pr2-verify/probes/trav/real
OUT_EQ_INPUT_DIR ValueError: ... refusing to delete existing files
OUT_EQ_INPUT_DIR_SRC_EXISTS True notes=True
OUT_IS_PARENT ValueError: ... refusing to delete existing files
PROTECTED repo_root ValueError: output must not overwrite website/dist
PROTECTED ancestor ValueError: output must not overwrite website/dist
PROTECTED dist ValueError: output must not overwrite website/dist
PROTECTED dist_child ValueError: output must not overwrite website/dist
PROTECTED website ValueError: output must not overwrite website/dist
PROTECTED_KEY_UNCHANGED True
PROTECTED_DIST_UNCHANGED True
OFFER_ID_TRAVERSAL ValueError: S1 requires one offer with a safe filename identifier
OFFER_ID_ESCAPE_EXISTS escape=False out=False
```

补充探针：进程 cwd 是符号链接时，输出参数用 `.` 指到非空无标记目录，仍被第 3 层拒绝，`precious.txt` 还在。代码没有单独比较 `--input` 与 `--out`；输入目录非空且无标记时由第 3 层拒绝。`..` 会被 `resolve()` 规范化，落点若非空且无标记则拒绝，没有单独的“出现 `..` 就拒绝”。

相对路径 `rel-out` 在 cwd 已是符号链接时，会在链接目标下新建子目录，不删除该目录里原有的 `precious.txt`。符号链接检查只看传入路径的词法分量，不看进程 cwd。这不是列出的删除场景。

输出路径若是一个普通文件，在 `iterdir()` 处抛 `NotADirectoryError`，文件内容不变。这是低严重度观察 D4：没有打成明确的拒绝文案，也没有删文件。

## 3. 变异与负向测试

状态：**passed**。五项都是 captured，没有 missed。每次只改一份临时副本里的 `/tmp/pr2-mut-<项>/vps_pipeline/public_dto.py`，跑完删除副本。原 head 检出未被修改。

变异套件命令：

```text
python3 -B -m unittest tests.test_public_dto tests.test_public_dto_pages
```

变异副本上的 `python3 -B -m unittest discover -s tests`：**unrun**。31 项已经失败，足够判断 captured，没有再用全库 discover 补跑。

| 变异 | 结果 | 退出码 | 外层秒 | 用例行 | sha256 |
| --- | --- | --- | --- | --- | --- |
| (a) 首次 | captured | 输出以 FAILED 结束；退出码该次未单独采集 | 未记录（见下） | `Ran 31 tests in 0.541s` / `FAILED (failures=6, errors=4)` | `91f58cc5de26bfdd74460f7e1fa266ddfba308aaa479f4f4aa4a64df8a3456e2` |
| (a) 重试 | captured | 1 | 0.615067 | `Ran 31 tests in 0.551s` / `FAILED (failures=6, errors=4)` | `82a1a1c13140cfcdeaad5ab96413f22a45b3d2675ae7a36182020e08ef699e32` |
| (b) | captured | 1 | 0.613242 | `Ran 31 tests in 0.550s` / `FAILED (failures=1)` | `8026871fc8c029057db373d0720de69f54d386669a771ec3685f9a02f0593458` |
| (c) | captured | 1 | 0.615068 | `Ran 31 tests in 0.552s` / `FAILED (failures=10)` | `37a310b2ed8a5c63c02daedf08f237c31dc750e23ac94dcab26d4d26583236ac` |
| (d) | captured | 1 | 0.596832 | `Ran 31 tests in 0.539s` / `FAILED (failures=10)` | `0335fc4fafd7bcc27b28a49d3bc05c2aaacd4bc79e0ccfff79d91a8166f098a7` |
| (e) | captured | 1 | 0.585979 | `Ran 31 tests in 0.527s` / `FAILED (failures=2)` | `7a86715868ab31157bbaacecbbca25887892af51d1d0a120e6b1eb7360863d15` |

(a) 的首次与重试，把耗时替换成常量后的 sha256 都是 `a7c11b40d8fcd31570d790e49e705ea3bad1602e738413c9d7b1b91159ab26ed`。首次失败保留：测试进程已经写完 FAILED 日志，随后记录器用错了探针字符串的百分号格式化，抛 `TypeError: not enough arguments for format string`，因此没有记外层耗时和退出码。重试是同一种源码改动，退出码 1。

### (a) 白名单多放一个内部字段 — captured

改动：在 offer schema 增加 `private_key`，并在投影里从内部记录拷贝该字段。临时副本上的探针显示公开 offer 含有该键且值非空；非空无标记目录仍拒绝。

抓住它的测试：

- `test_fixture_contains_all_canaries_and_projection_removes_them`
- `test_projection_matches_handwritten_expectation_and_preserves_input`
- `test_unknown_keys_rejected_at_every_object_level`（level=`offer`，key=`private_key`，`ValueError not raised`）
- `test_build_writes_valid_exact_public_data_and_copies_stylesheet`
- `test_cli_build_succeeds_and_produces_both_pages_and_valid_data`
- `test_entire_build_output_has_no_internal_canaries_or_private_json_keys`
- `test_handwritten_valid_dto` 与白名单负向测试的恢复断言，因为该字段变成必填后，手写期望对象缺少它

摘录：`ValueError: $.offers[0]: missing ['private_key']`；未知键子测试 `AssertionError: ValueError not raised`。

### (b) 去掉某个必填字段的校验 — captured

改动：计算 missing 之后 `missing.discard('post_id')`。探针 `PROBE_MISSING_POST_ID allowed`。其他目录保护探针仍拒绝。

抓住它的测试：`test_missing_required_fields_rejected`（level=`offer`，key=`post_id`）。

```text
AssertionError: ValueError not raised
Ran 31 tests in 0.550s
FAILED (failures=1)
```

其余必填字段的子测试仍然报错，所以整次运行只有这 1 个失败。

### (c) 去掉目录保护里的标记检查 — captured

改动：删掉“非空且标记不是文件则拒绝”整段。清空循环还在，因此无标记的非空目录会被直接重建。符号链接检查还在。

探针：`PROBE_BUILD allowed`，`PROBE_PRECIOUS False`，`PROBE_NOTES False`；符号链接输出仍然拒绝，目标里的文件还在。

抓住它的测试（10 个失败子测试）：

- `test_build_refuses_nonempty_directory_without_marker_and_leaves_existing_files`
- `test_cli_build_refuses_nonempty_directory_without_marker`
- `test_cli_build_refusal_exit_nonzero_for_unsafe_out` 的 `unmarked_nonempty`

摘录：

```text
AssertionError: ValueError not raised : unmarked nonempty output must be refused before deletion
AssertionError: False is not true : precious.txt must survive refusal
AssertionError: False is not true : keep/notes.txt must survive refusal
AssertionError: True is not false : refusal must not write a site
AssertionError: 0 == 0 : CLI build must reject unmarked nonempty output
```

`symlink` 这一 CLI 子情况没有失败，因为符号链接检查还在。这符合只改标记检查的预期。

### (d) 清理时不检查标记就先删 — captured

改动：在原来的拒绝判断之前，只要目录存在就先 `rmtree`/`unlink` 全部子项。判断留在删除之后，此时目录已经空了，判断不会再拒绝。

探针与 (c) 相同（探针日志 sha256 都是 `c74a0eca340630a5052caea4c1937e40359cca5f1aacf55fdc640f1fb7e6e016`）：无标记非空目录被清空。符号链接路径仍在删除前被拒绝。

失败集合与 (c) 相同，10 个子测试。测试日志 sha256 与 (c) 不同。摘录同样是 `precious.txt must survive refusal` 和 CLI 退出码变成 0。

### (e) 符号链接检查失效 — captured

改动：`if component.is_symlink()` 改为 `if False and component.is_symlink()`。

探针：无标记非空目录仍拒绝，文件还在。符号链接输出抛出的是无标记目录的 `ValueError`，消息里没有 symlink；目标文件还在。也就是说，这条变异被测试发现了，但“非空且无标记”那一层仍然挡住了这次删除。

抓住它的测试：`test_build_refuses_symlink_out_and_path_containing_symlink` 的 `out_is_symlink` 与 `path_contains_symlink`。

```text
ValueError: output directory is not a public-dto build output; refusing to delete existing files
AssertionError: "(?i)(symlink|symbolic|符号链接)" does not match "output directory is not a public-dto build output; refusing to delete existing files"
Ran 31 tests in 0.527s
FAILED (failures=2)
```

覆盖缺口（不把本项改成 missed）：`test_cli_build_refusal_exit_nonzero_for_unsafe_out` 的 `symlink` 子情况没有失败。CLI 只断言退出码非 0，无标记目录的拒绝仍然使退出码非 0。API 测试断言错误文案含 symlink，所以整组仍然失败。

探针 sha256：

| 探针 | sha256 |
| --- | --- |
| (a) 重试 | `aec7b84d56d103fa1815bc5225ea155faf41b647f0d61b341bbf3c1260344990` |
| (b) | `e1ef1d7a80f7be6c4897154904fe4e92ebb4a2f0ff356c4f53830b5c72cfd93e` |
| (c) | `c74a0eca340630a5052caea4c1937e40359cca5f1aacf55fdc640f1fb7e6e016` |
| (d) | `c74a0eca340630a5052caea4c1937e40359cca5f1aacf55fdc640f1fb7e6e016` |
| (e) | `af7e979ca470116e6458f7f590e6baf3f3d5fd7243f80bf4864c7f63bf0df7fa` |

## 4. 残留风险

状态：**failed**。两条描述都能复现，删除触发比它们更宽（缺陷 D2）。

`build_public_site` 是这个模块里唯一会删除输出内容的路径。`scan_public_output` 和 `scan` 子命令只读。删除循环在第 223–228 行，门闩是第 220–222 行。

### 无关目录里手工放了标记文件，会被清理

与描述一致，已复现。临时目录里放了 `precious.txt`、`keep/notes.txt`、`user-data.txt`，并写入普通文件 `.public-dto-build`（内容为构建标识）。`build_public_site` 成功，这三个用户文件都不在了，目录变成一套新的站点文件，标记文件仍在。

标记内容不必等于官方字符串。内容写成 `not the official marker` 的普通文件同样会清空目录。这仍是“放了一个叫这个名字的标记文件”，没有超出该条描述。

### 扫描失败后标记文件残留

与描述一致，已复现。从空目录构建，摘要里放入 https 图片 URL。构建在扫描阶段抛：

```text
SCAN_FAIL_EMPTY ValueError: .../data.json: forbidden original image URL
SCAN_FAIL_EMPTY_MARKER exists=True is_file=True content='public-dto/v1 build output\n'
```

标记写在 `scan_public_output` 之前（第 269–270 行）。失败后标记还在，同时 html、`data.json`、`style.css` 也留下，其中仍含有那张图片 URL。描述只点了标记残留；失败产物一并留下，但这不是额外的删除。

若目录在构建前已经有标记和用户文件，扫描失败时用户文件已经没了，新标记还在：

```text
SCAN_FAIL_MARKED ValueError: .../data.json: forbidden original image URL
SCAN_FAIL_MARKED_USER_SURVIVED False
SCAN_FAIL_MARKED_MARKER True
```

这是第一条先授权清空，然后才发生第二条。清空不取决于扫描成功。空目录上的扫描失败不会先删用户文件，因为清空前目录是空的。

### 更宽的删除触发

缺陷 D2。`.public-dto-build` 若是指向普通文件的符号链接，`is_file()` 跟随链接后为真，拒绝被跳过，目录被清空。链接目标文件本身还在。

```text
MARKER_SYMLINK result=allowed
MARKER_SYMLINK_OUTSIDE_EXISTS True
```

清空后的目录快照只剩站点文件，原有 `precious.txt` 不在。

没有授权清空的对照：

```text
MARKER_IS_DIR ValueError: ... refusing to delete existing files
MARKER_IS_DIR_PRECIOUS True
MARKER_SYM_DIR ValueError: ... refusing to delete existing files
MARKER_SYM_DIR_PRECIOUS True TARGET True
```

标记若是目录，或符号链接指向目录，则拒绝，用户文件和链接目标都保留。

已标记目录内部的目录符号链接和文件符号链接，在合法重建时被摘掉，链接外面的 `do-not-delete.txt` 内容仍是 `OUTSIDE`。这次没有沿着符号链接删到目录外面。

因此，比两条描述更宽的路径是：输出目录里不必有一个真实的标记文件，只要有一个指向普通文件的同名符号链接，就会清空该目录。

## 缺陷

### D1 扫描跳过含 NUL 或非法 UTF-8 的 data.json

- 严重度：中
- 状态影响：第 2 项 failed
- 位置：`/tmp/pr2-verify/head/vps_pipeline/public_dto.py` 的 `scan_public_output`，第 107–113 行。`UnicodeDecodeError` 或源码含 `\x00` 时 `continue`。同一函数第 124–125 行才会对非法 JSON 的 `data.json` 抛错，前面的跳过使它到不了。
- 复现：对 FX-001 做一次成功构建；给 `data.json` 的 offer 加上 `evidence` 对象后，在文件末尾加一个 NUL 字节；或把 `data.json` 换成非法 UTF-8 字节。对输出目录调用 `scan_public_output`。本次结果是 `NUL_SCAN result=allowed_BYPASS` 与 `BADUTF8_SCAN result=allowed_BYPASS`。同一目录在扫描失败探针里，未加 NUL 的图片 URL 仍会被拒绝（`SCAN_FAIL_DATA_HAS_IMAGE True`）。
- 正常 `build_public_site` 写出的是已通过 `validate_public_dto` 的 UTF-8，不会自己制造这个旁路。旁路影响的是事后 `scan`，以及任何先改 `data.json` 再依赖扫描发现泄漏的用法。

### D2 指向普通文件的标记符号链接会授权清空

- 严重度：中
- 状态影响：第 4 项 failed
- 位置：同文件第 220 行，`(out / '.public-dto-build').is_file()`
- 复现：见上一节。需要对该输出目录有写权限，和手工放标记文件是同一前提，但触发物不必是标记文件本身。

### D3 同一套餐的多条价格或多条 GB6 取第一条，不记冲突

- 严重度：低
- 状态影响：不改变 2.2 的 passed。指定的“价格缺失”和“多套餐”没有走这条分支。
- 位置：同文件第 147–151 行，`next(...)` 只取第一条匹配的 price 和 `geekbench6_single`
- 复现：同一 `plan_id` 再追加一条 amount 99 的价格。结果仍是 amount 10 的第一条，`conflict_flags` 仍是 `[]`。再追加一条 GB6 值为 1 的观测，公开值仍是 1420，冲突列表仍空。

```text
PRICE_MULTI_FIRST {"amount": 10, "currency": "USD", ... "price_status": "known"}
PRICE_MULTI_CONFLICTS []
MULTI_OBS value=1420 conflicts=[]
```

### D4 输出路径是普通文件时抛 NotADirectoryError

- 严重度：低
- 位置：同文件第 220 行的 `out.iterdir()`
- 复现：`--out` 指向一个已存在的普通文件。结果 `OUT_IS_FILE NotADirectoryError`，文件内容仍是 `file-content`。没有删除。

## 未单独采集或未跑的部分

- 变异 (a) 首次的外层耗时和进程退出码：未采集。测试输出已完整，重试补上了退出码 1。
- 变异副本上的全库 `discover`：unrun。见第 3 节。
- 没有对并发替换（检查与删除之间的 TOCTOU）做测试。
- 没有联系作者线程，没有推送，没有修改 pull request。
