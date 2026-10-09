# VPS 测评一体化程序 0.2.0

一个 Python 启动入口，包含有限采集与归档、真实助手识别交接、原 v5 多维筛选网页及本机任务管理。

采集、分析校验和筛选现在共用后端任务与安全数据接口。识别环节由真实助手实际阅读工作包里的文字和图片后提交结果；程序不会自动调用模型/OCR或把空模板标成已完成。

## 部署入口

- [Windows、Debian 12、systemd、SSH 隧道与备份](docs/DEPLOYMENT.md)
- [架构与安全边界](docs/ARCHITECTURE.md)
- [0.2.0 测试结果及未验证范围](validation/integrated-test-report.md)

本次完整运行验证环境为 Debian 13.6 / Python 3.12.14。下方 Windows 和 Debian 12 操作指引不代表已完成这两个环境的 0.2.0 全量验收。

## 获取源码

本仓库为私有仓库，请先登录有访问权限的 GitHub 账号。可在仓库页面点击 **Code → Download ZIP**，解压后进入同时包含 `README.md` 与 `vps_pipeline/` 的目录。

已配置 GitHub 身份验证的 Git 用户也可以执行：

    git clone https://github.com/WenLiCG/vps-review-platform.git
    cd vps-review-platform

不要把密码或访问令牌写入克隆地址、脚本或配置文件。获取完整源码即可直接运行，当前交付以源码目录为准，不需要构建 wheel。

## 直接运行

需要 Python 3.11+，运行时仅用标准库；无需 pip/npm 安装。请保留完整源码目录，包括 website、vps_pipeline/vendor 和 skills。

在解压后的程序根目录运行（Windows 可用 python 或 py -3）：

    python scripts/verify_package.py
    python -m vps_pipeline --data ./var init
    python -m vps_pipeline --data ./var serve --host 127.0.0.1 --port 8765

- 筛选网页：http://127.0.0.1:8765/catalog/
- 本机任务管理：http://127.0.0.1:8765/
- 管理页需要本次启动控制台显示的 Session token。重启后 token 更新，只填在管理页，不放入 URL 或公开日志。
- Ctrl+C 停止。服务仅允许监听 127.0.0.1 或 ::1，不直接提供公网管理服务。

网站初始保留原 v5 的 120 篇原帖、128 条对象及22份61字段历史复核。53项、9组筛选布局和61字段详情保留；对象数不等于独立机器数。初始私有任务库为空，不把这22份历史记录伪装为刚完成的新任务。

## 采集与归档

添加链接只入队，不自动联网：

    python -m vps_pipeline --data ./var add https://www.nodeseek.com/post-POST_ID-1
    python -m vps_pipeline --data ./var collect --limit 1 --allow-network

替换 POST_ID。collect 明确限1–100个任务，只取规范首楼页面；遇到限制或错误停止本批，不追跳转、验证码、代理或自动重试。图片及报告由合法取得的本地资源映射导入，未取得的内容保留失败原因。管理 API 不提供联网采集入口。

已有完整首楼页面：

    python -m vps_pipeline --data ./var ingest JOB_ID /absolute/capture/post.html --resources /absolute/capture/resources.json

resources.json 把首楼实际引用的 URL 映射到 HTML 同目录内的相对路径。额外映射不会读取，路径穿越、符号链接、非法类型和预算超限会拒绝或明确保留缺失原因。

已有合规归档：

    python -m vps_pipeline --data ./var ingest-archive JOB_ID /absolute/archive/assets/POST_ID/manifest.json

该命令先严格检查原 manifest、身份、文件哈希/大小与来源，再逐字节复制到新的私有快照；不伪造 div#0，不更改原捕获日期，也不接收或自动解压 ZIP。重复相同快照去重，旧快照和已接受分析版本保留。更多边界见 docs/ARCHIVE-IMPORT.md。

原版两个 Skill 随包保存在 skills/，可由支持 Skill 的助手读取；未自动安装或修改用户已安装的版本。原采集脚本及用法保留在 references/V5-README-original.md，但权限、访问限制和有限范围要求不变。

## 实际识别与提交

    python -m vps_pipeline --data ./var task JOB_ID ./work/review-task.zip

把工作包交给具备文字与视觉能力的助手。它需要按包内原技能和61字段协议，实际查看证据，填写 observations 与逐文件 review_log。未取得、未读清或冲突内容保持 null/unknown/conflict；不能用0代替缺失值，也不能伪造 completed、核读时间、图片区域或身份。

要让结果进入筛选页，填写明确的 catalog_mapping。它确认具体对象的 item_id、原帖对象数、唯一被本次核读的对象及安全公开名称；模板默认 null。已有多对象帖必须指定原对象，不能把一份分析复制成多台机器。新帖目前支持一个明确核读的对象；未映射或歧义记录留在 pending_catalog。

完成后通过管理页上传 envelope，或运行：

    python -m vps_pipeline --data ./var submit JOB_ID /absolute/completed-envelope.json

校验成功后刷新 /catalog/。网页一次读取原子安全快照，新结果与保留的原v5历史复核分开标记。后端保留全部接受版本；网页当前展示最新版本和原v5历史，其他中间版本留在私有数据库。跑分必须有明确工具/版本，线路必须有明确协议族/方向/运营商；TCPQuality延迟不充当普通ICMP Ping。公开投影隐藏的值不会误入数值筛选。

结构校验不能独立证明事实准确或实际核读发生。程序保留 ai_invoked=false 和 review_attestation_verified=false；真实助手交接不等于无人值守模型服务。没有配置付费API、密钥或后台AI调度。

## 已有历史分析

    python -m vps_pipeline --data ./var import-legacy /absolute/archive/assets/POST_ID/manifest.json
    python -m vps_pipeline --data ./var list-legacy

legacy_imported 独立于新 accepted。保留原 manifest/analysis/证据与旧核读声明，不补造原来没有的 observations/review_log。已有20篇批次已完成本地迁移验证；与 v5 基线重合时仅关联历史来源，不重复增加帖子或覆盖较丰富的原公开数据。两篇 pilot 仍保留在网站基线，私有迁移需单独来源配置，不能静默绕过。

## 安全导出与部署

    python -m vps_pipeline --data ./var export-public ./public-vps-001

export-v5 是相同安全出口。输出仅含筛选网页及允许公开的结构化数据，不含原始证据、图片、全文引文、作者/核读者身份、IP地址、token或SQLite。目标必须为私有数据目录之外的新目录或空目录。命令只导出，不部署。

只发布导出目录的内容。不要把整个程序包、var、skills、工作包或私有归档作为网站根目录。deploy/nginx-public.conf.example 是仅本机监听的静态预检示例，不反向代理管理 API；公网域名/TLS/权限由操作者另行确认。

需要本地证据备份时，旧原证据出口已明确改名：

    python -m vps_pipeline --data ./var export-evidence ./private-evidence-001

此目录包含原文和原图，可能有IP、作者及引用内容，禁止当作公开网站发布。完整数据库备份应停止写入后复制整个私有数据目录；详见 docs/DEPLOYMENT.md。

## 复测和本次验收

完整离线测试需要 Node.js 18+；日常运行不需要 Node。

    python scripts/run_offline_checks.py

包括后端安全/状态测试、原技能自检、原桥接程序测试、66项原筛选回归及22项整合回归。合成测试始终使用单独临时目录，不能作为真实测评发布。

另在私有测试库完成了真实971353工作包交接：助手重新读文字并查看5张原图，生成61字段、51条观察、10条真实核读日志；成功入库并进入原v5对象筛选，原120帖/128对象/22历史复核保留。详细结果见 validation/integrated-test-report.md。没有重新联网采集、调用付费模型或修改已发布网站。


## 来源与许可

原有项目与 Skill 的来源摘要及哈希见 [NOTICE](NOTICE) 和 [provenance.json](provenance.json)。未附带开源许可证；仓库可见性不代表获得再分发或商用授权。第三方公开测评内容的权利仍属于各自权利人。
