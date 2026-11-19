# VPS Review Collection 停止开发归档清单（安全附件）

整理时间：2026-11-19，America/Los_Angeles（PST，UTC−8）。
整理范围：只复制并敏感检查既有 QA 停止交接及其 evidence/ 12 份历史报告，不改实现、不复测、不采集、不上传 GitHub、不操作 CloudAgent 或仓库。
方法：software-handoff v1.3。本清单是归档说明，不是新的质量结论。

## 项目与入口
- 项目：VPS Review Collection
- 仓库：https://github.com/WenLiCG/vps-review-platform
- 既有唯一执行 Project（来源：QA 停止交接原文）：https://cursor.com/agents/bc-1dfb3b68-390d-59b9-9e8d-02ceff9b3d97
- 下一责任人：PM 将本附件交上述既有 Project 只存档。不新建 Project，不合并，不部署，不恢复开发或采集。
- 本包与 PowerWhois、TunnelBrowser 严格分开。

## 必须保留的质量边界
本交接**未实时核对当前远程**分支/PR/head。以下仅为绑定历史候选的独立结论，不能当作当前远程状态，也不是用户批准。
- PR2 fix3 https://github.com/WenLiCG/vps-review-platform/pull/2：head `5a06d684381ab8e74adfc2dcc129ed9ff163c410`，tree `b8f38499f01f8ffd4e787a828bf8109dc192c88b`。历史质量 **pass**（2026-11-12 18:56 PST；原文件记 2026-11-13 10:56 Asia/Shanghai）。D1–D5 按当时范围 skipped；EXDEV、并发读者、umask 0、TOCTOU 等未覆盖见原报告。
- PR3 S2 fix1 https://github.com/WenLiCG/vps-review-platform/pull/3：head `afe0bb473eacdcb66a48b9434c0cdb34467dfd0a`，tree `f0dcfd7d8bc5ece7dc0501ddd426f1f0f7c7734d`。历史质量 **fail**（2026-11-12 20:00 PST；原文件记 2026-11-13 12:00 Asia/Shanghai）。高：currency/billing_period_months/term_role/monthly_equivalent 在 keep_both 后详情页标签 KeyError，站点不能生成。中：价格冲突误清非冲突 vcpu 的变异未被 349 单测捕获（6 个变异仅抓住 5 个）。全量 349 OK 两遍不抵消上述失败。
- 更早的 PR2 / fix1 / fix2 与 PR3 S2 原文一并保留，便于看到修复链条，但**当前可引用的历史终态**仍是上面两行，不得把中间 fail 或更早 pass 说成当前结论。

## 敏感检查
对 QA 停止交接及 12 份 evidence 正文逐份阅读，并扫描秘密模式。
- 未发现密码、令牌、私钥、账户日志、邮箱或私人数据。
- 文中 `private_key`、`plain_sensitive_token` 等是测试字段名或探针标签，不是真实密钥。
- 合成示例 URL（如 `cdn.synthetic.example`）与公开仓库/临时 `/tmp` 路径予以保留。
- **未做脱敏**。归档副本与源文件字节一致。原件未改。源 SHA256 与 QA 交接所列 12 项及交接文件本身完全一致。

## 收录文件（均已审过，共 13 份源文件 + 本清单）

| 归档路径 | SHA256 |
|---|---|
| QA-HANDOFF-STOP-20261119.md | 59643d5fc9cdf6274c1c408916562130e173dce5409f074934fa067523c92844 |
| evidence/qa-pr2/VPS-PR2-VERDICT-20261113.md | 23973fb073a001481491d640f938d1103bbc8c17f63e1a782f634a8b09a0eef5 |
| evidence/qa-pr2/pr2-independent-review.copy.md | f2b0a1ad391bb026333f65c44e00c90676a87bc672c124c8d22b4224c03680a7 |
| evidence/qa-pr2-fix1/VPS-PR2-FIX1-VERDICT-20261113.md | 0a42481345a5072ce7a8bb3ba7554ed92f3ebed74460565ed070710380b0616f |
| evidence/qa-pr2-fix1/pr2-fix1-independent-review.copy.md | 1f0ac97b9a77e3e4f1d54f6b3b79fe9dbc7b3e38348d5e84dc7f493e1b1dfcd5 |
| evidence/qa-pr2-fix2/VPS-PR2-FIX2-VERDICT-20261113.md | 17ca440964d508e78d4390f6590ae0dc383e62607f4f58a8a263d13c9f915f13 |
| evidence/qa-pr2-fix2/pr2-fix2-independent-review.copy.md | 28006555598f63e8b59d27311ed96bce1ca06689a0265871557214dc0f5578eb |
| evidence/qa-pr2-fix3/VPS-PR2-FIX3-VERDICT-20261113.md | c083a174bb8eedeebd49f8e822786f3f56fa963300c64d47cc61b6e254328397 |
| evidence/qa-pr2-fix3/pr2-fix3-independent-review.copy.md | e42f95d707f53fcdab49c43447fe2e3f4ddbba06962053b8ad5982884c4f85ce |
| evidence/qa-pr3-s2/VPS-PR3-S2-VERDICT-20261113.md | dddb8d5194581fbf23e608ddfffdd9d97a88085649e6e3f895a1442ab6d37d45 |
| evidence/qa-pr3-s2/pr3-s2-independent-review.copy.md | 199bc2a689cc75262b69ba73c789da1c6c5cef02fc57a3b9e37a99297f5dd5c8 |
| evidence/qa-pr3-s2-fix1/VPS-PR3-S2-FIX1-VERDICT-20261113.md | 5643ff5bbbaba4e2cac9cff91bf87efb0c3fc55830c20d042e7e2b8b18778e79 |
| evidence/qa-pr3-s2-fix1/pr3-s2-fix1-independent-review.copy.md | b63f75db5cdc0597a8341e3eb3d6c0f5603ccc4cad49af3c038a0941a47109ec |

源目录：/workspace/vps/qa-stop-handoff-20261119/ 及其 evidence/。

## 明确不收录
指定来源中**没有**当前开发停止交接。未把更早的 `/workspace/codex/vps-review/S2-HANDOFF-to-grok.md` 纳入，以免把旧交接当成这次停止包。作者工作目录/分支/diff 仍以（尚未见到的）开发交接为准，QA 不补猜。

## 需要 PM 注明的局限
- 本包只是可上传的安全附件，整理者未上传、未操作 Cloud Project。
- 未实时核对远程；历史 pass/fail 不能写成当前结论。
- 缺当前开发停止交接；若后续补交，须单独敏感检查后再归档，不要与本 QA 包混淆成一次新验证。
- 不合并、不部署、不恢复采集或改冲突规则。
