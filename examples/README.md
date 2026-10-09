# 合成工作包

`synthetic-task.zip` 由本项目 CLI 使用 `tests/fixtures/nodeseek_first_post.html` 生成。
这是合成协议演示，里面的帖子身份标记、图片链接和 VPS 文字不是真实评测。

包状态为 `needs_ai`；61 个字段保持未知，`ai_review.completed=false`。
图片与关联报告未提供，因此归档为 `partial`，缺失原因已保留。
本示例没有触发任何网络请求或模型调用，不可发布成真实测评数据。

用真实公开证据替换输入后，可按项目 README 导出自己的工作包，交给能够
实际阅读文本、查看图片的助手，再导入完成核读后的 envelope。

0.2.0重新生成的示例仍为needs_ai，catalog_mapping为null；未执行识别，不可作为真实测评发布。按README真实核读并明确对象后才能进入筛选。
