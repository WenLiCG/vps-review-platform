# VPS PR #2 fix2 独立复验结论（2026-11-13 10:40 Asia/Shanghai）

- 仓库/PR：https://github.com/WenLiCG/vps-review-platform/pull/2，分支 s1-public-dto-v1
- 被审 head：d8c41af4301e53304faad44df062435b0021666b（tree 0ba3198adc74019372cbff6667246e1beb6e7e9b），父 de9ea46a，base main f7b35842；作者 Codex 程序员（gpt-6.1-sol 生成），复验线程 bc-6194c9a7 独立检出，只读，未推送/未评论/未改 PR
- 依据报告：pr2-fix2-independent-review.copy.md（sha256 28006555598f63e8b59d27311ed96bce1ca06689a0265871557214dc0f5578eb）
- 环境：Python 3.12.3，Linux 6.12.113 x86_64

## 结论：fail（需修复复验，质量建议；产品行为本轮未发现新缺陷）

| 项 | 状态 |
|---|---|
| 实时 head = d8c41af4 | passed |
| diff 只改 public_dto.py 与 tests/test_public_dto_pages.py | passed |
| D5 三种情形（--out 不存在 / 已有有效构建 / 父目录缺失）扫描失败不发布、无残留、umask 不变 | passed |
| 成功路径 --out 为 0o755（umask 022），无临时/备份残留 | passed |
| 替换第二步 rename 失败（mock）：旧目录逐字节、mode、mtime 不变，无备份残留 | passed |
| D2 非普通标记在 mkdtemp/rename 前拒绝 | passed |
| D4 普通文件与符号链接 --out | passed |
| 全量两遍 | passed（Ran 306 / OK ×2） |
| 六个变异 | **failed**：(i)(ii)(iii)(v)(vi) 抓到；(iv) 去掉“替换失败还原备份”后仍 306 OK |
| PR 描述写明残留风险（短暂缺失、EXDEV、umask 临时置 0、TOCTOU） | passed |
| D1、D3 | skipped（PM 定本轮不重测） |

## 缺陷
- **D6（低-中，测试缺口，阻塞本轮）**：tests 没有模拟“临时目录 rename 进 --out 失败”，所以 os.rename(backup, target) 的还原分支删掉也测不出来。这是 PM 明确要求核对的“备份能还原”路径。当前代码在 mock 下能还原，不是运行时数据损坏。
  - 位置：tests/test_public_dto_pages.py（缺测试），被保护代码在 vps_pipeline/public_dto.py 的替换/还原分支
  - 修复建议：加一条失败优先测试，patch 第二次 rename 抛 OSError，断言旧 --out 逐字节/mode 不变、无备份或临时目录残留、异常向上抛；并确认变异 (iv) 能让它失败。

## 观察（不阻塞，请 PM 定）
- 删备份失败时：新站点已在 --out，函数仍抛 OSError，同级留 .site-backup-*。调用方看到“失败”但新站点已发布。是否接受或改成告警由 PM 定。

## 未覆盖
- 真实跨文件系统 EXDEV 未在两块盘上重放；并发 TOCTOU、替换窗口内读者撞空目录未测；子目录/文件权限未逐个核对（只核对 --out 本身）。
- 未合并，组合/端到端回归不在本轮。
