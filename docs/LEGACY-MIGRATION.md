# 历史归档迁移

## 用途

将已经采集、已经留下旧版分析的完整本地证据目录接入后端，只读查看历史结果。状态是 `legacy_imported`；不会生成新任务的 `accepted`，不会为旧分析编造 observations、review_log、reviewed_at 或新的图像核读声明。

## 输入与操作

输入必须是解包后的 `assets/<post_id>/manifest.json`，默认使用相邻 `analysis.json`。不接收 ZIP、单独文章片段或任意 HTML；不会自动解压，也不访问网络。

在项目根目录使用实际绝对输入路径：

    python3 -m vps_pipeline --data ./var import-legacy /path/to/archive/assets/971353/manifest.json
    python3 -m vps_pipeline --data ./var list-legacy
    python3 -m vps_pipeline --data ./var show-legacy RECORD_ID

`--analysis /absolute/path/analysis.json` 可指定同一历史归档对应的原分析。输入引用文件必须全部存在、哈希和大小匹配。原文件只读；私有快照逐字节保留原 manifest、analysis 和 manifest 列出的证据。POSIX 新快照目录仅所有者可访问。重复的相同字节返回同一记录；不同原始分析形成独立历史版本，不覆盖旧版本。来源路径和运行时 SQLite 不进入公共导出。

中断复制不会提交记录。复制完成而数据库提交前中断形成的孤立快照，会在下次相同导入时重新校验后恢复登记；不会盲目覆盖已有目录。

## 严格的历史规则

- 原 metadata 必须显式记录 browser_import、首帖和非回复的采集声明；这是历史声明，不是本次重新验证的远端页面身份。
- HTML 必须是完整、平衡的单个 article.post-content，拒绝整页、回复结构、数字楼层标记、缺失/多余/错配闭合标签。不得伪造 div#0 包装，普通 ingest 的 div#0 要求不放宽。
- 原文件哈希、大小、角色、MIME、路径、总预算、JSON 唯一键及有限数值均检查；不跟随符号链接、重解析点或路径穿越。
- 图片必须由首帖实际 DOM 引用。报告最多允许两跳：首帖 → 已归档的允许域报告 → 该报告实际出现的报告 URL。manifest.links 单独不能证明来源，脚本/style/template 内容不能建立引用链。
- 971510 的已记录补充文字有单独窄规则：原 report_text/#0 保留不改，完整文字须与原 HTML 提取对应，原可见文字须与折叠 details 状态对应；只在迁移 provenance 中记录 first_post_supplement 派生语义。
- 旧版 61 字段校验通过且标准化结果必须等于原分析；需要修复或重算的输入拒绝静默改写。
- 引文按原协议去除空白后比对。历史 HTML 图片 src/页签标签仅可作为来源绑定引用，且须有同字段独立图片证据、实际 DOM 与已归档历史已读图片对应；这些检查不证明图片测量正确。普通新分析校验保持严格不变。

本候选配置面向已有 20 篇 browser_import 批次。两篇 pilot 的文字来自页签视窗拼接，另含独立补充来源，未纳入该严格配置；不能为了让导入通过改写旧 manifest。

## 查看与公共投影

启动原本机服务后，管理页面“历史分析（只读）”显示导入结果。相同 token/Host/Origin 防护适用于：

- GET /api/legacy
- GET /api/legacy/<64位记录ID>

这些 API 不提供导入、修改、删除或原文件执行/下载操作。原 HTML 从不作为活动页面注入，历史内容使用 textContent 显示。

0.2.0的`export-public`/`export-v5`输出原v5兼容筛选网站。历史记录先形成安全字段投影，再由catalog_adapter与原公开基线精确关联；重合条目仅标注来源，原v5较丰富的公开事实保持原样，不把历史迁移当作新accepted。独立字段投影保留原status与projection_status（unchanged/partial/redacted），不暴露原文、图片、引用、作者、核读者、路径或IP。长篇说明隐藏时，私有原分析仍完整保留。早期records/legacy_records加原证据的低层出口仅在明确私有的export-evidence中保留，绝不能用于发布。

`new_review_performed=false`、`ai_invoked=false`、`review_attestation_verified=false`、`new_analysis_accepted=false` 始终明确保留。历史 ai_review 只在私有记录中原样保存，不能据此宣称本次进行了 AI/OCR、确认核读者身份或证明所有事实准确。
