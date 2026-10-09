# 归档与识别协议 v1

输入目录：`<archive>/assets/<post_id>/manifest.json`。manifest 的 `schema_version` 为 `vps-archive/1`，含 `post_id`、`source_url`、`title`、`author`、`captured_at`、`status`、`files`、`links`、`failures`。状态为ready/partial才可识别。files每项包含唯一id、role、相对本帖目录的path、source_url、sha256、bytes、content_type。role为first_post_text、first_post_html、image、report_text或report_html。禁止跨目录路径，不修改归档原件。

`review.py init` 生成以下形状，具体61字段见同目录fields.json：

```json
{
  "schema_version": "vps-analysis/1",
  "post_id": "913633",
  "source_url": "https://www.nodeseek.com/post-913633-1",
  "ai_review": {"completed": false, "agent": "", "reviewed_files": []},
  "summary": "",
  "affiliate_url": null,
  "facts": {
    "vcpu": {
      "value": null,
      "status": "unknown",
      "evidence": [],
      "note": "尚未识别"
    }
  },
  "latency_samples": {}
}
```

上例只展示1字段，真实facts必须包含全部61个id。不要新增不在字段目录中的id。

- `status`：reported（首帖/报告明示）、computed（程序计算）、inferred（推断）、official_current（当前官网补充）、unknown（没有证据）、conflict（来源冲突）。unknown/conflict的value必须null并说明原因；冲突原始候选值保留在note和evidence。其他状态value须符合字段目录类型。
- `evidence`数组项：`{"file_id":"first-text","locator":"CPU测评，第12行","quote":"2核心, 2线程"}`。图片也用同一形状，locator写图片区域或坐标，quote写读到的文本。文本证据quote必须能在来源文本中找到（忽略空白差异）；图片证据由AI核对。标题等元数据使用保留来源id `manifest`，locator仅可为title、author、source_url，quote须匹配对应值；同时将manifest加入reviewed_files。这样可提取只写在标题中的商家和价格。
- `ai_review.reviewed_files`：真实阅读的文件id，至少包括一份首帖文本/HTML，以及每张图片；不能为了通过检查虚填。缺失或损坏图片应回到下载状态登记问题，不能把它删出清单冒充完整。
- `test_time.value`：`{"report_times":["2026-09-05T21:03:31+08:00"],"timezone_basis":"报告明确UTC+8","half_hour_buckets":[]}`。程序转换所有时间到UTC+8并计算`YYYY-MM-DD HH:mm–HH:mm`桶。跨午夜桶的终点带日期，所有报告的日期/原始偏移应保留在evidence/note。无确定时区则整个字段unknown。
- `latency_samples`可为`{"ipv4":{"telecom":[160,null,180],"unicom":[200],"mobile":[]}}`，同理ipv6。仅当相应latency字段为computed时使用，三运营商键必须齐全。单位ms，数组中的null代表无结果，0是有效数值。程序覆盖AI给出的均值、样本量和method，输出`mean_ms`、`sample_count`、`method=non_null_arithmetic_mean`。确认采用TCP省份统计等测量口径写入该字段note；必须保留原始省份/节点及缺失判断的证据。
- 单位为字段目录中的标准单位，原始单位/换算写note。别把数字与单位拼接成字符串。样本数据不能当作其他帖默认值。
- affiliate_url必须是用户提供的HTTP(S) URL；其来源不从帖子推断。程序不校验账号归属，由调用者确认用户授权。

finalize输出的analysis.json额外含`archive_status`、`download_failures`、`generated_at`、`markdown_path`、`sources`和`source_metadata`，它们由程序填写。用于网站筛选时结合value与status，尤其不要把official_current当作历史实测。program_version固定为1，后续字段协议变更应升级schema_version。
