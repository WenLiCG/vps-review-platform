# VPS 评测：现状 brief

核对日期：2026-11-07。只读核对 GitHub 上的 `main` 与 [PR #1](https://github.com/WenLiCG/vps-review-platform/pull/1)。没有改仓库、没有采集、没有部署。

合成契约在 `/cursor/stores/self/internal/vps-review-offline-spec.zip`，已读到。全部 `FX-*` 都是人工构造，用来对照字段规则。它们不是 NodeSeek 帖子。附件里的 README 写过「参考仓库仍不可访问、网站开发未开始」；以当前 GitHub 仓库为准，那两句已经过时。

## 已核实

### main

| 项 | 事实 |
|---|---|
| 仓库 | `https://github.com/WenLiCG/vps-review-platform` |
| 分支 | `main` |
| SHA | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` |
| 说明 | Complete 0.2.0 public catalog baseline data |
| 提交时间 | 2026-10-09 08:31:01 -0700 |

`git fetch` 之后，`origin/main` 仍是这个 SHA。先前说的 `f7b3584` 现在还成立。

`main` 是 Python 3.11+ 标准库流水线（`pyproject.toml` 的 `dependencies` 为空）加静态站 `website/dist`。`website/dist/data.json` 的 `counts` 为 **120** 篇帖、**128** 条对象（`items`）。数据自己写明对象含复测、套餐和主机，`uniqueMachines` 为 `null`。离线测试在 `main` 上能数到 19 个 Python 测试文件、约 306 个 `test*` 方法，另有 Node 筛选脚本。`scripts/run_offline_checks.py` 展开后是 12 条命令。仓库里的 `validation/publication-checks.json` 记录的是 **2026-10-09** 那次通过（后端 259、桥接 40、采集技能 7、筛选 66/22/7、进程 117）。那份记录早于本 PR。

### PR #1

| 项 | 事实 |
|---|---|
| 状态 | `open`，非 draft，`merged: false` |
| 头分支 | `cursor/offline-contract-first-batch-ad64` |
| head SHA | `9861fdab8625eaab376e59b01d7cc150807708c8` |
| 提交 | Add offline contract helpers for filenames, time, and currency.（2026-11-06 15:52:48 UTC） |
| 相对 main | merge-base 就是 `f7b3584`；超前 1、落后 0 |
| 变更 | 71 个文件，+3594 / −18 |
| GitHub 合并判定 | `mergeable: true`，`mergeable_state: clean` |
| CI | 仓库没有 GitHub Actions workflow。该 head 的 check-runs 为 0。`gh pr checks` 返回 no checks reported。combined status 为 `pending`，statuses 为空 |

`website/dist`、`docs/`、`validation/` 不在这 71 个文件里。已发布的筛选 JSON 没有被这支 PR 改写。

GitHub 当前把这个 PR 标成可合并、无冲突。没有自动化检查结果。这里只记录这个事实。

## 首批实际完成

代码在 PR head 的 `vps_pipeline/offline_contract.py`，测试在 `tests/test_offline_contract.py`。合成样例在 `tests/fixtures/offline-spec/`。本轮在 `/tmp` 的只读副本上执行了这一个测试模块：**9 项 OK**（Python 3.12.3）。

这些函数吃的是已经写好的 `expected.normalized.json`，再核对文件名、时区、单位、分桶和币种。它们不把 `raw.excerpt.txt` 解析成整篇文档。例外是推广链接函数会读原文，并且忽略其中的 URL。

与先前声称一致、且本轮对过代码和单测的项：

- **文件名**：价格、周期、地点、核/内存/盘、测试日期。缺了就用 `unknownPrice` / `unknownLoc` / `unknownCfg` / `unknownDate`，并在缺日期或重名时加上 `__{source_post_id}`。续费月付优先于首期价（FX-006 文件名是 `12USD-mo_…`，不用 1 USD 首期）。FX-001、002、003、004、005、006、007、009、010、012 的实际文件名与 expected 相同。FX-002 的文件名已是 `MULTI_东京_unknownDate__synth-002`。
- **时区**：只有明确偏移、`Z`/`UTC`/`GMT`，或写明北京时间，才换成 `+08:00`。发帖时间不填进测试时间。裸日期和含糊的 `CST` 保持 `tested_at_beijing: null`，`tz_confidence` 为 `inferred_weak`。FX-005 的 `2025-06-03T17:30:00Z` 换成 `2025-06-04T01:30:00+08:00`。
- **原单位**：`retain_unit` 保留 GB 与 GiB。FX-007 磁盘 50 GiB、流量 1000 GB，互不改写。
- **线路标签**：只保留来源已经写下的标签。路径里只有 AS4809 时，不补 `CN2_GIA`（FX-010）。
- **样本去重**：Geekbench 6 单核按 `run_id` 计一次。FX-012 同一 run 两行 1420，样本数为 1，中位数 1420。稳定标签列表在这批函数里保持为空；满 5 次也不会写出 `#线路稳定`。
- **Benchmark 主版本分桶**：FX-009 把 Geekbench 5 与 6 分开放进两个桶。
- **推广链接空配置**：未传入 `https://` URL 时结果为 `null`。正文里的链接不会被捡起来。`main` 上 `vps_pipeline/analysis.py` 仍要求分析稿的 `affiliate_url` 为 `null`。
- **缺币种不默认 USD**：`normalize_price` 在币种为空，或备注写明未写币种/默认 USD 时，币种为 `null`、状态 `unknown`、月均价为 `null`。`bridge/public_adapter.py` 把这类月价投影成 `currency: null`、不可筛选，金额仍保留。注明「刀」的 USD 和注明欧元的 EUR 仍可进入筛选。`skills/vps-review-analyze` 与 vendor 副本的字段说明已改成同一句。公开站里已经写成 USD 的历史数字还在 `website/dist`，因为该目录没有进这支 PR。

## 明确未完成

- **FX-002 多套餐仍未进现有分析模型。** expected 有两个套餐（东京：1 GB / 20 GB / 5 USD，以及 4 GB / 40 GB / 24 USD），测试时间为空。`vps_analysis_adaptation("FX-002")` 返回 `adapted: false`，不挑选其中一个。`main` 的目录映射仍要求 `reviewed_object_count == 1`（`vps_pipeline/analysis.py`、`catalog_adapter.py`）。文件名的 `MULTI_` 前缀已经有了，缺的是两套套餐事实都能留下。
- **FX-003 双候选仍未同时保存。** expected 把正文 `2GB`（候选 2048）和图片预期 `4.0 GiB`（候选 4096）放在 `conflicts[].values`，`resolution` 为 `keep_both`，`memory_mb` 为 `null`。适配函数返回 `adapted: false`。现有 `conflict` 状态要求字段值为 `null`，不能连带两个候选和 `resolution` 一起入库。
- **三份日期 fixture 不能算通过。** 它们的 `tz_confidence` 已是 `inferred_weak`，expected 仍写成北京时间零点：
  - FX-008A：原文 `2025-06-03`，expected 北京时间 `2025-06-03T00:00:00+08:00`，文件名 `…_20250603__synth-008a`。函数文件名是 `…_unknownDate__synth-008a`。
  - FX-008B：同一日期，后缀 `__synth-008b`，差异相同。
  - FX-011：原文 `2025-01-14`，expected 北京时间 `2025-01-14T00:00:00+08:00`，文件名含 `20250114`。函数文件名含 `unknownDate`。
  - 测试断言的是「函数结果与这三份 expected 不相等」。9 项 OK 只说明拒绝被记下来了。`DATA_CONTRACT.md` 第 4.3 节写明时区不明就不猜成北京时间；这三份 expected 与该节不一致。`vps_analysis_adaptation` 对这三例返回 `adapted: true`，那个标志只表示它们不在「多套餐 / keep_both」拒绝名单里。
- **契约里还有、这批函数没有做的产品目标**：按 `assets/<post_id>/` 归档真实首帖、下载远程正文图、从原文生成结构化文档、仓库根目录每帖一份标准命名 Markdown、流媒体测试的时间与证据、线路按三网和方向建档、benchmark 的完整参数、网站用用户自备推广链接做筛选。fixture 里的 `streaming` 都是空数组，`offline_contract.py` 没有对应函数。
- **满样本后的 `#线路稳定` 标签**没有实现。去重本身已在首批里。

## 项目目标

下面是目标，不是完成记录。

- 把 NodeSeek 评测首帖归档到内部 `assets/<post_id>/`。
- 下载远程正文图。
- 把图文整理成结构化字段。
- 根目录为每帖保留一份 Markdown。
- 标准文件名包含价格、周期、地点、核/内存/盘和测试日期；缺失留空位，不编造。
- 测试时间只在时区明确时换成北京时间。
- 套餐事实、价格快照，与历次测评观测分开存放。
- 线路按三网和方向记录；benchmark 保留版本与参数；流媒体测试带时间和证据；冲突双方都留着。
- 网站筛选使用用户自己提供的推广链接。用户还没有提供，链接保持为空。
- 论坛采集只覆盖公共首帖的低频试验。用户说明已有 5 篇。这不表示第三方原文或图片可以公开转载。版权和图片占位继续作为风险保留。不再跑联网采集。

## 下一批验收门槛

不重复上一节已经对齐的文件名、明确时区换算、原单位、线路标签、run 去重、空推广位、缺币种和 GB5/GB6 分桶。

1. **FX-002**：同一帖的两个套餐事实都留下。不把 5 USD 或 24 USD 收成整帖的唯一当前值。目录侧要能表达「一帖两个套餐」，现有的 `reviewed_object_count == 1` 过不了这道门槛。`MULTI_` 文件名已对齐，不作为这道门槛。
2. **FX-003**：正文 `2GB` 与图片预期 `4.0 GiB` 同时保留，`resolution` 为 `keep_both`，`memory_mb` 仍为 `null`。不选取 2048 或 4096。
3. **FX-008A、FX-008B、FX-011**：仅日期且 `inferred_weak` 时，`tested_at_beijing` 为 `null`，文件名日期段为 `unknownDate`。现在的 expected 仍是北京零点加 `20250603` / `20250114`。在 expected 改成与第 4.3 节一致之前，这三例保持未通过。验收不能靠把断言改成「等于当前 expected」来变绿。FX-011 的「样本不足不打稳定标签」已由去重函数核对（样本数 0、标签空），那一部分不重复做。

## 阻碍

- 现有 `vps-analysis/1` 每个字段一个当前值，新帖目录映射只接受一个核读对象。FX-002 和 FX-003 要进筛选站，得先有能放下两套餐和双候选的位置。
- 弱时区三例的 expected 与契约第 4.3 节相反。收口前需要定哪一份为准。
- 这个仓库没有 CI。PR 的「可合并」只来自 GitHub 无冲突判定。
- 公开转载原文和作者图片的权利还没有在仓库里结案。附件只转述了一份采集授权，本轮没有看到 PDF 原件。
- 用户还没有给出推广链接。

## 必须由用户决定

- PR #1 是否合并。当前事实是：开着、无冲突、GitHub 认为可合并、没有任何 check run。
- 仅有日期的测试时间，是否允许写成北京时间零点。契约正文写不猜测；三份 expected 写成了零点。
- 是否提供自备推广链接。未提供则槽位继续为空。
- 第三方原文和图片能否公开转载。采集试验范围是否仍只限公共首帖。用户所说的已有 5 篇，本轮没有在 Git 树里找到对应归档。

## 未能核实

- 先前 cloud agent 所说的「12 步离线检查全部通过」没有在本轮重跑。本轮只跑了 `tests.test_offline_contract` 的 9 项。PR 正文里的 268 / 41 / 66 / 22 / 7 / 117 与「main 旧记录 + 这批新增测试」的数目对得上，那是算术，不是本轮执行结果。
- 「已有 5 篇」公共首帖试验没有在仓库里对到 `assets/<post_id>/`。本轮没有联网去找。
- 附件里的采集授权 PDF 没有随包附上，签名未核。
- 没有打开筛选站，也没有做浏览器验收。

## 建议任务

- **核对 main 与 PR** — 已完成。结论见上文 SHA、PR 状态和首批范围。
- **文件名缺值不编造** — 已完成。十例文件名与 expected 一致；三例弱时区除外。
- **明确时区才换算** — 已完成。裸日期保持 null。
- **容量保留原单位** — 已完成。GB 与 GiB 分开。
- **线路标签不臆造** — 已完成。AS4809 不写成 CN2 GIA。
- **同运行样本去重** — 已完成。同一 `run_id` 只计一次。
- **版本分桶不合并** — 已完成。Geekbench 5 与 6 分开。
- **推广位保持为空** — 已完成。空配置不产生链接。
- **缺币种不默认美元** — 已完成。未知币种为 null，且不能进数值筛选。
- **一帖保留两套餐** — 待办。FX-002 的两个套餐都入库，且不选出唯一当前价。
- **冲突双方都保留** — 待办。FX-003 同时留下 2GB 与 4.0 GiB，内存字段保持 null。
- **复跑十二条离线检查** — 待办。在 PR head 上跑完 `scripts/run_offline_checks.py` 并留下当次结果。
- **决定是否合并 PR** — 等用户决定。
- **裁定仅日期时区** — 等用户决定。定下之后，三份 expected 与测试按同一规则对齐。
- **确认原文图片权利** — 等用户决定。
- **提供自备推广链接** — 等用户决定。未提供则继续为空。
