# VPS PR #3 S2 fix1 独立复验结论（2026-11-13 12:00 Asia/Shanghai）

- PR：https://github.com/WenLiCG/vps-review-platform/pull/3（Draft，未授权合并）
- head：afe0bb473eacdcb66a48b9434c0cdb34467dfd0a（tree f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d），开始与结束均核对一致；作者 Codex
- 执行：独立审查线程 bc-6194c9a7（经协调 Project bc-1dfb3b68），只读，未推送、未改 PR
- 依据报告：pr3-s2-fix1-independent-review.copy.md（sha256 b63f75db5cdc0597a8341e3eb3d6c0f5603ccc4cad49af3c038a0941a47109ec）
- 环境：Python 3.12.3，Linux 6.12.113+ x86_64

## 质量结论：fail（质量建议，非用户批准）

| 项 | 状态 |
| --- | --- |
| 范围、RED 只改测试、GREEN 不改 tests/、v1 字节不变 | passed |
| 价格 keep_both（amount、整个 price） | passed |
| 价格 keep_both（currency / billing_period_months / term_role / monthly_equivalent） | failed（建页 KeyError） |
| price_status schema 不接受 null、枚举含 unresolved_conflict | passed |
| 端口与 amount 端到端测试 | passed |
| D2 文档、无时区完整时间保留原文 | passed |
| 全量两遍 | passed（349 OK ×2） |
| 变异（6 个） | failed（5 captured，clear-vcpu missed） |
| price_status 自身冲突样例 | 夹具与离线 spec 均无，失败封闭可接受，列入未覆盖 |

## 缺陷

1. 高：price 子字段别名 currency、billing_period_months、term_role、monthly_equivalent 发生 keep_both 冲突时，投影正确置 null 且 price_status=unresolved_conflict，但 public_dto.py 详情页用 KEEP_BOTH_PUBLIC_FIELDS[field][0] 查 KEEP_BOTH_FIELD_LABELS，标签表只有 price.amount，抛 KeyError: 'price.currency' 等，站点不生成。复现：FX-002 套餐 A，冲突字段设为上述任一，resolution=keep_both，调用 build_public_site。
2. 中（测试缺口）：变异「价格冲突时把非冲突字段 vcpu 置 null」全量仍 349 OK，未被抓住。上面 4 个别名也无测试。

## 未覆盖

- price_status 自身冲突样例（无样例，当前 ValueError 失败封闭）
- 「误清另一个套餐」未做成变异（探针已验证 amount 冲突不影响 B 套餐）

## 首次失败与重试

探针首次在 currency 建页 KeyError 处退出（产品缺陷），加异常捕获后重跑全部字段；全量与变异无重试。

## 建议修复

补齐四个价格别名的标签（或按冲突字段而非首条路径取标签），并为四个别名各加端到端测试，加一条断言保证价格冲突不清空 vcpu 等非价格字段。修复后复验受影响项并重跑全量与变异。
