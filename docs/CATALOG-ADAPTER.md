# 筛选数据适配接口

catalog_feed.catalog_records(store)读取并重新验证最新已接受快照及独立历史导入，输出安全的61字段、状态、明确对象映射和可比较的跑分/线路/报告时间维度。它不输出原manifest、原文、图片、引文、作者、核读者、token或私有路径。

catalog_adapter.build_catalog(baseline, records, definitions, exported_at)是无网络、无文件副作用的纯函数。baseline按原v5五个JSON文件名索引；definitions是原61字段目录。输出同样的五个公开JSON和catalog-integration.json。调用方另外保留原公开incremental-public-provenance.json。

服务一次返回{schemaVersion: vps-catalog-snapshot/1, files: 文件名到JSON的映射}。客户端只在snapshot返回404时回退到原五文件模式，错误或不合法快照不能静默混读。仅本机服务添加managementPath=/；静态导出不带管理链接。

重复历史记录只关联已有单对象复核，不覆盖原公开事实。accepted必须明确映射；多对象必须精确匹配原对象，不能把同一份分析扩成多个对象。旧v5复核保留为reviewHistory；其他后端中间接受版本保存在私有SQLite。

筛选只使用同一有效观察中的明确工具版本、指标、协议族、方向、运营商与线路。未知/冲突及安全投影遮蔽不转成零或猜测值。已接受修订不借用旧价格、旧跑分或图片派生数据补齐当前空值。时间维度仅接收已验证、带时区、与当前事实一致的安全元数据。
