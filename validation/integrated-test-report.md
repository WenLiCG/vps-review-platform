# VPS 一体化程序 0.2.0 验证结果

验证日期：2026-10-09。

## 已通过

- Debian 13.6 / Python 3.12.14：259 项后端 Python 测试通过，0 失败、0 跳过。
- 原桥接程序：40 项测试；原采集 Skill：7 项；原分析 Skill 自检通过。
- 筛选网页：原 66 项、整合 22 项、线路方向 7 项逻辑断言通过。
- 独立服务进程：117 项检查、42 次 localhost HTTP 请求及两次重启通过。
- 使用已有公开来源的真实证据验证了工作包交给助手实际阅读后再提交入库的流程。原始证据、完整提交及 SQLite 未包含在源码仓库中。
- 原 v5 的 120 篇原帖、128 条对象和 22 份历史公开复核保留；6 份基线 JSON 和 10 份原 Skill 文件保留原始字节。

## 能力边界

- 运行时不自动调用 AI/OCR；识别由实际具备文字与视觉能力的助手核读工作包后提交。结构校验不能独立证明事实正确或核读身份。
- 管理界面只监听回环地址；安全筛选站由 `export-public` / `export-v5` 单独导出。`export-evidence` 包含私有原文和原图，禁止公开。
- 0.2.0 尚未在 Debian 12 / Python 3.11 或 Windows 真机上重新完成全套运行验收；Debian 12 与 Windows 部署步骤基于该程序接口，不能视为实机部署通过。早期 0.1.0 曾在 Windows / Python 3.14.3 运行 93 项测试，其中 2 项因符号链接权限跳过，此结果不等于 0.2.0 全量验收。
- 未执行真实联网采集、生产 systemd/nginx 安装或公网部署。网页测试涵盖 JS 逻辑、模拟 DOM 和真实 HTTP，不包含实际浏览器视觉验收。

## 重复验证

    python scripts/run_offline_checks.py

GitHub 发布前的最新检查见 [publication-checks.json](publication-checks.json)。
