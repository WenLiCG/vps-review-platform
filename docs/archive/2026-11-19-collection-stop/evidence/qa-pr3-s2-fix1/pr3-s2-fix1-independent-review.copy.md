---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 3 S2 fix1 独立只读复验

仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/3`。

本文件只给质量结论。没有推送，没有改 PR，没有评论。

## 结论

**fail**

`amount` 和整个 `price` 冲突可以投影，详情页有「价格未选定」，`price_status` 为 `unresolved_conflict`，schema 不接受 null。`currency`、`billing_period_months`、`term_role`、`monthly_equivalent` 的投影是对的，但详情页在取中文标签时 `KeyError`，站点出不来。另外，价格冲突顺手清空非冲突字段 `vcpu` 的变异没有被测试抓住。

| 项 | 状态 |
| --- | --- |
| 开始和结束时 head 仍是 `afe0bb47` | passed |
| 1. 范围、GREEN 不改测试、v1 字节 | passed |
| 2. 价格 keep_both 探针 | failed |
| 3. 端口与 amount 的端到端测试 | passed |
| 4. D2 文档与无时区完整时间 | passed |
| 5. 全量两遍 349 OK | passed |
| 6. 变异 | failed（`clear-vcpu` missed） |
| price_status 自身冲突样例 | 没有；失败封闭可接受，见未覆盖 |

## 环境与检出

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`

开始和结束：

```text
git ls-remote https://github.com/WenLiCG/vps-review-platform.git refs/pull/3/head
afe0bb473eacdcb66a48b9434c0cdb34467dfd0a	refs/pull/3/head
```

独立检出：

```text
git clone --local /workspace /tmp/pr3-fix1/head
git -C /tmp/pr3-fix1/head checkout --detach afe0bb473eacdcb66a48b9434c0cdb34467dfd0a
```

| 项 | SHA |
| --- | --- |
| head | `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a` |
| head tree | `f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d` |
| 上一轮 head | `dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e` |
| RED | `292019321a7a4719dd221188353aba080203bb3e` |
| GREEN | `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a` |

## 1. 范围

状态：**passed**。相对 `dc4ffc71` 是 6 个文件，168 行增、15 行删。RED 只改两个测试文件。GREEN 改 `docs/CONTRACT-v2.md`、两份 v2 schema、`vps_pipeline/contract_v2.py`，`tests/` 为空。

`git diff --stat dc4ffc71..afe0bb47 -- schemas/public-dto/v1 website/public-dto-v1 tests/fixtures/public-dto tests/test_analysis.py skills/vps-review-analyze/references vps_pipeline/vendor/vps-review-analyze/references` 没有输出，这些 v1 和分析侧文件字节未变。

这 6 个文件对应上轮的四件事：价格冲突状态、端口端到端、价格端到端、D2 文档和无时区完整时间。没有新的筛选页或 capture CLI。

## 2. 价格 keep_both

状态：**failed**。探针 `/tmp/pr3-fix1/probe.py`，日志 sha256 `5dab89a1084a82dc3c67efca81f195fcbbdf1b99886b44b78c4d31f70bec0da0`。夹具是 FX-002 的内存副本。

两个 schema 的 `price_status` 都是 `type=string`，枚举都是 `known`、`unknown`、`partial`、`unresolved_conflict`，不含 null。`docs/CONTRACT-v2.md` 写了 `unresolved_conflict`。把投影结果的 `price_status` 改成 null 再校验：`ValueError: $.offers[].price.price_status: invalid type`。

| 冲突字段 | 被清空 | 保留 | price_status | 详情页 |
| --- | --- | --- | --- | --- |
| amount | amount、monthly_equivalent | USD、1、renewal、vcpu=1 | unresolved_conflict | 「价格未选定」 |
| price | amount、currency、周期、角色、月均 | vcpu=1 | unresolved_conflict | 「价格未选定」 |
| currency | currency | amount 5、周期、角色、月均 5.0 | unresolved_conflict | `KeyError: 'price.currency'` |
| billing_period_months | 周期、月均 | amount 5、USD、renewal | unresolved_conflict | `KeyError: 'price.billing_period_months'` |
| term_role | term_role | amount、USD、周期、月均 | unresolved_conflict | `KeyError: 'price.term_role'` |
| monthly_equivalent | 月均 | amount、USD、周期、renewal | unresolved_conflict | `KeyError: 'price.monthly_equivalent'` |
| price_status | 不投影 |  |  | `ValueError: unmapped conflict field: price_status` |

同一帖两个套餐、只在 A 上放 amount 冲突：A 的 amount 和月均为 null，状态 `unresolved_conflict`；B 仍是 24 USD、12 个月、月均 2.0、`known`。

### 缺陷

**部分价格别名无法生成详情页。** 严重度：高。

- 位置：`/tmp/pr3-fix1/head/vps_pipeline/public_dto.py` 详情页循环，用 `KEEP_BOTH_PUBLIC_FIELDS[field][0]` 去 `KEEP_BOTH_FIELD_LABELS` 取标签。标签表只有 `price.amount`，没有 `price.currency`、`price.billing_period_months`、`price.term_role`、`price.monthly_equivalent`。
- 复现：用 FX-002 的套餐 A，把观测冲突字段分别设为这四个名字，`resolution` 为 `keep_both`，调用 `build_public_site`。
- 影响：投影本身已把对应字段置 null，但建页抛 `KeyError`，扫描和替换不会发生，页面上不会出现「价格未选定」。`amount` 和整个 `price` 不受影响，因为它们的第一条路径是 `price.amount`。

`price_status` 作为冲突字段会失败封闭。仓库和离线包里没有这种样例，所以这个报错按补充口径可以接受，不另记缺陷。

## 3. 端到端测试

状态：**passed**。`tests/test_contract_v2_s2_fix1.py` 的 `single_fx002()` 从 `tests/fixtures/contract-v2/FX-002.json` 深拷贝。`test_price_amount_keep_both_end_to_end` 断言 amount 为 null、`price_status` 为 `unresolved_conflict`、月均为 null、币种周期角色仍在，再 `build_public_site` 后检查可见文本含「价格未选定」。`test_port_keep_both_end_to_end` 同样从该夹具走到 `offers/FX-002.html`，断言端口为 null 且可见「端口未选定」。全量里这两项通过。它们不覆盖上面四个会 `KeyError` 的别名。

## 4. D2

状态：**passed**。`docs/CONTRACT-v2.md` 的「D2 日期」写明离线规格里只有日期转北京零点并标 `inferred_weak` 的规则作废，仅日期保持 unknown 和 null，完整时间要有显式时区才换算。

无时区字符串 `2025-06-03T17:30:00`：

```text
tested_at_beijing=null
tz_confidence=unknown
review_date=2025-06-03
review_date_precision=day
tested_at_raw 仍为 2025-06-03T17:30:00
```

`test_timezone_free_full_timestamp_preserves_clock_evidence` 里的日期和原文是写死的 `'2025-06-03'` 与 `'2025-06-03T17:30:00'`，输入文档在投影后与投影前相等，证据里的 `17:30:00` 还在。

## 5. 全量

状态：**passed**。目录 `/tmp/pr3-fix1/head`。

```text
python3 -B -m unittest discover -s tests
```

| 遍 | 外层秒 | 退出码 | 用例行 | sha256 |
| --- | --- | --- | --- | --- |
| 1 | 7.553873 | 0 | `Ran 349 tests in 7.317s` / `OK` | `b3831fb82bc25d4907e1c94d09f67b3b2cf08133874def61db175bf248b7f56d` |
| 2 | 7.458663 | 0 | `Ran 349 tests in 7.247s` / `OK` | `1d9327f64b80754cd73d342996fe19df52273045aab26de1217d2597151b9f86` |

## 6. 变异

状态：**failed**。临时副本，全量命令，跑完删除。作者的 3 个和「amount 不清月均」「截断原文」被抓住。「价格冲突时把 vcpu 也清空」没有被抓住。

| 变异 | 结果 | 退出码 | 外层秒 | 汇总 | sha256 |
| --- | --- | --- | --- | --- | --- |
| price_status 改回 None | captured | 1 | 7.329218 | `FAILED (errors=1)` | `9ed7df63c37980f20b637bfe92463d3af46fae0c9d5991833a114a4b6a77368e` |
| 「未选定」改成「待选定」 | captured | 1 | 7.657257 | `FAILED (failures=3)` | `ea7b713ecb11f0f306d1cd7bd03057f8421a1fcb353fd3064d3ae4f52548165f` |
| 删掉 `port` 别名 | captured | 1 | 7.591264 | `FAILED (failures=1, errors=1)` | `218fe842e00e8b241234893f42b082d26fa64d5f67b44c25c6e72429f4815e8e` |
| amount 冲突不清 monthly_equivalent | captured | 1 | 7.524624 | `FAILED (failures=2)` | `3af8c0a92812956b40f94145f1adb9aa31ab8119f9371086a9e342f69ff1f4a9` |
| 价格冲突时把 vcpu 置 null | missed | 0 | 7.880930 | `Ran 349 tests in 7.671s` / `OK` | `0e65125dac892837898119f3fa9e4d85c1322f571ae85a995df53290c21b7fe0` |
| 无时区原文截成日期 | captured | 1 | 7.886265 | `FAILED (failures=1)` | `1ea70a67f80a72c6403a3bbc52d7b027fc3ef00dc4ec631270d17691297d867e` |

摘录：`price_status` 为 null 时 `ValueError: $.offers[].price.price_status: invalid type`。删端口别名时 `ValueError: unmapped conflict field: port`。不清月均时 `AssertionError: 5.0 is not None`。截断原文时 `AssertionError: '2025-06-03' != '2025-06-03T17:30:00'`。

## price_status 自身冲突样例

没有。失败封闭 `ValueError: unmapped conflict field: price_status` 可以接受。

搜过：

```text
rg -n "price_status" /tmp/pr3-fix1/head/tests/fixtures
rg -n '"field"' /tmp/pr3-fix1/head/tests/fixtures --glob '*.json'
```

夹具里 `price_status` 只在 `tests/fixtures/public-dto/FX-001.internal.json` 作为普通值 `known`。冲突字段只有 FX-003 的 `memory` 和 FX-S2-DISK 的 `disk`。

离线包用 Python 读 `/cursor/stores/self/internal/vps-review-offline-spec.zip`，只看 `fixtures/cases` 与 `DATA_CONTRACT.md` 里的 `.json`、`.md`、`.txt`，搜索 `price_status` 和 `unresolved_conflict`，命中数是 0。唯一带冲突字段的期望文件是 FX-003 的 `expected.normalized.json`，字段不是 `price_status`。

## 首次失败与重试

探针第一次跑到 `currency` 的 `build_public_site` 就因 `KeyError: 'price.currency'` 退出，后面的字段没跑到。这是产品缺陷，不是夹具写错。补上页面异常捕获后重跑，六个价格字段、另一套餐、null 校验和无时区时间都记在同一份日志里。全量和变异没有重试。

## 未覆盖

- 无 `price_status` 自身冲突样例。当前会按未映射字段失败封闭。
- 价格冲突误清另一个套餐：这次只验证了 amount 冲突不清 B 套餐，没有把「误清另一套餐」做成被测试抓住的变异。
- `currency` 等四个别名的页面 `KeyError` 没有现成测试，所以全量 349 仍是 OK。
- 价格冲突顺手清空 `vcpu` 的变异 missed。
