# VPS 评测聚合 · 离线数据契约（中文）

> 版本：`1.0.0-offline`  
> 性质：**规格与验收数据**，不是业务实现代码。  
> 所有 fixtures 均为 **synthetic（人工构造）**，**不是**真实 NodeSeek 帖。

## 1. 目的

定义规范化文档（normalized review document）的字段、单位、`null` 语义、证据（evidence）、置信度（confidence）与审阅状态，供解析器/校验器/离线 CI 对齐。配套 `fixtures/` 覆盖难例。

## 2. 授权与边界（务必读）

### 2.1 用户提供的采集授权（已收到，未独立验签）

- 文档标题：`DATA COLLECTION AND WEBSITE CRAWLING AUTHORIZATION`
- 伙伴：`Cary`；日期：`2026-09-30`
- 范围摘要（据用户提供 PDF 的父级转述）：授权对 NodeSeek 网站数据进行 access / crawl / scrape / collect / process / analyze；覆盖 webpages / posts / comments / metadata / public UGC；允许 automated tools / crawlers / scripts / APIs；有效至书面撤销或修改；受适用法律及另行约定限制约束。
- **本交付物不独立确认签发/签名真实性**；签名字段未抽取到可视签名时，**不作「授权无效」的法律结论**。
- **可推进**：按授权范围做**低频公开首帖采集准备**（限流、幂等、只采首帖）。
- **仍待确认**：公开原文全文、第三方作者图片的转载/商业再许可；该授权**未明确**此类公开复用权。
- **本 ZIP 不执行**全站采集、不创建仓库、不写业务爬虫实现。

### 2.2 平台公开条款（仍相关）

来源：https://www.nodeseek.com/post-1-1 《隐私协议和服务条款》（生效 2022-11-24）

相关原文摘录（用户行为规范）：

> 未经本网站事先明确书面许可，以任何方式（包括但不限于机器人软件、蜘蛛软件、爬虫软件等任何自动程序、脚本、软件）和任何理由自行或委托他人、协助他人获取平台的服务、内容、数据；

另：用户上传内容知识产权归作者或原始著作权人；网站侧内容亦声明 IP。  
**用户提供的伙伴授权**可作为「书面许可」路径之一推进采集准备；**不等于**已解决作者侧图片/全文公开再许可。

### 2.3 robots.txt

https://www.nodeseek.com/robots.txt — `Disallow: /api/`；**不等于**爬取授权。

## 3. 核心模型：套餐事实 vs 测评观测

| 层 | 存放位置 | 可硬筛？ | 示例 |
|---|---|---|---|
| 套餐事实 | `plans[]` | 是 | vCPU、内存、硬盘、流量、价格 snapshot、地点声明 |
| 测评观测 | `observations[]` | 否（仅「测到过」） | Ping、线路、Geekbench、流媒体、IP 风险 |
| 派生 | `derived` | 有条件 | 标签、median；**无足够独立样本则 null/空** |

**禁止**：把单次 Netflix / Ping / 线路写回 `plans` 永久属性。

## 4. 字段与单位约定

### 4.1 内存 / 硬盘 / 流量

- `memory_mb`：整数；语义在 `unit_notes` 声明（常见按 GiB→1024 MiB）。
- `disk_value` + `disk_unit`：`GB` | `GiB` | `null`。**禁止**静默换算后抹掉原单位。
- `traffic_value` + `traffic_unit`：`GB` | `GiB` | `TB` | `TiB` | `null`。

### 4.2 价格

每条 `prices[]` 必须含：

- `currency`（ISO 4217 三位）
- `billing_period_months`（1=月，12=年…）
- `amount`
- `term_role`：`first_term` | `renewal` | `unknown`
- `monthly_equivalent`：仅当可计算时填写；**年付不得写成裸月价且不标注 period**
- `evidence`

排序/榜单默认用 **续费** 月均，不用首月优惠价冒充长期价。

### 4.3 时间

- `published_at`：发帖时间，**不得**写入 `tested_at_beijing`。
- `tested_at_raw` / `tested_at_beijing`：测试时间；不明 → `null`；`tz_confidence`=`explicit`|`inferred_weak`|`unknown`。
- 显式 UTC/`Z`：换算 `Asia/Shanghai`，允许跨日（见 FX-005）。
- 时区不明：**不硬猜**为北京时间。

### 4.4 线路

- 底层：`carrier`（CT/CU/CM）× `direction` × `asn_path` × `route_tags`。
- **仅见 AS4809**：只保留 `asn_path`，`route_tags` **不得**自动含 `CN2_GIA`（FX-010）。
- 国际 Transit 与中国接入网枚举分层，不混为一列字符串。

### 4.5 Benchmark

- `suite` + `version_major` + `metric` + `score`。
- GB5 / GB6 / GB7 **分桶**，禁止单一 `geekbench_score`（FX-009）。

### 4.6 样本与标签

- `sample_policy.dedupe_by_run_id = true`：同 `run_id` 内多行 **计 1 个样本**（FX-012）。
- `min_samples_for_stability_tag`（fixtures 用 5）：不足则 `derived.tags` 不写 `#线路稳定` 等（FX-011）；`aggregates` 的 median/P95 无样本则 `null`，**不造数**。

## 5. Evidence / Confidence / 审阅

### 5.1 Evidence

```
kind: text_quote | ocr_expected | derived | absent
quote / asset_ref / region_box / confidence(0..1) / extractor / notes
```

- 图片项：只定义 **预期 OCR 输入**（`ocr_expected` + `asset_ref` 占位），**不生成真实截图**。
- 非空观测字段应有 evidence；`absent` 用于明确「源中没有」。

### 5.2 冲突

- 正文与 OCR 冲突：`conflicts[]`，`resolution=keep_both`（默认），字段值可 `null` 直至人工（FX-003）。
- **禁止 last-write-wins 覆盖**。

### 5.3 review_status

`state`: `draft` | `auto_ok` | `needs_review` | `approved` | `rejected`  
`needs_human` + `reasons[]`。

### 5.4 summary

- `limited_claim=true`：缺上下文时必须；文案声明「仅基于已抽取字段」。

## 6. 导出文件名

模式：`{price}-{period}_{地点}_{配置}_{YYYYMMDD}`  

- 周期：`10USD-mo` / `24USD-yr`  
- 测试日不明：`unknownDate`  
- 碰撞或缺关键字段：附加 `__{source_post_id}`（FX-008A/B）  
- 多套餐：`MULTI_…` 或拆多文件（FX-002）

## 7. Schema 文件

| 文件 | 说明 |
|---|---|
| `schema/evidence.schema.json` | 证据 |
| `schema/price-snapshot.schema.json` | 价格快照 |
| `schema/plan.schema.json` | 套餐事实 |
| `schema/observation.schema.json` | 观测 |
| `schema/review-document.schema.json` | 整文档（含 `$ref`） |

实现方可内联 `$ref` 做校验；本包不附带校验器业务代码。

## 8. Fixtures 覆盖表

见 `fixtures/manifest.json`。每案目录：

- `case.json` — 元数据  
- `raw.excerpt.txt` — 虚构原文片段  
- `expected.normalized.json` — 期望规范化输出  
- `acceptance.asserts.json` — 可机器检查的断言描述  

## 9. ID 链接规则（自洽）

- `observations[].plan_id` ∈ `plans[].plan_id`
- `export.collision_suffix` 若存在则等于或派生自 `source.source_post_id`
- 同文档内 `observation_id` / `plan_id` / `run_id` 唯一（`run_id` 可跨多 benchmark 行共享）

## 10. 非目标（本包不做）

- 不实现爬虫/解析器/网站  
- 不创建 Git 仓库、不联系 Bot、不启动 routine  
- 不把网站开发进度标为已完成  
