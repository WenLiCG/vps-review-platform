# 七站论坛采集与验收

Python 共享引擎、七个独立站点入口、带站点设置和开始／暂停的 Web 面板。本机 Windows / WSL 与独立 Debian 12 / Python 3.11.2 VPS 两轮测试均已完成：七站各 300 个不同主题，并通过保存响应的独立验收。历史实测结果以 `REPORT.html` 和各运行目录的 `verification.json` 为准；持续采集使用单独的 `live-*` 目录。本项目不把首页、登录页、挑战页或同一主题分页的重复响应计为新增主题。

## 首页控制台与持续采集

首页固定显示七站，可逐站设置线程、请求间隔、超时、传输方式、代理池和增量发现间隔，开始／暂停实际采集，并进入站点详情查看队列、正文、历史验收任务和证据下载。待采主题只统计已发现且尚未成功的不同原生主题；不代表全站总量。正在处理主题按实际在途任务去重；请求／失败和流量为当前 live 运行累计值。

Web 服务负责保存设置，独立 `controller.py` 服务负责启动和管理采集进程。暂停会停止派发新批次，待在途请求落盘、进程退出后才显示已暂停。运行中保存设置采用同样的流程重新启动；使用同一个 live 目录续采、累计请求与代理预算。服务重启不会恢复用户已暂停的站点。代理 URL 只保存在隐藏控制数据库和子进程环境中，不从 API 回显、不进入下载包。

Debian 安装脚本会安装两个 systemd 服务；默认七站暂停，登录后点击开始。手动本机使用需另外运行 `.venv/bin/python controller.py --data data`（Windows 使用对应 Python 路径）；AffiliateFix 的浏览器采集仍需要 Linux/WSL。

持续模式不在 300 主题后停止。队列耗尽后显示等待更新，默认每 900 秒重新抓取已知目录发现新主题；已完成的旧正文不会自动重新同步编辑内容。失败阈值、代理累计流量上限和默认 2 GiB 剩余磁盘保护仍会停止采集，详情保留原因，不能将错误或等待状态视为正在发送请求。

已确认的 XenForo 登录限制主题记录为 `login_required`，保留失败响应且不计成功；持续模式继续处理其他公开主题，不因此触发整站连续失败停机或代理切换。识别要求原主题地址、原生登录模板、主区明确错误及站内登录表单同时成立；挑战页、未知 403 和传输错误仍执行原失败保护。

持续模式遇到有完整 301/308 证据链、且最终公开正文身份和板块均通过校验的主题迁移时，旧 URL 仍保留为失败；新 URL 按保存的跳转证据入队并独立请求，已有目标自动去重。离线验收同时核对跳转链和原始响应哈希，不把旧链接当作新增主题。

浏览器首次挑战等待预算至少 180 秒，后续按请求超时设置；两次挑战尝试共享等待预算。启动另设至少 180 秒超时。此保护针对依赖中的挑战等待循环，不是整个浏览器请求的绝对截止时间。网页暂停不强杀在途请求；systemd 服务关停等待 900 秒后才执行兜底清理。

浏览器传输明确启用 HTTPS 证书校验；Bright Data 配置使用 HTTPS 44445 入口，每站独立固定会话。七站的当前服务器设置以面板为准，源码默认配置仍保持初次安装不启用付费代理。

## 七站完整运行（Linux / WSL）

将代码包与数据包解压到同一个目录，两者共用 `forumcrawl/` 根目录；进入该目录后执行以下命令。已有数据用于查询和离线验收，新的网络测试请使用新的 `--run` 名称。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash install_browser.sh
xvfb-run -a .venv/bin/python run_all.py --affiliatefix-browser --chrome-sites namepros afflift blackhatworld --dnforum-all --target 300 --workers 3 --delay 1 --timeout 120 --run test300
```

请先进入项目目录。`install_browser.sh` 会安装可选浏览器依赖、Xvfb 和经哈希核对的 Chrome；系统依赖安装需要 sudo/root。`--affiliatefix-browser` 为 AffiliateFix 选择浏览器会话，线程数沿用 `--workers`；`--chrome-sites` 为指定站点选择 Chrome TLS 模拟，其他站点沿用公共 `--transport`（默认直接 HTTP）。如果同一站点同时出现在这两个选项中，AffiliateFix 浏览器优先。这里的三种方式对应 VPS 已验证可取得正文的组合。`--dnforum-all` 使用本轮已获同意的 DNForum 公开板块扩展范围；原始板块只有 98 个可验证主题，不足 300 个。

本次交付中的七个入口是 `namepros.py`、`dnforum.py`、`affiliatefix.py`、`blackhatworld.py`、`afflift.py`、`warriorforum.py`、`advertcn.py`，都接受相同参数。六个 HTTP 站点和面板也可以在原生 Windows 使用 `.venv\Scripts\python.exe` 运行；AffiliateFix 的已验证方法需要 Linux / WSL。例如：

```bash
.venv/bin/python namepros.py --transport chrome --run namepros300 --target 300 --workers 2
.venv/bin/python dashboard.py --port 8765
```

打开 `http://127.0.0.1:8765`，可查看进度、CPU、内存、主题正文和下载证据。默认仅允许本机访问。`CRAWL_DATA` 指定面板数据根目录，默认当前目录下 `data`；运行 controller 服务后可从面板控制采集。

`run_all.py` 会创建 `test300-namepros` 等每站独立运行目录，避免站点之间争用解析器和数据库写锁。所有其余参数转交给采集器。也可以直接执行 `crawl.py`，把多个站点放在同一个运行数据库中。

## 代理与参数

默认 `--proxy off`，完全不用代理。`--proxy on` 全程使用配置的代理池；`--proxy auto` 在直连返回连接错误、403、429、503 后切换代理，HTTP 模式同时启用 Chrome TLS 模拟，浏览器模式继续使用浏览器。凭据只从环境读取，不写入源码或客户报告。

```bash
export CRAWL_PROXY_URL='https://USERNAME:PASSWORD@brd.superproxy.io:44445'
.venv/bin/python namepros.py --proxy on --transport chrome --run namepros-proxy300
```

多个代理使用 `CRAWL_PROXY_URLS`，内容是 JSON 字符串数组；它优先于单条 URL。每个请求按序选择一个代理，会话内的重定向和 AdvertCN 验证保持同一个代理。要保持固定出口，可在供应商支持的账号参数中设置固定 session。此次本机测试确认 Bright Data 的 `https://...:44445` 可用，`http://...:44445` 超时；不要关闭 TLS 校验。自定义 CA 可通过 `CRAWL_CA_BUNDLE` 设置。

| 参数 | 默认 | 含义 |
|---|---:|---|
| `--target` | 300 | 累计有效的不同原生主题数量 |
| `--target-unit` | topics | `topics` 按不同主题计数；`pages` 按不同真实分页计数 |
| `--strict-consecutive` | 关闭 | 启用后要求单执行片段连续成功达到目标，否则连续数仅作诊断 |
| `--workers` | 2 | 每站工作线程数（1–16）；实际并发受会话锁、全局名额、内存与流量预留限制 |
| `--delay` | 1 | 每站请求批次之间的间隔秒数 |
| `--timeout` | 35 | 请求超时秒数；浏览器模式至少 90 秒 |
| `--max-requests` | 1500 | 每站页面任务上限，重定向/验证往返另记 hops |
| `--failure-limit` | 8 | 连续无效页面达到此数则停止该站 |
| `--proxy-mib` | 250 | 每个运行目录的代理响应正文预算；不等于供应商账单金额 |
| `--transport` | requests | `chrome` 模拟 Chrome TLS；`browser` 使用 Linux 有界面 Chrome 与 Scrapling，支持独立会话的多线程采集 |
| `--retry-failed` | 关闭 | 恢复运行时重新入队失败任务 |
| `--skip-research` | 关闭 | 跳过本轮 GitHub 复用检查 |
| `--continuous` | 关闭 | 持续增量模式，必须使用新运行目录 |
| `--rescan-seconds` | 900 | 持续模式队列耗尽后的目录复查间隔 |
| `--min-free-mib` | 2048 | 磁盘剩余容量保护 |
| `--stop-file` | 无 | 控制器使用的协作暂停标记 |
| `--dnforum-all` | 关闭 | DNForum 从首页发现其他公开板块；需要新运行名 |

用户给定本轮费用上限为 200 美元；程序保留更保守的字节上限。供应商可能对请求、响应头和其他流量计费，本项目无法通过页面正文推导精确账单。要执行严格美元限额，请同时设置供应商账户的预算限制；程序不会自行购买服务或提升账户配额。

默认每轮先查询用户指定的四个 GitHub 仓库，记录更新时间、许可证和复用决策至 `github-review.json`，不会自动运行远程仓库代码。HTTP 采集复用 requests、BeautifulSoup 和 curl_cffi；AffiliateFix 的可选浏览器模式复用 Scrapling 与 Patchright。

## AffiliateFix 浏览器采集

Linux 下的 `browser` 模式复用 Scrapling 的浏览器会话，可以在没有人工操作的新临时配置中完成本轮观察到的 Cloudflare 验证。每个浏览器工作线程使用独立会话与私有配置目录，重试保留目标的会话槽；槽 0 兼容原有单线程会话。浏览器最多同时运行 2 个，内存不足时排队，调高线程数不保证等比例提速。无显示器的 Debian 服务器通过 Xvfb 提供显示环境。安装可选浏览器依赖后，执行：

```bash
xvfb-run -a .venv/bin/python affiliatefix.py --transport browser --workers 1 --timeout 120 --proxy off --target 300 --run affiliatefix-browser300
```

浏览器默认使用项目 `.browser/chrome-linux64/chrome`，也可通过 `CRAWL_BROWSER_EXECUTABLE` 指定兼容的 Chrome。每次运行从临时配置开始，同一次运行保留验证会话。保存的是浏览器实际收到的最终 HTTP 文档正文，而不是重建的 DOM；挑战和跳转的主文档响应也保留为 `*-browser*.bin`。只有最终正文通过相同的身份、归属与内容检查才计入主题数。

Debian 专用服务用户的 HOME 与程序目录可以保持只读；只需运行的数据目录可写。适配器为 Chrome 子进程把 `XDG_CONFIG_HOME`、`XDG_CACHE_HOME` 指向临时 profile 内的可写目录，供配置、缓存及 Crashpad 使用，关闭会话时一并清理；不会改动 Python 进程的全局环境变量。

浏览器代理请求每次预留 50 MiB，再按观察到的资源响应正文流量扣减；HTTP 请求保持约 8 MiB 预留。浏览器触及资源限制会停止加载并记录失败，但已在途资源可能超出限制，计量方式与限制写入 `browser_meta`，不宣称精确网络流量或供应商账单。最终 HTML 限制为 8 MiB。异常退出无法恢复实际流量时保守扣除整笔预留。直连命令不使用付费代理。

## 范围与验收

- NamePros：仅 `domain-parking-and-traffic-monetization.126`，线程须有对应板块证据。
- DNForum：默认仅 `domain-monetization`，线程须有对应板块证据；明确启用 `--dnforum-all` 时可采集其他公开板块。
- AdvertCN：从 `forum.php?gid=1` 的 `#category_1` 实际链接取得板块 ID，并验证主题面包屑。
- AffiliateFix、BlackHatWorld、affLIFT、WarriorForum：从公开目录发现的主题及其分页。没有提供登录账号，付费或登录门槛不会被当作成功正文。

只跟随实际观察到的目录链接和线程自身分页，不根据 ID 猜测主题。默认目标是每站 300 个不同原生主题，同一主题的多个分页只贡献一个主题计数。调度优先取新主题首页，其次取目录续页，最后取主题后续分页，因此达到 300 个主题不代表已经采完这些主题的全部回复或整个板块。需要按分页计数时显式指定 `--target-unit pages`。

每站 `accepted_topics` 是累计不同主题数，`accepted_pages` 是累计有效分页数，`accepted` 对应所选目标单位；默认累计主题数达到目标即通过采集目标。原生身份、正文、归属或重复检查失败均留下证据，失败数量不会因后来成功而清零。

连续数按已记录的处理顺序计算：失败的主题尝试打断连续数，目录页不计数，主题模式下同一主题的后续有效分页保持连续数不变。`max_consecutive` 默认仅作诊断，只有 `--strict-consecutive` 才将其作为达标条件。断点恢复开启新的连续片段，不跨进程中断拼接连续数。

```bash
.venv/bin/python verify.py --data data --run test300-namepros --workers 4
```

验收器从保存的响应重新解析，并校验身份、哈希、正文重复、来源链、数据库和连续计数。它不信任面板的汇总成功数。

## DNForum 扩大公开板块范围

本轮原始 `domain-monetization` 板块的三页目录列出 99 个主题，其中一个跳转至其他板块；其余 98 个主题共 104 个可验证分页，已全部采集。这个公开快照不足以提供 300 个不同主题。

用户随后授权加入 DNForum 的其他公开板块。使用下面的显式参数从首页观察到的链接继续发现公开板块；原始板块运行及其失败记录保持独立。

```bash
.venv/bin/python dnforum.py --dnforum-all --run dnforum-expanded300 --target 300 --workers 2 --delay 1
.venv/bin/python verify.py --data data --run dnforum-expanded300 --workers 4
```

扩大范围的开关写入 `LEDGER.jsonl` 的 `run_start.settings.dnforum_all`，首页种子与板块限制写入 `summary.json` 的 `scope`。请使用新的运行名，并在恢复该运行时继续提供 `--dnforum-all`。默认 DNForum 入口的原始板块限制不变。

## 数据与恢复

本机数据包 `forumcrawl-data.zip` 与代码包共享 `forumcrawl/` 根目录。VPS 的独立复测数据另存为 `forumcrawl-vps-data.tar.gz`，其中的顶层目录是 `vps300-20261006-站点`；可用以下方式导入同一个面板。两轮采集有主题重叠，不应相加当作全局不同主题数。

```bash
mkdir -p forumcrawl/data
tar -xzf forumcrawl-vps-data.tar.gz -C forumcrawl/data
```

```text
data/<run_id>/
  responses/<site>/<request_id>.bin    收到的最终响应正文
  responses/<site>/*-hop*.bin          验证等中间响应
  identity/<site>/<request_id>.json    URL、哈希、状态、来源和校验结果
  corpus/<site>/<thread_id>-<page>.json 结构化正文与证据
  corpus.sqlite                       队列、页面、主题、帖子、版本与出现记录
  LEDGER.jsonl                        请求开始、结果、片段与停止事件
  summary.json                        面板状态
  github-review.json                  本轮复用检查
  verification.json                   独立验收结果
```

`.bin` 是应用收到的正文（HTTP 内容压缩已由客户端解压），不是 TCP/TLS 抓包。原始页面按请求保存；SQLite 的去重键包括站点与原生 ID。`topics` 保存主题最近采集页的记录，完整分页以 `pages` 与 `corpus` 为准；`posts` 是最近版本，`post_versions` 保留不同正文版本，`occurrences` 保留来源请求。解析保留作者、可确定时间、正文和资源引用；无法确定的时间为 null，不猜测。图片与附件仅保留引用，不代表已下载附件。

用相同 `--run` 恢复持久化待办队列，例如：

```bash
.venv/bin/python namepros.py --run namepros300 --target 300 --retry-failed
```

同一运行目录只允许一个采集进程。恢复时必须保持目标单位和范围；旧运行未记录 `target_unit` 时按 `pages` 解释，不能作为新的主题目标运行恢复。需要不同目标单位、不同范围或独立验收时请使用新 `--run`。采集与面板可以同时运行，SQLite 使用 WAL；从面板下载数据库会创建一致性备份。

## Debian 12 公网 IP + 端口

把代码目录复制到服务器，不需要域名。安装脚本需要 root，会安装 venv、创建服务用户、生成私有密码及 IP SAN 自签 TLS 证书，并启动面板和采集控制服务：

```bash
sudo bash install.sh 203.0.113.10 8443
sudo cat /etc/forumcrawl/dashboard.env
sudo systemctl status forumcrawl-dashboard
```

把示例 IP 换成真实公网 IPv4，在服务器和云防火墙放通选定端口，访问 `https://服务器IP:8443`。使用环境文件中的随机密码登录。自签证书需要在客户端核对安装脚本显示的 SHA-256 指纹并信任；如已有可信 IP 证书，可替换 `/etc/forumcrawl/server.crt` 和 `.key`。密码、签名密钥、TLS 私钥不应放入报告或公开下载区。

浏览器依赖需先安装。可在首页分别开始持续采集；也可单独执行一次有限验收：

```bash
sudo bash /opt/forumcrawl/install_browser.sh
sudo -u forumcrawl xvfb-run -a /opt/forumcrawl/.venv/bin/python /opt/forumcrawl/run_all.py --affiliatefix-browser --chrome-sites namepros afflift blackhatworld --dnforum-all --target 300 --workers 1 --timeout 120 --data /opt/forumcrawl/data --run test300
```

首次安装的七站保持暂停；升级保留运行／暂停意图。命令行代理密钥通过受限环境传入，面板代理设置由控制器注入子进程环境。安装不自动修改防火墙或上传本机数据；需要带入已有数据时，复制 `data` 并把其属主设为 `forumcrawl`。

已在独立 Debian 12 / Python 3.11.2 VPS 实际完成安装，七站各 300 个主题均通过独立验收。公网密码登录、正文查看、原始文件下载和 SQLite 一致性快照检查通过；专用服务用户的浏览器启动修复已部署。采集过程与各运行片段保留在账本中。

## 扩展与检查

首页“添加站点”可输入公开入口网址，默认自动识别页面。高级选项提供 XenForo、vBulletin、Discuz、通用 HTML，以及正文/链接 CSS 选择器。新站先保存为暂停；设置代理、速率后点开始。域名和目录范围在创建时固定，变更范围请建立新站。每个运行保存带哈希的 `site-profiles.json`，恢复和离线验收使用这个快照，避免后来修改配置改变历史解释。

通用 HTML 保存实际规范 URL 身份及完整正文块，文件名用 URL 哈希；有充分原生论坛证据的页面才保存原生主题/帖子 ID。面板对新增站显示“条目”，不会把普通网页算成已证实的论坛主题。只跟随范围内实际发现的链接，查询参数保留；公开地址检查拒绝内网、元数据地址和带凭据 URL。自定义站点 HTTP/TLS 连接固定已校验的公网地址；浏览器子资源的同等网络隔离尚未实现，因此自定义站点浏览器回退会明确跳过，原七站浏览器能力保留。

通用站点在队列耗尽后按间隔重访入口，发现新链接；入口已有的正文副本保持不变，刷新响应单独留证。需要追踪深层目录时，把该目录作为新站入口；这不代表已经发现全站所有 URL。

可选模块复用已安装能力：`tls_fallback`（curl_cffi）、`browser_fallback`（浏览器）、`retry_backoff`（暂时错误的有界重试）。没有近期有效经验时先尝试基准，成功后不执行回退；同一配置、页面类型的可选方法累积至少 3 个有效样本、连续失败少于 2 次且最近成功不足 24 小时，才可优先采用。配置或代理配置变化使旧经验失效。缺失可选依赖、不可用能力或不足以预留回退流量时记录跳过原因。每次真实请求独立计数、保存响应与失败证据；同一失败目标最多 5 次尝试，暂停恢复和重排失败任务不会清零。代理开启时所有策略仍走代理。登录、付费、证书校验失败和预算保护不能用回退伪装为成功；没有保证任意网站均能采集的开关。

浏览器回退按需启动独立子进程，总期限包含启动和导航，取消或超时清理整个子进程树。Linux 可选依赖与 Xvfb 均可用时使用 Xvfb；缺少 Xvfb 时不阻止 HTTP 基线，没有显示环境的浏览器使用无头模式。原七站直接选择浏览器为主传输时仍使用 Xvfb。当前为公平释放共享名额，每次尝试关闭浏览器进程；同一逻辑会话复用私有配置目录，但强杀前未刷盘的 Cookie 不保证恢复。

会话按站点、传输、客户端版本及代理配置隔离，CookieJar 保留域、路径、有效期等属性，Requests 每跳显式执行 host-only 限制。`.sessions.sqlite`、`.session-locks`、`.browser-profiles` 均为私有数据，不可从面板下载。该机制不证明代理实际出口 IP 稳定，不做跨引擎完整会话迁移，也不缓存一次性验证码令牌。每次请求的不可变脱敏计划写入 SQLite `execution_plans`，完成结果仍以 `fetches` 为准，JSONL 用于诊断和导出。

429 和带 `Retry-After` 的普通 5xx 按完整期限冷却，重启保留期限，不因此升级浏览器。可选方法连续网络失败触发按站点/方式/错误类型保存的熔断，冷却后只放行一个半开探测。等待会话、浏览器名额或冷却不计作一次网络失败。200 仍需验证正文与身份，离线重解析已有 `reparse.py`；动态 JS 空壳的通用渲染提取尚未实现。

跨进程资源账本位于 `.control/runtime.sqlite`：浏览器最多 2 个，每个预留 1024 MiB，并保留 512 MiB 内存底线；不足时排队。启动前保留完整预留；启动后绑定子进程身份，只补足“1024 MiB 减去已实测进程树 USS”的剩余预留，避免对已被系统扣除的内存重复预留。USS 不重复累计共享页；进程消失、身份不符或无法采样时保留完整预留。该估计是准入保护，不是操作系统硬内存限制，线程数不保证同时运行的浏览器数。面板按真实租约显示“浏览器运行 X · 等待资源 Y”，区分内存、槽位和排队；一个线程等待不会覆盖另一个线程正在运行的状态。

持续采集按完成顺序验证、入库和更新计数，已完成页面不再等先提交的慢页面；有限验收仍保持原提交顺序。每批结束后的配置间隔、同会话串行锁、每页关闭浏览器释放共享名额仍保留，因此不是无限制的连续满载。请求结果的 `browser_meta` 新增 `resource_wait_seconds`、`worker_startup_seconds`、`browser_launch_seconds`、`browser_close_seconds`，分别记录资源排队、Python 子进程准备、浏览器启动和关闭的实测耗时；缺失表示该阶段没有完成或旧记录未测量。`seconds` 是抓取及关闭等总耗时，不含资源排队，不能再与其包含的分项重复相加。

代理流量先原子预留，再按观测正文结算，异常中断按保守额度入账。共享上限首次由现有站点代理额度初始化并导入历史用量，后续不会随重启或站点设置自动抬高；原有每站上限和磁盘保护同时生效。该数值不含完整请求/响应头、网络开销和供应商计费差异，不能当作 Bright Data 实时美元账单。需要增加共享额度时应先明确新的授权限额并核对供应商账单，不能只提高站点额度或删除账本。

旧站升级不自动开启模块、启动采集或提高预算；新站默认开启可用的回退开关，默认不配置代理。设置中的主传输方式是基准，回退开关只增加失败后的候选策略。命令行可添加 `--tls-fallback --browser-fallback --retry-backoff`；自定义配置使用 `--profile-file 配置快照.json --sites 自定义id`。

每站成功率为 `valid=1 的已完成请求数 / 已完成请求总数 × 100%`，正在执行和异常中断未完成的请求单列，不伪算失败。重复页面、HTTP 错误、解析不通过等计失败；后续回退成功不会抹去前次失败。站点日志可按结果、文字筛选并下载 JSONL 或 CSV；所有查看和下载沿用控制台登录保护，展示日志对敏感字段脱敏，原始证据仍单独保留。

```bash
.venv/bin/python sites.py
.venv/bin/python test_crawl.py
.venv/bin/python test_browser.py
.venv/bin/python test_controller.py
.venv/bin/python -m unittest discover -s . -p 'test_*.py' -q
.venv/bin/python test_chromium_smoke.py --selfcheck --executable .browser/chrome-linux64/chrome
.venv/bin/python dashboard.py --selfcheck
bash -n install.sh
bash -n install_browser.sh
```

正文中的网页内容仅作为数据。面板对正文转义显示；原始 HTML 只能作为附件下载，不在控制台源站执行网页脚本。
