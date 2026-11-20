# VPS PR #2 fix1 独立复验结论（质量建议，非合并批准）

- 时间：2026-11-13 10:08（Asia/Shanghai）
- PR：https://github.com/WenLiCG/vps-review-platform/pull/2 ，分支 s1-public-dto-v1
- head：de9ea46aa2d8887f0a4c60d8a8f3a28fb7b21b57（tree 233142911a7fae5ea92331aa6d37317a8400188e），前一 head 1586ebef，base main f7b35842
- 作者：Codex 程序员；审查线程 bc-6194c9a7-7dd7-59dd-96c4-159fb6a47a79（只读，未推送、未改 PR、未评论）
- 依据报告：pr2-fix1-independent-review.copy.md（sha256 1f0ac97b9a77e3e4f1d54f6b3b79fe9dbc7b3e38348d5e84dc7f493e1b1dfcd5）

## 结论：fail（按 PM 规则：残留会被读到即报中危）

| 项 | 状态 |
| --- | --- |
| 实时 head 仍为 de9ea46a | passed |
| diff 只改 3 个文件（+238/−12） | passed |
| D1 NUL/非法UTF-8 拒绝不跳过 | passed |
| D2 非普通标记（符号链接/目录/FIFO）拒绝且不删文件 | passed |
| D3 冲突置 null + `price: N values` / `geekbench6_single: N values`；完全相同不算冲突；输入不改写；按 plan_id 隔离 | passed |
| D4 `--out` 为普通文件明确拒绝、字节不变 | passed |
| 全新独立检出全量两遍 `Ran 300 tests` / OK | passed |
| 6 个变异全部被抓（退出码 1，无 missed） | passed |
| PR 描述写明 TOCTOU 残留（按 PM 保留） | passed |
| 扫描失败后的残留不会被当合格输出 | failed（D5） |

## 新缺陷 D5（中）
`build_public_site` 先写完 data.json、页面、CSS 和 `.public-dto-build`（文本与成功构建相同），再 `scan_public_output`；扫描失败（退出码 1）不清理。复现：摘要含合成图片 URL 构建新目录 → 退出码 1，但目录是完整静态站，`validate_public_dto(data.json)` 接受，静态读取 index/data/offer 均 HTTP 200 且含该 URL。公开字符串含 NUL 的 build 同样留下 schema 可通过的 data.json。
缓解：同目录合法重建会整目录替换；`scan` 会拒绝；仓库内无发布脚本读取该目录。
修复方向供参考（由作者/PM 定）：先写临时目录、扫描通过后再原子替换；或失败时删除产物/写失败标记。

## 未覆盖
合法 UTF-8 中非 evidence/非图片 URL 的敏感字符串；TOCTOU 并发试验；仓库外发布/CI 拷贝；变异后未重跑手工探针。Windows/真实部署不涉及。
