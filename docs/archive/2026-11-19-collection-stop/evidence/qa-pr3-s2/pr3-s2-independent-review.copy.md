---
cursor:
  subagentId: "bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79"
---

# PR 3 / S2 独立只读复验

仓库 `https://github.com/WenLiCG/vps-review-platform`，pull request `https://github.com/WenLiCG/vps-review-platform/pull/3`，分支 `s2-contract-v2`。

本文件只给质量结论。没有推送，没有改 PR，没有评论，没有采集真实帖子。

## 结论

**fail**

范围、v1 字节、D2 日期和 344 OK 都成立。失败点是价格 `keep_both`：公开 `price_status` 被置为 null 后，public-dto/v2 不接受这个类型，投影在出页之前抛错。端口 `keep_both` 能把值置 null 并在详情页写出「端口未选定」，但仓库没有这条端到端测试。按本轮口径，缺这条端到端覆盖至少是中危，计入 fail。

| 项 | 状态 |
| --- | --- |
| 开始和结束时 head 仍是 `dc4ffc71` | passed |
| 1. 文件范围与 RED→GREEN | passed |
| 2. 契约版本号 | passed |
| 3. v1 字节与分析侧文件 | passed |
| 4. 多套餐、冲突页、keep_both | failed |
| 5. D2 日期 | passed |
| 6. 全量 344 OK 与变异 | passed |
| 7. 离线 spec 位置 | passed（只记录，不作待决冲突） |

## 环境与检出

- Python `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`
- 系统 `Linux cursor 6.12.113+ #1 SMP PREEMPT_DYNAMIC Thu Nov 12 16:05:37 UTC 2026 x86_64 GNU/Linux`

开始：

```text
git ls-remote https://github.com/WenLiCG/vps-review-platform.git refs/pull/3/head refs/heads/s2-contract-v2
dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e	refs/heads/s2-contract-v2
dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e	refs/pull/3/head
```

结束时同一条命令仍然是这个 SHA。

独立目录：

```text
git clone --local /workspace /tmp/pr3-s2/head
git -C /tmp/pr3-s2/head checkout --detach dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e
git -C /tmp/pr3-s2/base checkout --detach 5a06d684381ab8e74adfc2dcc129ed9ff163c410
```

| 项 | SHA |
| --- | --- |
| head | `dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e` |
| head tree | `596672e3529abf1ddb4939029530d7c55c9be7df`（前缀 `596672e3`） |
| base `s1-public-dto-v1` | `5a06d684381ab8e74adfc2dcc129ed9ff163c410` |
| base tree | `b8f38499f01f8ffd4e787a828bf8109dc192c88b` |

## 1. 范围与顺序

状态：**passed**。`git diff --name-status 5a06d684..dc4ffc71` 是 19 个文件，与作者所说的个数一致。没有六维筛选页面，没有 capture CLI。`docs/CONTRACT-v2.md` 写明本契约不实现捕获 CLI 或六维筛选。

顺序是 RED、GREEN、RED、GREEN。两次 GREEN 的 `tests/` 都是空的。

| 提交 | 说明 | tests/ |
| --- | --- | --- |
| `185a54ac4dd965a90ecafd9b8ae665bb367dc040` | S2 RED：失败测试与空模块 | 有 |
| `f91581841e6b125176d2074d670b2f46185b6869` | S2 GREEN：契约实现 | 无 |
| `c88b7e987270114be14fac648b04432f316455be` | S2 RED：keep_both 封闭测试 | 有 |
| `dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e` | S2 GREEN：keep_both 通用映射 | 无 |

文件：`docs/CONTRACT-v2.md`，四份 schema（capture-manifest/v1、price-semantics/v2、public-dto/v2、review-document/v2），8 个 `tests/fixtures/contract-v2/`，3 个测试模块，`vps_pipeline/contract_v2.py`，以及修改后的 `vps_pipeline/public_dto.py`。`schemas/public-dto/v1/` 不在 diff 里。

## 2. 版本号

状态：**passed**。这些字符串都在对应产物里：`contract/v2`（文档和 `CONTRACT_V2_VERSION`）、`review-document/v2`、`public-dto/v1`、`public-dto/v2`、`capture-manifest/v1`、`price-semantics/v2`。后五个 schema 的 `properties.schema_version.const` 与常量一致。

去掉或改错实例里的版本号，校验失败：

```text
VERSION review-missing ValueError: invalid review document version
VERSION review-wrong ValueError: invalid review document version
VERSION capture-missing ValueError: $: missing fields
VERSION capture-wrong ValueError: $.schema_version: invalid version/value
VERSION price-missing ValueError: $: missing fields
VERSION price-wrong ValueError: $.schema_version: invalid version/value
VERSION dto-v2-missing ValueError: $: missing fields
VERSION dto-v1-missing ValueError: $: missing ['schema_version']
```

`contract/v2` 是契约名称，不是某一份 JSON schema 的 const。删掉文档标题不会触发 schema 校验器。五个带 schema 的版本号会。

## 3. v1 字节

状态：**passed**。base 与 head 上这些文件字节相同：`FX-001.internal.json`、`website/public-dto-v1/` 的 data.json、index、详情页、style.css、`schemas/public-dto/v1/public-dto.schema.json`、`tests/test_analysis.py`、skills 与 vendor 两处的 `contract.md` 和 `fields.json`。

两边用同一份 FX-001 各构建一次，五个产物 sha256 逐项相同，并与已提交的 `website/public-dto-v1/data.json` 相同（`2f37717280c36f57c08cc9cb2c4e5a60e9f6ae53c3e396eae3e91e09d923038b`）。`BUILD_TREES_EQUAL True`。

## 4. 多套餐与 keep_both

状态：**failed**。

FX-002 详情页同时有 A、B，`价格快照` 与 `观测摘要` 各出现 2 次。FX-003 公开 `memory_mb` 为 null，页面有「内存未选定」，候选 2GB / 4.0 GiB 还在。磁盘夹具 FX-S2-DISK 有端到端测试，断言「磁盘未选定」。

仓库测试里，端口和价格没有「冲突 → 公开值为 null → 详情页「{label}未选定」」的端到端用例。`MAPPING_ROWS` 只核对常量和文档表格。

独立探针：

- 端口：`port_speed_mbps` 为 null，页面含「端口未选定」。价格快照和观测摘要仍是分开的标题。磁盘值 40 没有被这次端口冲突清掉。
- 未映射字段 `fictional_widget`：`ValueError: unmapped conflict field: fictional_widget`。
- 价格：在 FX-002 的合法价格对象上把冲突字段改成 `amount`。投影抛 `ValueError: $.offers[].price.price_status: invalid type`。没有生成详情页。

原因：`contract_v2.py` 在 keep_both 时把 `price.price_status` 也写成 null，而 `schemas/public-dto/v2/public-dto.schema.json` 里 `price_status` 的 type 只是 string，枚举没有 null。空价格列表不会编造金额，`price_status` 为 `unknown`，`observations_summary.geekbench6_single` 为 null。

### 缺陷

**价格 keep_both 无法出页。** 严重度：高。

- 位置：`/tmp/pr3-s2/head/vps_pipeline/contract_v2.py` 第 16–19 行和第 235–242 行；schema 第 200–207 行。
- 复现：取 FX-002 的一个套餐，保留合法 `prices[]`，在对应观测上放 `field: amount`、`resolution: keep_both` 的两条候选，调用 `project_review_document_to_public_dto`。
- 影响：价格冲突这条核心路径到不了「价格为 null、详情页显示价格未选定」。调用方得到校验错误，站点不会发布。

**端口 keep_both 没有端到端测试。** 严重度：中。

- 位置：`tests/test_contract_v2_keep_both.py` 只有磁盘页面断言；端口只出现在 `MAPPING_ROWS`。
- 复现：在仓库测试里搜索「端口未选定」，没有匹配。独立探针可以把端口冲突做成页面，但现有测试不会在这条回归时失败。
- 影响：端口映射或页面标签改坏时，全量测试仍可能是绿的。

## 5. D2

状态：**passed**。

只有日期的 FX-008A、FX-008B、FX-011：`tested_at_beijing` 为 null，`tz_confidence` 和 `review_date_tz` 为 unknown，精度为 day，文件名日期段是 `20250603` 或 `20250114`。`matches_review_date_filter('2025-06-03','2025-06-01','2025-06-30')` 为 True，七月区间为 False。没有日期的 FX-004 文件名含 `unknownDate`，不用 `published_at`。

FX-005 的 `2025-06-03T17:30:00Z` 得到 `2025-06-04T01:30:00+08:00`，时区 explicit，文件名 `20250604`。`tests/test_contract_v2.py` 里的期望是写死的字符串 `'2025-06-04T01:30:00+08:00'`，不是把同一个函数的返回值再比一次。

非法日期的实际行为：

```text
ILLEGAL '2025-13-40' ValueError: month must be in 1..12
ILLEGAL 'not-a-date' ValueError: Invalid isoformat string: 'not-a-date'
ILLEGAL '2025/06/03' ValueError: Invalid isoformat string: '2025/06/03'
ILLEGAL '2025-06-03T25:00:00Z' ValueError: hour must be in 0..23
ILLEGAL '' ValueError: Invalid isoformat string: ''
ILLEGAL '2025-06-03T17:30:00' RESULT review_date=2025-06-03, tested_at_beijing=null, tz_confidence=unknown, filename_date_segment=20250603
```

没有时区的时间不会被猜成北京时间，但时钟部分被丢掉，只留日历日。这不是 D2 的失败项，记在这里。

## 6. 全量与变异

状态：**passed**。目录 `/tmp/pr3-s2/head`。

```text
python3 -B -m unittest discover -s tests
```

| 遍 | 外层秒 | 退出码 | sha256 |
| --- | --- | --- | --- |
| 1 | 7.709903 | 0 | `7b6d3d22d30937dedcc08ad6b5335ee056df15f4ded61d734bfc5da80f96c473` |
| 2 | 7.460770 | 0 | `33c681bfa071ce8545cf2914f64f713607d5c418cb46630fb533f39b3404a1f4` |

两遍都是 `Ran 344 tests in …` / `OK`。去掉耗时后 sha256 都是 `badbeccbc5f0ca1c16f30c59086b3569ae93d6dc7cc306f86455a85330a7c9b2`。

变异都在临时副本，跑的是同一条全量命令，跑完删除。没有 missed。

| 变异 | 结果 | 退出码 | 外层秒 | 汇总 | sha256 |
| --- | --- | --- | --- | --- | --- |
| (i) 去掉冲突处理 | captured | 1 | 7.405080 | `FAILED (failures=3)` | `0f3ea116e922caa728683120050bf65ee82576de27b46defe2f2473122841716` |
| (ii) 只投影一个套餐 | captured | 1 | 7.716701 | `FAILED (failures=2)` | `5b742a9258ebb808e0469d96238ca7e94883f3f66436e292189ace1562fedc51` |
| (iii) 只有日期改成北京零点 | captured | 1 | 7.476728 | `FAILED (failures=7)` | `40a173a175c2b35ef835880d86e95e1ff23532663998702534be4e81fe5cb68f` |
| (iv) 去掉 schema_version | captured | 1 | 7.906691 | `FAILED (errors=11)` | `69a9b665140a4b328599d96a987c64657fdc8057695c0e1dcea6f67f2fa477ba` |
| (v) keep_both 只处理内存 | captured | 1 | 7.612292 | `FAILED (failures=2)` | `096e6821374bdbd255b8afdb78ac5a36b976ff504c0a37edc61c0fcc50282a89` |
| 自选：未映射冲突不抛 ValueError | captured | 1 | 7.533539 | `FAILED (errors=1)` | `1ce4a4b39402011028e51e2414ad6a66f611d6976e6ef77223a6e636b4764193` |
| 自选：v1 摘要被改动 | captured | 1 | 7.429661 | `FAILED (failures=10)` | `5834e289c8b2bac40efcb12d1decef535dcc4026abf04041f74ba057db2582c1` |

(iii) 的摘录是 `AssertionError: '2025-06-03T00:00:00+08:00' is not None`。(ii) 是 `['FX-002-A'] != ['FX-002-A', 'FX-002-B']`。未映射那次在去掉显式 `ValueError` 后，后续映射查找变成 `KeyError: 'fictional_widget'`，测试仍然失败。

## 7. 离线 spec 位置

状态：**passed**。PM 已作废「只有日期时转北京零点并标 inferred_weak」，以 D2 为准。这里只记位置。

- `/cursor/stores/self/internal/vps-review-offline-spec.zip` 内 `vps-review-offline-spec/DATA_CONTRACT.md` 第 72 行列出 `tz_confidence` 可取 `inferred_weak`；第 74 行写「时区不明：不硬猜为北京时间」。
- 同包 `fixtures/cases/FX-008A/expected.normalized.json`、`FX-008B/expected.normalized.json`、`FX-011/expected.normalized.json` 的 `observations[0]` 把仅日期写成北京零点，`tz_confidence` 为 `inferred_weak`。例如 FX-008A：`tested_at_raw` `2025-06-03`，`tested_at_beijing` `2025-06-03T00:00:00+08:00`。

## 探针与重试

探针日志 `/tmp/pr3-s2/logs/probe.log`，sha256 `69e37fe33cf6bc49011df3b95c65c2e37c772a6adcc5b0c7594c7608ae086a05`。价格探针第一次把 `evidence` 写成数组，schema 先拒绝了类型；改成 FX-002 那种 evidence 对象后，才暴露 `price_status` 类型错误。这是探针夹具的第一次失败，产品缺陷以上面第二次为准。全量和变异没有产品重试。

## 未覆盖

- S3 六维筛选和 S4 capture CLI 不在本 PR，没有测。
- 并发、跨盘 `EXDEV`、umask 窗口没有重做。
- 没有时区的完整时间字符串只记了实际行为，没有单独的验收断言。
- v2 投影把 `geekbench6_single` 固定写成 null，没有把历史观测数值抄进摘要。这次夹具也没有要求抄过去。
