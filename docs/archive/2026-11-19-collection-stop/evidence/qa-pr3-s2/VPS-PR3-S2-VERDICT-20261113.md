# VPS PR #3 / S2 契约 v2 独立审查结论（质量建议，不是用户批准）

- 时间：2026-11-13 11:37（Asia/Shanghai）
- PR：https://github.com/WenLiCG/vps-review-platform/pull/3（Draft，作者 Codex 程序员）
- head dc4ffc717bd12877ba9b9763856b6fcf41e8ea5e，tree 596672e3529abf1ddb4939029530d7c55c9be7df；base 5a06d684（tree b8f38499）。开始和结束时 head 未变。
- 审查执行：协调 Project bc-1dfb3b68 → 审查线程 bc-6194c9a7（与作者线程 bc-778fb6bb 隔离），只读，不推送不评论。
- 依据报告：pr3-s2-independent-review.copy.md，sha256 199bc2a689cc75262b69ba73c789da1c6c5cef02fc57a3b9e37a99297f5dd5c8
- 环境：Python 3.12.3，Linux x86_64，独立 clone 检出

## 结论：fail

| 项 | 状态 |
|---|---|
| 1 文件范围（19 个）与 RED→GREEN 顺序 | passed |
| 2 契约版本号（5 个 schema const + 去掉/改错均拒绝） | passed |
| 3 v1 字节兼容（FX-001 两 SHA 构建 5 产物 sha 一致） | passed |
| 4 多套餐、冲突页、keep_both | **failed** |
| 5 D2 日期（含 FX-005 写死常量对照） | passed |
| 6 全量 344 OK ×2；7 个变异（5 作者 + 2 自选）全抓 | passed |
| 7 离线 spec 位置（只记录，PM 已定 D2 为准） | passed |

## 缺陷（交 Codex 修复，同一轮）

1. **高｜价格 keep_both 无法出页**：contract_v2.py 第 16–19、235–242 行在 keep_both 时把 price.price_status 写成 null，public-dto/v2 schema 第 200–207 行 price_status 只允许 string，投影抛 `ValueError: $.offers[].price.price_status: invalid type`，详情页不生成，站点发布中断。复现：FX-002 一个套餐，保留合法 prices[]，观测上放 field=amount、resolution=keep_both 两条候选，调用 project_review_document_to_public_dto。
2. **中｜端口 keep_both 无端到端测试**：仓库里搜「端口未选定」无匹配，端口只在 MAPPING_ROWS 常量核对。独立探针显示当前行为正确，但回归不会被抓到。按 PM 口径计入 fail。修复时价格也需补端到端测试（null + 「价格未选定」）。

## 观察（不计失败）
- 无时区的完整时间 `2025-06-03T17:30:00` 被降为日精度、北京时间 null，不猜北京时间，但时钟部分丢失；无单独验收断言。
- v2 投影 geekbench6_single 固定 null。
- 离线 spec 位置：DATA_CONTRACT.md 第 72、74 行；FX-008A/FX-008B/FX-011 expected.normalized.json。

## 未覆盖
S3 六维筛选、S4 capture CLI（不在本 PR）；并发、EXDEV、umask 未重做。

## 下一步
Codex 修复后推新 head，我对新 head 复验：价格/端口 keep_both 端到端、全量回归、受影响变异。合并由用户决定。
