# 一体化工作流与边界

同一个serve进程提供本机管理页/、原v5筛选页/catalog/、带token保护的管理API和无需token的安全公开数据快照。一次catalog-snapshot.json读取全部相互一致的公开数据，避免五个JSON文件混读版本。

采集：add只入队；collect必须显式--allow-network且限1–100个任务；或使用ingest/ingest-archive导入已有合法证据。图片和报告缺失会如实保留。不会处理登录/验证码或绕过访问限制。

识别：task导出needs_ai工作包，交给助手真实看文字/图片，再submit合规envelope。程序无自动模型/OCR服务、不存模型凭据、不调用付费API。核读声明不能被结构校验独立证明。

筛选：默认保留原120帖/128对象/22份61字段公开复核。legacy_imported重合条目只标历史来源；accepted必须有明确catalog_mapping。新帖只接受单个明确核读对象，已有多对象帖必须精确匹配原item_id和对象数。歧义记录保留pending_catalog，不制造对象。

当前accepted覆盖层以reviewHistory保留原v5基线复核；所有中间accepted版本仍保存在私有SQLite，网页当前只显示最新版本和原v5历史，并排除旧跑分/价格/图片派生字段对新结果的隐性回填。unknown/conflict保持空值；公开遮蔽与事实未知分开。Geekbench5/6、单核/多核、IPv4/IPv6、去回程、运营商、TCP/UDP/ICMP不混合。只有显式已确认时区的报告时间可筛，不拿采集时间替代。

export-public与export-v5仅生成允许公开的14项网页/数据文件，不复制原证据。不公开作者、核读者、原始图像、全文引文、IP、路径或token。原始证据出口是明确标注私有的export-evidence；绝不能发布它。/catalog/只支持固定资源白名单，不映射任意本地路径。

没有改动现有线上网站；一体化代码和本次测试均在独立副本进行。原v5和0.1.1/0.1.2交付候选保留，用户安装的技能文件未修改。
