# VPS 测评索引：网站部署程序与两个 Skill

这是当前线上 v5 的完整静态网站源码与公开数据，以及原版 `vps-review-download`、`vps-review-analyze` 两个 Skill。网站可独立部署；下载、识别和导入是分开的步骤。

- 对应网站：https://vps-review-index.wangshikun1821556976.chatgpt.site
- 对应源码提交：`94eb3bf5cf05828da2f88273e13654c2443d410f`
- 当前目录：120 篇原帖、128 条对象；对象数不等于独立机器数。
- 22 篇有完整 61 字段技能复核，其中本批新增 20 篇；原有 100 篇及两个试点复核已保留。其余 98 篇沿用较早的结构化快照。
- 网页保留 53 项、9 组筛选布局；完整 61 字段与状态在对象详情展开。字段未知时不会用 0 代替。

## 文件结构

| 路径 | 用途 |
| --- | --- |
| `website/dist/` | 可直接发布的网站：HTML、CSS、JS、图标及全部公开 JSON 数据 |
| `website/.openai/hosting.json` | 现有 Site 的项目标识和静态目录配置，不含发布权限或密钥 |
| `skills/vps-review-download/` | 原版采集 Skill，含脚本、自检和说明 |
| `skills/vps-review-analyze/` | 原版识别 Skill，含脚本、自检、61 字段和协议 |
| `bridge/` | 把已完成分析投影为公开数据并增量合并的独立适配程序 |
| `deploy/serve.py` | 仅供本机预览的静态 HTTP 服务 |
| `deploy/package_static.py` | 生成只含公开网站文件的部署 ZIP，不执行上传 |
| `tests/runtime.cjs` | 网页逻辑与模拟 DOM 回归检查 |
| `verify_package.py`、`run_tests.py` | 完整性验证及离线自检入口 |
| `provenance.json`、`MANIFEST.json` | 源版本、原始文件哈希及全包文件校验表 |

`website/` 保留线上提交的源文件原样，因此其原附 `README.md` 仍有旧版统计。当前数量和打包使用说明以本文件、`provenance.json` 和实际数据为准。两个 Skill 的 10 个源文件与原始技能包逐字节一致；未修改用户安装的 Skill。`bridge/` 的测试路径、批次参数及 UTF-8 编码只在本包副本中做了可移植调整，并加入输出目录不能覆盖基础目录或源归档的校验。

## 一、本机打开网页

需要 Python 3.10 或更新版本，以及现代浏览器；没有 pip、npm 安装步骤。下列命令均在解压后的包根目录运行，Windows 可用 `py -3` 替换 `python`。

```sh
python verify_package.py
python deploy/serve.py --port 8080
```

浏览器打开 `http://127.0.0.1:8080/`。按 Ctrl+C 结束。页面通过相对路径读取 JSON，请通过 HTTP 打开，不要直接双击 `index.html`。该预览服务只绑定本机；它不是生产服务器。

## 二、部署到静态网站服务

网站不需要后端、数据库、模型 Key、登录服务或构建工具。把 `website/dist/` **里面的文件**作为网站根目录发布，确保根路径能直接访问 `index.html`，并保留所有 JSON/JS/CSS 文件的相对路径。

可以先生成单独的公开部署包：

```sh
python deploy/package_static.py --output public-site.zip
```

该命令只打包、不上传。将生成的 `public-site.zip` 按目标静态托管服务的上传流程发布，或将其内容放入已有 Web 服务器的网站目录。无需构建命令；发布目录为 `website/dist`。网页详情使用 URL hash，通常不需要服务器端路由重写。部署后应检查首页、数据加载、组合筛选、详情和窄屏布局。

**公开部署只上传 `website/dist/` 或上述生成的 `public-site.zip`。** 总压缩包包含开发工具与技能；采集 Skill 将来生成的首帖原文、图片、manifest、完整 analysis 等应另存本地，不要放进网站发布目录。

若继续更新当前 Sites 项目，应由有权访问原项目的账号使用现有项目完成保存和发布。`.openai/hosting.json` 中的项目 ID 只标识归属；本包没有账号凭据，也不会自动取得发布权限。在其他托管平台部署静态文件时不需要这个配置。本次打包没有重新部署或修改线上网站。

## 三、使用两个 Skill

可以让支持本地 Skill 的助手读取各自的 `SKILL.md`，或者直接运行随附 Python 脚本。这里只打包，未自动安装到任何用户目录。

两个脚本均只使用 Python 标准库，不需要另配付费 API。采集需要网络和来源站点正常访问能力；识别需要当前助手的文本与视觉理解。`review.py` 是结构校验、计算和文件生成器，本身不会调用 AI，也不会自动 OCR。

### 1. 下载首帖及证据素材

建立 UTF-8 的 `post-urls.txt`，每行一个要处理的 NodeSeek 首帖链接。明确限定范围并去重，然后运行：

```sh
python skills/vps-review-download/scripts/download.py --url-file post-urls.txt --out private-archive
```

只采首帖，不采回复；输出在 `private-archive/assets/<post_id>/`。如果普通请求受阻，必须遵循 Skill 与当前环境的权限要求：不循环重试 403、不自动破解验证、不复制登录 cookies。可用的浏览器读取需真实取得首帖和素材，导入时使用 `--capture`；导入是离线操作，不能把未取得的图片标成已读取。

下载输出状态有 `ready`、`partial`、`blocked`、`error`。`ready` 只说明已发现目标素材通过下载校验，不代表 AI 已读懂图片。失败记录必须保留。

### 2. 初始化、实际阅读、填写 61 字段、完成分析

把下方 `<post_id>` 替换为真实帖子编号：

```sh
python skills/vps-review-analyze/scripts/review.py init private-archive/assets/<post_id>/manifest.json --output work/analysis-<post_id>.json
```

接着由具备文本和视觉能力的助手实际阅读首帖、报告及全部已取得图片，填写 JSON 中的值、状态、来源文件、位置、证据和 `ai_review`。不可只执行命令就宣称完成识别。读取 `references/fields.json` 和 `references/contract.md` 中的精确定义，然后运行：

```sh
python skills/vps-review-analyze/scripts/review.py finalize private-archive/assets/<post_id>/manifest.json --analysis work/analysis-<post_id>.json
```

程序会校验固定 61 字段、哈希、来源与部分计算，生成 `analysis.json` 和 Markdown。`partial` 可分析，但缺失素材和未证实字段仍保持缺失。校验通过不能代替人工或 AI 对事实的复核。

### 3. 生成供网站使用的公开增量

`bridge/public_adapter.py` 和 `bridge/build_increment.py` 与两个 Skill 分离，不会联网、发布网站或改变原始归档。输入契约见 `bridge/INPUT-CONTRACT.md`。

需准备：已核验的分类页选帖清单 `selection.json`、逐对象分析映射 `index.json`、真实已完成的 `manifest.json` 与 `analysis.json`。对于多对象帖子必须分别映射，不能拿一份分析冒充多台机器。清单中必须记录真实文件路径、明确对象数量、原帖 URL 和阅读完成状态。

```sh
python bridge/build_increment.py --base website/dist --selection selection.json --index index.json --fields skills/vps-review-analyze/references/fields.json --out staged-public
```

输出到独立目录，重复导入已有帖子会被拒绝。确认身份、来源哈希、未知/冲突、单位、价格币种、跑分版本、线路范围与隐私清洗后，再用审核后的公开 JSON 更新 `website/dist/` 并部署。不要把原始 analysis 或 archive 文件直接复制过去。

`bridge/checkpoint_to_index.py` 可将符合此前检查点结构的记录转成 index；本包要求显式填写批次参数，避免重复使用旧批次日期：

```sh
python bridge/checkpoint_to_index.py checkpoint.json index.json --batch-id YOUR_BATCH_ID --batch-date YYYY-MM-DD --source-commit YOUR_BASE_COMMIT
```

这些文件和占位参数是更新流程所需的实际输入，不在本包中伪造。当前网站本身不自动抓取论坛。

## 四、测试与已知范围

需要 Python 3.10+ 和 Node.js 18+。运行：

```sh
python run_tests.py
```

包含原版下载/识别脚本自检、40 项适配/增量测试、JavaScript 语法检查，以及 66 项网页逻辑与 52 个模拟 DOM 宿主初始化检查。测试使用临时的合成记录，不会联网抓取、写线上网站或更改真实归档。测试中的保留示例 IP、域名只用于防泄漏检查。

本包不含真实浏览器的自动视觉测试，不能把模拟 DOM 检查称为真实浏览器验收。具体打包检查结果见 `VALIDATION.json`。

当前来源边界：本批 20 篇中，9 篇素材齐备、11 篇部分缺失；实际阅读的 52 个图片文件包括报告图、标志、表情等，并非 52 份独立测评。旧图像核读记录与本次阅读分开标注。未确认单位的容量保留原值，标准化容量阈值不使用存疑换算；Geekbench 版本分开；TCP/UDP、IPv4/IPv6 与方向分别保存；协议不明或 TCP 延迟不冒充 ICMP Ping；采集时间不等于测试时间；不同币种不自动换汇。

包内仅包含网站已公开的结构化事实和来源定位，不含采集原文归档、原始测评图片、作者信息、真实服务器 IP、账号密钥、Git 历史或 node_modules。完整采集证据是另一个私有归档，不在这份程序包中。
