# VPS Review Collection QA停止开发交接

2026-11-19 11:24 PST（America/Los_Angeles）。按用户本群要求停止开发，完成handoff后更新GitHub。本次只整理历史证据，不编码、不复测、不采集、不部署。
接手：PM汇总，由既有项目唯一更新负责人归档GitHub；QA不改作者分支、不重复推送。

## 项目与入口
仓库：https://github.com/WenLiCG/vps-review-platform
唯一执行Project：https://cursor.com/agents/bc-1dfb3b68-390d-59b9-9e8d-02ceff9b3d97
保留VPS-1/VPS-2原台账。PR1仅既有上下文，不从加入项目推导新编码授权。
本次未实时核对远程分支/PR/head，以下为明确绑定历史候选的独立结论，不能直接当当前远程状态。当前作者工作目录、分支、diff及未提交文件由开发handoff提供，QA不补猜。

## 可核实的历史独立QA
1. PR2 fix3：https://github.com/WenLiCG/vps-review-platform/pull/2
head `5a06d684381ab8e74adfc2dcc129ed9ff163c410`，tree `b8f38499f01f8ffd4e787a828bf8109dc192c88b`，历史质量pass（不是用户批准）。D6回滚/备份删除失败语义、5个变异通过，全量309 OK两遍；D1–D5按当时PM范围skipped，不能称全部重新验证。EXDEV、并发读者、umask0、TOCTOU等未覆盖见原报告。时间为2026-11-12 18:56 PST（原文件记2026-11-13 10:56 Asia/Shanghai）。
2. PR3 S2 fix1：https://github.com/WenLiCG/vps-review-platform/pull/3
head `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a`，tree `f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d`，历史质量fail。
高严重度：currency/billing_period_months/term_role/monthly_equivalent价格子字段keep_both后，详情页标签映射抛KeyError、站点不能生成。
中严重度测试缺口：价格冲突误清非冲突vcpu的变异未被349单测捕获。历史全量349 OK两遍不抵消上述失败；6个变异仅抓住5个。
时间2026-11-12 20:00 PST（原文件记2026-11-13 12:00 Asia/Shanghai）。未覆盖price_status自身冲突样例、误清另一套餐变异等见报告。
审查经原Project独立上下文执行，未参与作者Codex实现；作者自测不算独立QA。

## 证据和停止边界
随包复制了本QA现有qa-pr*目录中的原报告/结论，保持原文，包含首次失败、重试、环境、命令输出和限制。当前交接未新跑测试；不把历史报告日期当本次执行时间。
目标仍包括证据/冲突保留，缺值不猜，多套餐及事实/历史价格观测分离；未经恢复授权不采集或改变冲突规则/范围。
QA当前没有运行中的任务。用户本次归档要求不等于合并、发布或新一轮修复批准；后续恢复须另有明确授权。

## GitHub完成判据
在既有项目记录归档本handoff、开发handoff及经过敏感检查的必要证据，提供真实提交SHA和可访问文件链接，不能只留共享电脑绝对路径；保留历史fail/未测与当前状态未知的边界。本QA尚未执行或核实GitHub更新。
方法software-handoff v1.3、software-release-gate v1.0；不表示远端工具已安装。

## 本次复制证据SHA256
- `evidence/qa-pr2/VPS-PR2-VERDICT-20261113.md`：`23973fb073a001481491d640f938d1103bbc8c17f63e1a782f634a8b09a0eef5`
- `evidence/qa-pr2/pr2-independent-review.copy.md`：`f2b0a1ad391bb026333f65c44e00c90676a87bc672c124c8d22b4224c03680a7`
- `evidence/qa-pr2-fix1/VPS-PR2-FIX1-VERDICT-20261113.md`：`0a42481345a5072ce7a8bb3ba7554ed92f3ebed74460565ed070710380b0616f`
- `evidence/qa-pr2-fix1/pr2-fix1-independent-review.copy.md`：`1f0ac97b9a77e3e4f1d54f6b3b79fe9dbc7b3e38348d5e84dc7f493e1b1dfcd5`
- `evidence/qa-pr2-fix2/VPS-PR2-FIX2-VERDICT-20261113.md`：`17ca440964d508e78d4390f6590ae0dc383e62607f4f58a8a263d13c9f915f13`
- `evidence/qa-pr2-fix2/pr2-fix2-independent-review.copy.md`：`28006555598f63e8b59d27311ed96bce1ca06689a0265871557214dc0f5578eb`
- `evidence/qa-pr2-fix3/VPS-PR2-FIX3-VERDICT-20261113.md`：`c083a174bb8eedeebd49f8e822786f3f56fa963300c64d47cc61b6e254328397`
- `evidence/qa-pr2-fix3/pr2-fix3-independent-review.copy.md`：`e42f95d707f53fcdab49c43447fe2e3f4ddbba06962053b8ad5982884c4f85ce`
- `evidence/qa-pr3-s2/VPS-PR3-S2-VERDICT-20261113.md`：`dddb8d5194581fbf23e608ddfffdd9d97a88085649e6e3f895a1442ab6d37d45`
- `evidence/qa-pr3-s2/pr3-s2-independent-review.copy.md`：`199bc2a689cc75262b69ba73c789da1c6c5cef02fc57a3b9e37a99297f5dd5c8`
- `evidence/qa-pr3-s2-fix1/VPS-PR3-S2-FIX1-VERDICT-20261113.md`：`5643ff5bbbaba4e2cac9cff91bf87efb0c3fc55830c20d042e7e2b8b18778e79`
- `evidence/qa-pr3-s2-fix1/pr3-s2-fix1-independent-review.copy.md`：`b63f75db5cdc0597a8341e3eb3d6c0f5603ccc4cad49af3c038a0941a47109ec`
