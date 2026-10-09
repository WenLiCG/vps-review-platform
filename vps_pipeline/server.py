"""Private loopback management API. Evidence HTML is never served or executed."""

from __future__ import annotations

from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import socket
import tempfile
from urllib.parse import urlsplit

MAX_BODY = 4 * 1024 * 1024
MAX_TASK_BYTES = 256 * 1024 * 1024
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_STYLE = """
body{font:16px system-ui,sans-serif;max-width:1080px;margin:2rem auto;padding:0 1rem;color:#18212d;background:#f6f8fb}
h1{font-size:1.7rem}section{background:white;border:1px solid #dbe2ea;border-radius:10px;padding:1rem;margin:1rem 0}
input,button{font:inherit;padding:.55rem;border:1px solid #9aa8b7;border-radius:5px;margin:.2rem}
button{cursor:pointer;background:#edf3ff}input[type=url]{width:min(90%,580px)}table{border-collapse:collapse;width:100%;font-size:.9rem}
td,th{text-align:left;border-bottom:1px solid #dbe2ea;padding:.6rem;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.note{color:#44556a}#message{min-height:1.4em;white-space:pre-wrap}.table{overflow-x:auto}label{display:inline-block;margin:.5rem 0}
"""

_SCRIPT = """
'use strict';
const $=id=>document.getElementById(id);
let token=sessionStorage.getItem('vpsSessionToken')||'';
let selected='';
$('token').value=token;
function message(value){$('message').textContent=value;}
async function request(path,body){
 const options={headers:{'X-VPS-Token':token},cache:'no-store'};
 if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
 const response=await fetch(path,options);
 if(!response.ok){const error=await response.json();throw new Error(error.error||'请求失败');}
 return response;
}
function action(fn){return async()=>{try{await fn();}catch(error){message(error.message);}};}
function needSelection(){if(!selected)throw new Error('请先选择一个任务');return encodeURIComponent(selected);}
async function detail(id){selected=id;const response=await request('/api/jobs/'+encodeURIComponent(id));$('detail').textContent=JSON.stringify(await response.json(),null,2);$('selected').textContent=id;}
async function refresh(){
 const response=await request('/api/jobs');const jobs=await response.json();$('rows').replaceChildren();
 for(const job of jobs){const row=document.createElement('tr');
  for(const value of [job.id,job.status||job.state,job.source_url,job.error||job.last_error||'']){const cell=document.createElement('td');cell.textContent=typeof value==='object'?JSON.stringify(value):String(value??'');row.append(cell);}
  const cell=document.createElement('td'),button=document.createElement('button');button.textContent='选择';button.addEventListener('click',action(()=>detail(job.id)));cell.append(button);row.append(cell);$('rows').append(row);
 }message('已载入 '+jobs.length+' 个任务');
}
async function refreshLegacy(){
 const response=await request('/api/legacy');const records=await response.json();$('legacy-rows').replaceChildren();
 for(const record of records){const row=document.createElement('tr');
  for(const value of [record.post_id,record.status,record.archive_status,record.fact_count,record.image_count,record.missing_resource_count]){const cell=document.createElement('td');cell.textContent=String(value??'');row.append(cell);}
  const cell=document.createElement('td'),button=document.createElement('button');button.textContent='查看原分析与来源';button.addEventListener('click',action(async()=>{const result=await request('/api/legacy/'+encodeURIComponent(record.id));$('legacy-detail').textContent=JSON.stringify(await result.json(),null,2);}));cell.append(button);row.append(cell);$('legacy-rows').append(row);
 }$('legacy-count').textContent=String(records.length);
}
$('connect').addEventListener('click',action(async()=>{token=$('token').value.trim();sessionStorage.setItem('vpsSessionToken',token);await refresh();await refreshLegacy();}));
$('forget').addEventListener('click',()=>{token='';$('token').value='';sessionStorage.removeItem('vpsSessionToken');$('rows').replaceChildren();$('legacy-rows').replaceChildren();$('legacy-detail').textContent='';$('legacy-count').textContent='0';$('detail').textContent='';selected='';$('selected').textContent='未选择';message('已清除本标签页的 token');});
$('refresh').addEventListener('click',action(refresh));
$('legacy-refresh').addEventListener('click',action(refreshLegacy));
$('add').addEventListener('click',action(async()=>{await request('/api/jobs',{source_url:$('url').value.trim()});await refresh();}));
for(const name of ['retry','cancel']){$(name).addEventListener('click',action(async()=>{await request('/api/jobs/'+needSelection()+'/'+name,{});await refresh();await detail(selected);}));}
$('ingest').addEventListener('click',action(async()=>{const id=needSelection(),file=$('html').files[0];if(!file)throw new Error('请选择已保存的 HTML');if(file.size>4*1024*1024)throw new Error('文件超过 4 MiB');await request('/api/jobs/'+id+'/ingest',{html:await file.text()});await refresh();await detail(selected);}));
$('submit').addEventListener('click',action(async()=>{const id=needSelection(),file=$('analysis').files[0];if(!file)throw new Error('请选择分析 envelope JSON');if(file.size>4*1024*1024)throw new Error('文件超过 4 MiB');await request('/api/jobs/'+id+'/submit',{envelope:JSON.parse(await file.text())});await refresh();await detail(selected);}));
$('task').addEventListener('click',action(async()=>{const id=needSelection(),response=await request('/api/jobs/'+id+'/task'),blob=await response.blob(),url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download='analysis-task-'+selected+'.zip';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('已导出待真实助手核读的工作包');}));
if(token)action(async()=>{await refresh();await refreshLegacy();})();
"""


def _page(nonce: str) -> bytes:
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VPS 测评任务管理</title><style nonce="{nonce}">{_STYLE}</style>
<h1>VPS 测评任务管理</h1><p class="note">本机管理端 · 有限任务 · 原始证据留存</p>
<p><a href="/catalog/">打开完整 VPS 筛选网页</a></p>
<p class="note">流程：添加或导入首楼 → 下载真实助手核读工作包 → 上传完成的分析 envelope → 刷新筛选网页。程序不会自动调用 AI/OCR；未确认对象映射的结果留在管理端。</p>
<section><label>本次服务 token <input id="token" type="password" autocomplete="off" placeholder="从启动控制台复制"></label><button id="connect">连接</button><button id="forget">清除 token</button>
<p class="note">token 仅保存在当前标签页的 sessionStorage。重启服务后需重新输入。管理接口不提供联网采集；使用 CLI 显式授权有限采集。</p></section>
<section><label>公开首帖 URL <input id="url" type="url" placeholder="https://www.nodeseek.com/post-…-1"></label><button id="add">加入队列</button><button id="refresh">刷新状态</button><p id="message" role="status"></p>
<div class="table"><table><thead><tr><th>任务</th><th>状态</th><th>来源</th><th>失败原因</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><h2>当前任务：<span id="selected">未选择</span></h2><button id="task">下载分析工作包</button><button id="retry">重试任务</button><button id="cancel">取消任务</button>
<p><label>保存的 HTML <input id="html" type="file" accept=".html,.htm,text/html"></label><button id="ingest">导入首帖</button></p>
<p class="note">浏览器导入只接收 HTML 内容；图片及报告文件请使用 CLI 的 --resources 映射导入。导入的 HTML 不在此页面执行。</p>
<p><label>分析 envelope <input id="analysis" type="file" accept=".json,application/json"></label><button id="submit">校验并导入分析</button></p>
<p class="note">分析工作包须由真实助手核读并生成结果。结构校验不会完成 OCR 或 AI 分析。填好明确的 catalog_mapping 后，校验通过的结果可进入本机筛选网页；页面刷新读取同一份安全快照。</p><pre id="detail"></pre></section>
<section><h2>历史分析（只读，共 <span id="legacy-count">0</span> 条）</h2><button id="legacy-refresh">刷新历史分析</button>
<p class="note">通过 CLI import-legacy 导入已有归档。legacy_imported 保留原分析与历史核读声明，不计入新分析 accepted。迁移没有重新运行 AI，也不会补写原来不存在的逐文件核读日志。原始证据仅存于私有数据目录。</p>
<div class="table"><table><thead><tr><th>帖子</th><th>记录类型</th><th>归档状态</th><th>字段数</th><th>图片数</th><th>缺失资源</th><th>操作</th></tr></thead><tbody id="legacy-rows"></tbody></table></div><pre id="legacy-detail"></pre></section>
<script nonce="{nonce}">{_SCRIPT}</script></html>""".encode("utf-8")


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class ManagementServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address


class IPv6ManagementServer(ManagementServer):
    address_family = socket.AF_INET6


class Handler(BaseHTTPRequestHandler):
    server_version = "VPSPipeline"
    sys_version = ""

    def log_message(self, format, *args):
        # Do not log URLs or headers; they may contain a mistakenly pasted token.
        pass

    def _send(self, status, payload, content_type="application/json; charset=utf-8", headers=None):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", (headers or {}).get("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"))
        for name, value in (headers or {}).items():
            if name != "Content-Security-Policy":
                self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _guard(self):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in self.server.allowed_hosts:
            raise APIError(403, "Host is not an allowed loopback address")
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] != "http://" + hosts[0]):
            raise APIError(403, "Cross-origin requests are not allowed")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise APIError(403, "Cross-site requests are not allowed")
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "%" in parsed.path or "\\" in parsed.path:
            raise APIError(400, "Only exact local API paths without query parameters are accepted")
        return parsed.path

    def _authenticate(self):
        tokens = self.headers.get_all("X-VPS-Token", [])
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0].encode("utf-8"), self.server.session_token.encode("utf-8")):
            raise APIError(401, "A valid X-VPS-Token header is required")

    def _body(self):
        if self.headers.get_all("Transfer-Encoding"):
            raise APIError(400, "Transfer-Encoding is not supported")
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise APIError(415, "Content-Type must be application/json")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
            raise APIError(411, "One valid Content-Length header is required")
        length = int(lengths[0])
        if length > MAX_BODY:
            raise APIError(413, "Request exceeds the 4 MiB limit")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise APIError(400, "Incomplete request body")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate JSON property")
                result[key] = value
            return result
        def constant(_):
            raise ValueError("Non-finite JSON number")
        def floating(value):
            result = float(value)
            if not math.isfinite(result):
                raise ValueError("Non-finite JSON number")
            return result
        try:
            result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise APIError(400, "Request body must contain valid, unambiguous JSON") from None
        if not isinstance(result, dict):
            raise APIError(400, "Request body must be a JSON object")
        return result

    @contextmanager
    def _temporary_directory(self):
        root = self.server.data_root
        temp_root = root / "api-tmp"
        temp_root.mkdir(exist_ok=True)
        if temp_root.is_symlink() or temp_root.resolve().parent != root:
            raise APIError(400, "Unsafe temporary directory")
        with tempfile.TemporaryDirectory(prefix="request-", dir=temp_root) as name:
            yield Path(name)

    def _api(self, method, path):
        parts = path.split("/")
        if path == "/api/legacy":
            if method != "GET":
                raise APIError(405, "Historical imports are read-only in the API; use the local CLI to import")
            return self._send(200, self.server.store.list_legacy())
        if path.startswith("/api/legacy/"):
            if len(parts) != 4 or not re.fullmatch(r"[a-f0-9]{64}", parts[3]):
                raise APIError(404, "Unknown historical record route")
            if method != "GET":
                raise APIError(405, "Historical imports are read-only")
            return self._send(200, self.server.store.get_legacy(parts[3]))
        if path == "/api/jobs":
            if method == "GET":
                return self._send(200, self.server.store.list_jobs())
            if method == "POST":
                data = self._body()
                if set(data) != {"source_url"} or not isinstance(data["source_url"], str):
                    raise APIError(400, "Expected only a source_url string")
                return self._send(201, self.server.store.enqueue(data["source_url"]))
            raise APIError(405, "Method not allowed")
        if len(parts) not in (4, 5) or parts[1:3] != ["api", "jobs"] or not JOB_ID.fullmatch(parts[3]):
            raise APIError(404, "Unknown API route")
        job_id = parts[3]
        if len(parts) == 4:
            if method != "GET":
                raise APIError(405, "Method not allowed")
            return self._send(200, self.server.store.get_job(job_id))
        action = parts[4]
        if action == "task":
            if method != "GET":
                raise APIError(405, "Method not allowed")
            with self._temporary_directory() as directory:
                target = directory / "task.zip"
                self.server.store.export_task(job_id, target)
                if target.stat().st_size > MAX_TASK_BYTES:
                    raise APIError(413, "Task archive exceeds the 256 MiB download limit; use the CLI")
                payload = target.read_bytes()
                # The caller cannot select the download path or filename.
            # Complete cleanup before signaling success to the client. A fully
            # received download must not race cleanup in the request thread.
            return self._send(200, payload, "application/zip", {"Content-Disposition": f'attachment; filename="analysis-task-{job_id}.zip"'})
        if action not in ("submit", "retry", "cancel", "ingest"):
            raise APIError(404, "Unknown API route")
        if method != "POST":
            raise APIError(405, "Method not allowed")
        data = self._body()
        if action == "submit":
            if set(data) != {"envelope"} or not isinstance(data["envelope"], dict):
                raise APIError(400, "Expected only an envelope object")
            result = self.server.store.submit(job_id, data["envelope"])
        elif action == "ingest":
            if set(data) != {"html"} or not isinstance(data["html"], str) or not data["html"]:
                raise APIError(400, "Expected only non-empty HTML content; local paths and resource mappings are not accepted by the API")
            with self._temporary_directory() as directory:
                target = directory / "source.html"
                target.write_text(data["html"], encoding="utf-8")
                result = self.server.store.import_html(job_id, target)
        else:
            if data:
                raise APIError(400, "This action requires an empty JSON object")
            result = getattr(self.server.store, action)(job_id)
        return self._send(200, result)

    def _dispatch(self, method):
        try:
            path = self._guard()
            if path == "/catalog" and method in {"GET", "HEAD"}:
                return self._send(308,b"",headers={"Location":"/catalog/"})
            if path.startswith("/catalog/"):
                if method not in {"GET", "HEAD"}:
                    raise APIError(405,"The public catalog is read-only")
                return self._catalog(path)
            if path.startswith("/api/"):
                self._authenticate()
                return self._api(method, path)
            if path == "/" and method == "GET":
                nonce = secrets.token_urlsafe(20)
                policy = f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
                return self._send(200, _page(nonce), "text/html; charset=utf-8", {"Content-Security-Policy": policy})
            raise APIError(404, "Unknown route")
        except APIError as exc:
            self._send(exc.status, {"error": exc.message})
        except KeyError:
            self._send(404, {"error": "Job not found"})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:
            self._send(500, {"error": "Local operation failed; inspect the job status and local files"})

    def _catalog(self, path):
        from .catalog import BASELINE_JSON, STATIC_ASSETS, MAX_PUBLIC_BYTES, build_snapshot
        from .store import check_plain_path
        from .archive import _read_bytes
        name=path.removeprefix("/catalog/") or "index.html"
        policy="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        headers={"Content-Security-Policy":policy}
        if name in STATIC_ASSETS:
            data=_read_bytes(check_plain_path(self.server.catalog_root/name),MAX_PUBLIC_BYTES)
            return self._send(200,data,STATIC_ASSETS[name],headers)
        if name == "catalog-snapshot.json" or name in set(BASELINE_JSON)|{"catalog-integration.json"}:
            snapshot=build_snapshot(self.server.store,self.server.catalog_root,local_management=True)
            value=snapshot if name=="catalog-snapshot.json" else snapshot["files"].get(name)
            if value is None:
                raise APIError(404,"Unknown public catalog asset")
            return self._send(200,value,headers=headers)
        raise APIError(404,"Unknown public catalog asset")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PATCH(self):
        self._dispatch("PATCH")


def create_server(store, data_root: str | Path, host="127.0.0.1", port=8765, catalog_root=None):
    """Construct the server without starting a thread; useful for local tests."""
    if host not in ("127.0.0.1", "::1"):
        raise ValueError("Management server may only bind to 127.0.0.1 or ::1")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")
    root = Path(data_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    server_class = IPv6ManagementServer if host == "::1" else ManagementServer
    server = server_class((host, port), Handler)
    actual_port = server.server_address[1]
    authority = f"[{host}]:{actual_port}" if ":" in host else f"{host}:{actual_port}"
    server.store = store
    from .catalog import website_root
    server.catalog_root = Path(catalog_root) if catalog_root is not None else website_root()
    server.data_root = root
    server.session_token = secrets.token_urlsafe(32)
    server.allowed_hosts = {authority, f"localhost:{actual_port}"}
    server.management_url = f"http://{authority}/"
    return server


def serve(store, data_root: str | Path, host="127.0.0.1", port=8765):
    server = create_server(store, data_root, host=host, port=port)
    print(f"Local management: {server.management_url}", flush=True)
    print(f"Session token (X-VPS-Token): {server.session_token}", flush=True)
    print(f"Public filters: {server.management_url}catalog/ . Paste the token only into the management page. AI review requires a real assistant handoff.", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
