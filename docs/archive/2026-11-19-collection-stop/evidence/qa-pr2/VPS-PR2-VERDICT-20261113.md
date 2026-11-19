# VPS Review PR #2 独立结论（测试与Review）
时间：2026-11-13 09:00:26 Asia/Shanghai
PR：https://github.com/WenLiCG/vps-review-platform/pull/2  head s1-public-dto-v1@1586ebefd6450c0a38775f90e9e0f3baf6085f0e  base main@f7b35842c94d2ab77e3d2bd23f559cafc8b41929
依据：执行 Project bc-1dfb3b68 的独立只读线程 bc-6194c9a7 报告 docs/pr2-independent-review.md（副本 sha256 f2b0a1ad391bb026333f65c44e00c90676a87bc672c124c8d22b4224c03680a7）

## 结论：fail（需修复后复验）——质量建议，不是合并批准
- passed：作者结果复跑（定向 31 OK ×2，全库 290 OK ×2，base 259，差额 31）；白名单投影默认拒绝；缺时区/缺价格/多套餐不臆造；列出的目录拒绝路径；5 项变异全部 captured；SHA 核对。
- failed：代码审查（D1）；残留风险与描述一致且不更宽（D2）。
- unrun：变异副本全库 discover；检查与删除之间的 TOCTOU 并发替换。

## 缺陷
- D1 中：scan_public_output（public_dto.py 107–113）遇 NUL 或非法 UTF-8 直接跳过文件，data.json 带 evidence 也不被拒绝（NUL_SCAN / BADUTF8_SCAN allowed_BYPASS）。正常构建不触发，影响事后 scan 作为泄漏后闸。
- D2 中：public_dto.py:220 用 is_file() 跟随符号链接；名为 .public-dto-build、指向普通文件的符号链接即可授权清空整个输出目录，比 PR 声明的残留风险更宽。
- D3 低（按项目规则请 PM 定级）：同一套餐多条价格或多条 GB6 观测静默取第一条，conflict_flags 仍为空（147–151）。项目要求保留证据与冲突，S1 范围内是否必须修由 PM 决定。
- D4 低：--out 为普通文件时抛 NotADirectoryError 而非明确拒绝，未删文件。

## 复验范围（修复后锁定新 head）
D1、D2 定向探针 + 新增测试的变异可发现性；若 D3 纳入，再验多价格/多观测冲突标记；全库回归。
