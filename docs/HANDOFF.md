# 停止开发交接（2026-11-19）

仓库：https://github.com/WenLiCG/vps-review-platform
分支：`docs/collection-stop-handoff`（从当时的 `origin/main` 拉出，只增加本目录下的文档）
归档目录：`docs/archive/2026-11-19-collection-stop/`
只读核对时间：2026-11-19T20:05:12Z 之前已完成 `git fetch` 与 `gh pr view`；下表是这次提交之前的读数。

本文件是停止交接，不是质量复验，不是合并批准，也不是恢复开发的授权。本次没有跑测试，没有采集，没有改产品代码、测试、schema、网站或流水线。

批准包内的 QA 停止交接写明方法为 software-handoff v1.3，并提到 software-release-gate v1.0。包内没有单独的 software-handoff 规范正文，也没有 software-team-workflow 1.4 的规范正文。本交接按停止任务点名的章节书写。不发布。

## 已确认范围

- 只归档文档。正文放进本仓库，不把仓库外路径当作证据的唯一副本。
- 收录已批准的 QA 停止包正文：QA 停止交接、包内清单、12 份历史报告/结论。源压缩包 66753 字节，SHA256 `b4432711b14140c5156c0ae43459cb6708d6f84b7b312f104e75c6190d4ae5b8`。包内 `MANIFEST.md` 的 SHA256 为 `b373e7bcda8ab2ae5e07b5986d324eea48e67937df0bc12e8afc81f371a8a72d`。
- 另收录 7 份既有执行记录的正文，用来补充开发状态。未知保持「未知」。不根据这些记录新写实现。
- 包内没有当前开发侧停止交接。作者当时的工作目录、未提交 diff、本地分支：未知。
- S2（PR #3）保持暂停。
- 历史独立结论和 2026-11-19 的远程 SHA 分开写。历史 pass 或 fail 都不是本次新结论，也不是用户批准。
- 不合并、不部署、不发布、不付款、不采集、不改冲突规则或范围。

## 生成方式

1. 使用前核对源压缩包大小为 66753 字节、SHA256 为上一节的值。两者都相符之后才解包。
2. 包内 14 个正文按原字节复制到 `docs/archive/2026-11-19-collection-stop/`，路径与包内相对路径一致。复制后的 SHA256 与包内清单一致。
3. 7 份执行记录按原字节复制到 `docs/archive/2026-11-19-collection-stop/execution-records/`。其中 6 份独立复验报告与包内同名 `.copy.md` 的 SHA256 相同。`project-brief.md` 只出现在执行记录里。
4. 远程只读：`gh pr view` 读取 PR #1、#2、#3 的 state、isDraft、base、head；`git fetch` 上述头分支和 `main`；`git rev-parse <ref>` 与 `git rev-parse <ref>^{tree}` 取完整 SHA。没有 checkout 这些产品分支，没有推送它们。
5. 文件清单见 `docs/archive/2026-11-19-collection-stop/ARCHIVE-FILE-MANIFEST.md`。清单列出本归档每个已收录文件的路径、字节数和 SHA256，并再次写下源压缩包 SHA256。清单文件自身的 SHA256 写在提交说明里，避免把自身哈希写进自身。

## 候选

下表是本次文档提交之前的远程只读结果。产品 PR 与 `main` 不是本次要推进的候选。本次唯一新候选是文档分支 `docs/collection-stop-handoff`，基线为当时的 `origin/main`。

| 对象 | state | isDraft | base 分支 | base SHA | head 分支 | head SHA | tree SHA |
|---|---|---|---|---|---|---|---|
| `origin/main` | 分支尖端，不是 PR | 不适用 | 不适用 | 不适用 | `main` | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` | `ffe2b7a0a0bb8bbf629d10b987aeed3668ce750d` |
| PR #1 | OPEN | false | `main` | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` | `cursor/offline-contract-first-batch-ad64` | `9861fdab8625eaab376e59b01d7cc150807708c8` | `6e3564b2e3dce4738fe5589a848825ea26790b9b` |
| PR #2 | OPEN | true | `main` | `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` | `s1-public-dto-v1` | `5a06d684381ab8e74adfc2dcc129ed9ff163c410` | `b8f38499f01f8ffd4e787a828bf8109dc192c88b` |
| PR #3 | OPEN | true | `s1-public-dto-v1` | `5a06d684381ab8e74adfc2dcc129ed9ff163c410` | `s2-contract-v2` | `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a` | `f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d` |

PR 链接：

- https://github.com/WenLiCG/vps-review-platform/pull/1
- https://github.com/WenLiCG/vps-review-platform/pull/2
- https://github.com/WenLiCG/vps-review-platform/pull/3

历史审查点与上表对照（历史结论保持为历史结论）：

- PR #2 fix3 历史独立复验：**pass**。审查点 head `5a06d684381ab8e74adfc2dcc129ed9ff163c410`，tree `b8f38499f01f8ffd4e787a828bf8109dc192c88b`。2026-11-19 只读到的 PR #2 head 与 tree 和该审查点相同。本次没有复测。相同 SHA 不是新的 pass，也不是用户批准。D1–D5 在该次审查按当时范围 skipped。EXDEV、并发读者、umask 0、TOCTOU 未覆盖，见归档报告。
- PR #3 S2 fix1 历史独立复验：**fail**。审查点 head `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a`，tree `f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d`。2026-11-19 只读到的 PR #3 head 与 tree 和该审查点相同。本次没有复测。S2 保持暂停。缺陷仍以该历史报告为准：价格别名在 keep_both 之后详情页 KeyError（标签表只有 `price.amount`）；把非冲突 `vcpu` 置空的变异没有被当时的 349 项单测抓住。

更早的 PR #2、fix1、fix2 与 PR #3 S2 原文在归档里保留。可引用的历史终态是上一节两行，不把中间 fail 或更早的结果写成当前结论。

## 已做未做

### 这次归档做了

- 把 QA 停止包和 7 份执行记录的正文写入本仓库。
- 只读记录 PR #1、#2、#3 和 `origin/main` 的 state、draft、base、head、tree。
- 写明 S2 暂停，以及恢复须另有用户明确授权。

### 这次归档没做

- 没有跑测试，没有复验任一 head。
- 没有采集，没有写 NodeSeek、Notion 或其他外部服务。
- 没有实现修复，没有改冲突规则。
- 没有合并、部署、发布或付款。
- 没有补写一份当时不存在的开发侧停止交接。作者工作区状态：未知。
- 没有把 2026-11-07 或 2026-11-13 的结论改记成 2026-11-19 的新结论。

### 执行记录里的开发状态（历史）

完整正文在 `docs/archive/2026-11-19-collection-stop/execution-records/`。下面只摘状态，不代替原文。

`project-brief.md` 的核对日期是 2026-11-07，对象是当时的 `main` 与 PR #1。它记录的 `main` SHA `f7b35842c94d2ab77e3d2bd23f559cafc8b41929` 和 PR #1 head `9861fdab8625eaab376e59b01d7cc150807708c8` 与 2026-11-19 只读结果相同。该 brief 里的测试是当时那一轮，本次没有重跑。因此 PR #1 在 2026-11-19 的独立质量结论：未知。

该 brief 写明当时已经对齐的项：文件名缺值不编造、时区明确才换算、容量保留原单位、线路标签不臆造、同一次运行去重、Geekbench 5 与 6 分桶、空推广配置不产生链接、缺币种不默认美元。当时未完成：FX-002 两个套餐都留下、FX-003 冲突双方都留下、FX-008A / FX-008B / FX-011 的 expected 与「时区不明不猜北京时间」不一致、流媒体时间与证据、满样本后的「线路稳定」标签、十二条离线检查在该 head 上的当次重跑。用户决定项在该文里包括：是否合并 PR #1、仅日期是否允许写成北京时间零点、是否提供推广链接、原文和图片能否公开转载。这些决定在本次收录的材料里没有新的用户批复。推广链接：该 brief 称未提供；此后收录的记录没有写「已提供」。

PR #2 的历史链（都不是 2026-11-19 的新复验）：

- 首次独立复验，head `1586ebefd6450c0a38775f90e9e0f3baf6085f0e`：fail。D1 扫描遇 NUL 或非法 UTF-8 会跳过文件；D2 标记符号链接可以授权清空输出目录。
- fix1，head `de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57`，tree `233142911a7fae5ea92331aa6d37317a8400188e`：fail。D5，扫描失败后的残留仍可能被当成完整站点。
- fix2，head `d8c41af4301e53304faad44df062435b0021666b`，tree `0ba3198adc74019372cbff6667246e1beb6e7e9b`：fail。D6，去掉「替换失败后还原备份」的变异没有被抓住。
- fix3，head 与 tree 见上一节：历史 pass。这是 PR #2 可引用的历史终态。PR 在 2026-11-19 仍是 OPEN Draft，未合并。

PR #3 的历史链：

- S2，head `dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e`，tree `596672e3529abf1ddb4939029530d7c55c9be7df`：fail。价格 keep_both 把 `price_status` 写成 null，公开 schema 不接受，页面出不来；端口 keep_both 缺端到端测试。
- S2 fix1，head 与 tree 见上一节：历史 fail。这是 PR #3 可引用的历史终态。详情页对 `price.currency`、`price.billing_period_months`、`price.term_role`、`price.monthly_equivalent` 在 keep_both 后 KeyError，标签表只有 `price.amount`。价格冲突时把非冲突 `vcpu` 置空的变异未被抓住。全量 349 OK 两遍不抵消该 fail。

S2 审查记录写明：PM 已作废「只有日期就转成北京时间零点并标 inferred_weak」，以 D2 为准。这是那份历史报告里的记录，不是本次新决定。

## 未解决项

- S2 暂停在历史 fail 的同一 head 上。两个缺陷都未在本次处理：价格别名 keep_both 的详情页 KeyError；价格冲突误清非冲突 `vcpu` 的测试缺口。
- 该次未覆盖项仍未覆盖：`price_status` 自身冲突样例；误清另一套餐的变异。历史报告写当前对 `price_status` 自身冲突是失败封闭。
- PR #2 历史 pass 的未覆盖项仍未覆盖：EXDEV、并发读者、umask 0、TOCTOU。D1–D5 没有在 fix3 那一轮全部重测。
- PR #1、PR #2、PR #3 在只读时都是 OPEN，都没有合并。是否合并：未知，须用户决定。本次不合并。
- PR #1 的 2026-11-19 独立质量：未知。
- 当前开发侧工作目录和未提交改动：未知。
- 2026-11-19 的 CI / check-runs：未知。本次没有再查。`project-brief.md` 只记录了 2026-11-07 时 PR #1 没有 check run。
- 仅日期的时区口径、推广链接、原文与图片的公开转载：本次没有新的用户决定。沿用执行记录里的未决或历史记录，不补猜。
- 十二条离线检查在 PR #1 head 上的当次重跑：brief 记为未做。本次也未做。

## 恢复须用户明确授权

下面任何一件都要另有用户明确授权。本交接、本归档提交和随之打开的 Draft PR 都不是授权：

- 恢复编码或修复 S2
- 采集，或改变冲突规则、采集范围
- 合并 PR #1、#2 或 #3
- 部署、发布或付款
- 把历史 pass 当作当前通过并继续往下做

在该授权出现之前：S2 保持暂停，三个产品分支保持本次只读时的 tip，不从本文件推导新的实现任务。
