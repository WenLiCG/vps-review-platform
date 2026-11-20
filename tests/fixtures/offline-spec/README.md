# vps-review-offline-spec

离线 **数据契约 + synthetic 验收 fixtures** 打包，供开发直接对齐解析/校验行为。

- 生成时间（北京时间）：2026-11-06  
- Schema 版本：`1.0.0-offline`  
- **全部 case 均为人工构造（synthetic）**，不是真实 NodeSeek 内容。

## 快速路径

| 路径 | 用途 |
|---|---|
| `README.md` | 本文件 |
| `DATA_CONTRACT.md` | 中文数据契约（字段/单位/null/evidence/审阅） |
| `schema/*.schema.json` | JSON Schema 规格（非业务代码） |
| `fixtures/manifest.json` | 用例清单与授权边界说明 |
| `fixtures/cases/FX-*/` | 各难例 |

## 授权边界（摘要）

1. **已收到**用户提供的 NodeSeek 采集授权 PDF（伙伴 Cary，日期 2026-09-30）。可按授权范围推进**低频公开首帖采集准备**。本包**不独立验签**。  
2. **仍待确认**：公开原文/作者图片的转载与商业再许可。  
3. **本包不执行**全站采集；不包含爬虫实现。  
4. 参考仓库 `WenLiCG/vps-review-platform` **仍不可访问**（技术栈未核实）。  
5. 平台公开条款仍见 https://www.nodeseek.com/post-1-1 （含禁止未经书面许可的自动获取——用户提供授权作为书面路径之一，公开复用边界另议）。

## 覆盖难例

单套餐纯文字；多套餐；正文/图片冲突；缺失测试时间；UTC→北京跨日；价格周期/币种分离；GiB/GB；文件名冲突+缺值；GB5/6 分桶；仅 AS4809 不判 GIA；无样本不打稳定标签；同 run 不双计样本。

## 如何用于开发

1. 读取 `DATA_CONTRACT.md` 与 `schema/`。  
2. 对每个 `FX-*`：以 `raw.excerpt.txt` 为输入期望，断言对齐 `expected.normalized.json` 与 `acceptance.asserts.json`。  
3. 图片：仅使用 `ocr_expected` 的 `quote`/`asset_ref`/`region_box`；**无需**真实 PNG。  
4. 打开 `LIVE_FETCH` 抓真实站：需另循项目合规开关与限流；**不属于本 ZIP 范围**。

## 进度诚实声明

- ✅ 离线规范与 fixtures：**已完成（本包）**  
- ⏳ 采集许可：用户已提供伙伴授权；公开原文/图片复用边界：**待确认**  
- ⏳ 参考仓授权：**仍阻碍**  
- ❌ 网站产品开发：**未开始**（勿虚报）
