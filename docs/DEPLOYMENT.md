# 部署、备份与运维

## 运行条件

Python 3.11+、完整源码目录和本地可写数据目录即可运行；程序运行时无第三方 Python 依赖。`vps_pipeline/vendor/vps-review-analyze/` 必须随源码保留。本说明提供部署步骤，交付过程没有在 Debian 上安装服务、开放端口、配置账户或修改现有公网网站。

Windows 在源码根目录运行：

```powershell
python --version
python -m vps_pipeline --data .\var init
python -m vps_pipeline --data .\var serve --host 127.0.0.1 --port 8765
```

可使用 Python Launcher `py -3.11` 替代 `python`，以本机已安装版本为准。不需要执行 `pip install`。目录不要位于会同步公开或供其他用户任意写入的位置。

## Debian 12 前台运行

先确认已安装 Python 3.11+；以下路径是部署示例，须由操作者按实际目录准备完整源码。

```sh
cd /opt/vps-review-pipeline
python3 --version
python3 -m unittest discover -s tests -v
python3 -m vps_pipeline --data ./var init
python3 -m vps_pipeline --data ./var serve --host 127.0.0.1 --port 8765
```

前台方式适合首次验收。控制台显示管理地址及本次 session token；每次服务重启 token 改变。不要设置持久 API key，也不要将 token 放入 URL 或公开日志。

## 可选 systemd 服务

`deploy/vps-pipeline.service` 只启动回环管理服务，不会开始网络采集。它假定源码在 `/opt/vps-review-pipeline`、数据在 `/var/lib/vps-review-pipeline`、运行账户为 `vps-pipeline`。服务文件不会创建账户或授权目录；操作者明确决定安装时自行执行：

```sh
sudo useradd --system --user-group --home-dir /var/lib/vps-review-pipeline --no-create-home --shell /usr/sbin/nologin vps-pipeline
sudo install -d -o vps-pipeline -g vps-pipeline -m 0700 /var/lib/vps-review-pipeline
```

若账户已存在，先核对其用途，不要重复创建。将完整源码放入指定目录，保证服务账户可读取和遍历源码目录，但不能修改源码。然后：

```sh
cd /opt/vps-review-pipeline
sudo -u vps-pipeline /usr/bin/python3 -m vps_pipeline --data /var/lib/vps-review-pipeline init
sudo install -o root -g root -m 0644 deploy/vps-pipeline.service /etc/systemd/system/vps-pipeline.service
sudo systemctl daemon-reload
sudo systemctl start vps-pipeline
sudo systemctl status vps-pipeline
sudo journalctl -u vps-pipeline -n 20 --no-pager
```

日志中包含本次 session token，只有受信管理员应可读取，不能转发到公共日志系统。验证配置和访问后，如确需开机启动，再由操作者执行 `sudo systemctl enable vps-pipeline`。本例不会自动启用服务、配置防火墙或采集计时器。

服务示例限制源码写入、授予数据目录写入权，并限定地址族；仍必须保持管理端仅回环绑定。不要去掉本机监听限制、把数据目录加入 nginx 根目录，或把管理 API 代理到公网。

## 通过 SSH 访问管理页面

使用现有已授权 SSH 连接。Windows 或另一台电脑上运行：

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 user@server
```

保持隧道开启，在本机打开 `http://127.0.0.1:8765/`，填入远端本次 token。示例两端使用相同端口，以满足管理端精确 Host 检查；如 8765 已被占用，先为远端服务和本地转发选定同一个空闲端口。无需新增永久凭据或公网管理端口。

## 安全筛选站发布

0.2.0的export-public/export-v5仅导出安全筛选网站。目标必须位于私有数据目录之外；不要沿用早期版本把包含原证据的导出目录公开的做法。示例：

    python3 -m vps_pipeline --data /var/lib/vps-review-pipeline export-public /srv/vps-review-staging/site-001

该命令不发布、不开放端口。审核后由部署操作者把该静态目录放入公开站点。deploy/nginx-public.conf.example只允许固定网页资源与公开JSON，默认监听本机8080，绝不反代管理API，也不提供evidence/路径。应用前检查路径和权限并运行nginx -t；公网域名、TLS和实际发布须另行明确。

export-evidence是私有原文/原图导出，可能有IP和作者信息，不能放入站点。/catalog/本机页面无需token，但管理根页/API仍需本次token；两个用途分开。

## 备份

SQLite 使用 WAL。备份应包含数据库、可能存在的 `-wal`/`-shm` 与整个 `archives/`；只复制一个正在写入的 `.sqlite3` 文件不足以形成一致备份。最直接的方法是停止管理服务和所有 CLI 写入，确认无活动采集/导入，再复制整个私有数据目录。工作包和人工完成的 envelope 如果保存在目录外，也需另行保留。

Debian 示例（目录名需每次更新，保留既有备份）：

```sh
sudo systemctl stop vps-pipeline
sudo install -d -m 0700 /srv/vps-review-backups
sudo tar -C /var/lib -czf /srv/vps-review-backups/pipeline-backup-YYYYMMDD-HHMMSS.tar.gz vps-review-pipeline
sudo chmod 0600 /srv/vps-review-backups/pipeline-backup-YYYYMMDD-HHMMSS.tar.gz
sudo systemctl start vps-pipeline
```

运行前确认同名备份不存在，避免覆盖。Windows：用 `Ctrl+C` 停止服务，确认其他终端也停止写入，再用 `Copy-Item -LiteralPath .\var -Destination .\backup-NEW -Recurse` 复制到不存在的新目录。备份包含任务证据和提交记录，应限制读取权限；token 不在数据库持久保存。

## 恢复与失败处理

先停止所有使用该数据目录的进程，把备份恢复到新私有目录，保留原故障目录用于核查。不要把未知 ZIP 直接解压到源码、系统目录或正在使用的数据目录。

```sh
cd /opt/vps-review-pipeline
python3 -m vps_pipeline --data /path/to/restored-data list
python3 -m vps_pipeline --data /path/to/restored-data recover
python3 -m vps_pipeline --data /path/to/restored-data show JOB_ID
```

恢复命令只释放已经过 600 秒租约的操作，不处理仍有效的租约，也不会杀死原进程。归档/任务包/提交会重新验证证据哈希。恢复副本检查成功后，再更新服务数据路径与权限并启动服务；重新读取本次 token。

| 情况 | 操作 |
|---|---|
| `blocked` | 停止联网尝试；查看原因，必要时导入合法取得的本地公开证据 |
| `failed` / `cancelled` | 先解决原因，使用 `retry ID` 恢复，再明确执行下一步 |
| `awaiting_analysis` | 导出工作包，等待真实核读，不设置虚假的完成标记 |
| envelope 哈希不匹配 | 确认分析对应归档；重新导出正确工作包，不改哈希凑匹配 |
| 图片缺失或区域不可读 | 在归档失败及核读 issues 保留说明，对应字段保持未知 |
| 看到 `.import.lock` | 这是保留的锁文件，进程退出时操作系统自动释放锁；不要删除文件，锁冲突时确认实际持锁进程 |
| 导出目录非空 | 选择新目录，避免混合旧版文件 |

## 验收边界

离线测试命令是 `python3 -m unittest discover -s tests -v`；原技能测试为 `python3 vps_pipeline/vendor/vps-review-analyze/scripts/test_review.py`。fixture 使用合成数据，网络测试使用替身。0.2.0 完整验证环境为 Debian 13.6 / Python 3.12.14；Debian 12 / Python 3.11、Windows 0.2.0 全量实机验收以及生产 systemd/nginx 安装尚未执行。历史结果和当前限制见 [验证摘要](../validation/integrated-test-report.md)。Python 3.11 语法检查不等于该版本的运行验证。
