# 冻结契约 contract/v2

本契约只处理结构化离线文档，不解析原帖，不实现捕获 CLI 或六维筛选。
四项冻结物分别为：

| 项目 | 版本 | 定义路径 |
| --- | --- | --- |
| 规范化测评文档 | review-document/v2 | schemas/review-document/v2/review-document.schema.json |
| 公共 DTO | public-dto/v1（冻结）、public-dto/v2 | schemas/public-dto/v1/public-dto.schema.json、schemas/public-dto/v2/public-dto.schema.json |
| 私有捕获清单 | capture-manifest/v1 | schemas/capture-manifest/v1/capture-manifest.schema.json |
| 价格语义 | price-semantics/v2 | schemas/price-semantics/v2/price-semantics.json |

实现与版本常量位于 `vps_pipeline/contract_v2.py`。规范化 schema 的 const 是
review-document/v2；兼容读取器也接受 1.0.0-offline。内部可保留 private_key、
capture_file 和 notice，但公共投影只复制白名单字段，不复制 evidence、asset_ref、
作者、捕获路径、原图或引文。多套餐保留各自配置和价格，详情页在同一帖中展示。
keep_both 内存冲突不选定唯一值：memory_mb 为 null，公开候选仅包含
source、raw、normalized_mb_candidate，并保留字段和 resolution。

## D2 日期

仅日期输入保留 YYYY-MM-DD 和 day 精度，review_date_tz 与 tz_confidence 为
unknown，tested_at_beijing 为 null，不猜北京零点。仍参与按日的闭区间筛选，
文件名日期段为 YYYYMMDD。没有测评日期则用 unknownDate，不用 published_at
补日期。完整时间带显式时区才转换到北京时间；例如 2025-06-03T17:30:00Z
转换为 2025-06-04T01:30:00+08:00，文件名日期为 20250604。

## 价格和样本

明确正整数周期才计算 amount / billing_period_months；布尔值不是合法周期。
未知币种或周期不进入价格区间。不使用汇率，也不跨币种换算比较。
年付保留原金额、12 月周期与月均，不能当作裸月价。
term_role 为 first_term、renewal 或 unknown；月均函数不改变角色，长期榜单应
选择 renewal，不用首期优惠冒充长期价格。price_status 为 known、unknown、partial。
稳定标签至少需要五个独立样本，按 run_id 去重；当前未冻结稳定性数值判据，
因此不凭样本数自动声明稳定，也不制造聚合数值。

文件名由事实重新生成，多套餐用 MULTI；调用方已记录碰撞时附加
__{source_post_id}，不直接信任存储的 suggested_filename。

## 兼容与构建

`project_to_public_dto` 与 `validate_public_dto` 继续提供原 v1 路径；
FX-001 的字段和 public-dto/v1 版本不变，其北京时间仍为
2025-06-03T21:00:00+08:00。新增的 `project_review_document_to_public_dto`
输出 public-dto/v2，增加 review_date_tz 和结构化 conflicts。
`validate_public_dto_compatible` 接受两版；`build_public_site` 识别规范化文档，
按帖生成详情页，仍在扫描通过后原子替换站点，并保留原有备份恢复和删除警告。

清单 captured tab 必须带 64 位十六进制 sha256，missing 与 not_present 显式记录。
清单 captured_at 必须带 +08:00 时区，不能当作测评时间；清单是私有数据，
images.private_key 不得进入公共 DTO。本轮只冻结 schema 和校验器，无 ingest。
