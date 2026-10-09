# 验证说明

本目录只保留可分享的结果摘要；原始执行日志、私有测试库、真实工作包及环境路径不进入 Git 仓库。

- [0.2.0 验证结果](integrated-test-report.md)
- [GitHub 发布复测](publication-checks.json)

在源码根目录执行 `python scripts/run_offline_checks.py` 可自行复测。完整离线测试需要 Node.js 18+；正常程序运行只需要 Python 3.11+。测试使用临时目录、合成数据或已保留的公开结构化基线，不会重新联网采集或调用模型。
