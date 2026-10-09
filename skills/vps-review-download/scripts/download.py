#!/usr/bin/env python3
"""Archive NodeSeek first posts and their evidence. Python 3.10+, no model calls."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

MAX_BYTES = 20 * 1024 * 1024
VOID = set("area base br col embed hr img input link meta param source track wbr".split())
SKIP = {"script", "style", "template", "noscript"}
BLOCK = set("article div p pre li tr h1 h2 h3 h4 section table br hr".split())
# ponytail: auto-download only these common report hosts; extend on an observed new source.
REPORT_HOSTS = {"nodequality.com", "report.check.place", "browser.geekbench.com"}


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def all(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.all()

    def has_class(self, name):
        return name in (self.attrs.get("class") or "").split()

    def text(self):
        if self.tag in SKIP or self.has_class("xterm-helpers"):
            return ""
        value = "".join(c.text() if isinstance(c, Node) else c for c in self.children)
        return "\n" + value + "\n" if self.tag in BLOCK else value

    def markup(self):
        if not self.tag:
            return "".join(c.markup() if isinstance(c, Node) else html.escape(c) for c in self.children)
        attrs = "".join(f' {k}="{html.escape(v or "", quote=True)}"' for k, v in self.attrs.items())
        start = f"<{self.tag}{attrs}>"
        if self.tag in VOID:
            return start
        return start + "".join(c.markup() if isinstance(c, Node) else html.escape(c) for c in self.children) + f"</{self.tag}>"


class Parser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def normalize_post(url):
    parts = urlsplit(url.strip())
    match = re.fullmatch(r"/post-([1-9]\d*)-\d+/?", parts.path)
    if parts.scheme not in {"http", "https"} or parts.hostname not in {"nodeseek.com", "www.nodeseek.com"} or parts.username or parts.password or parts.port not in {None, 80, 443} or not match:
        raise ValueError(f"Not a NodeSeek post URL: {url}")
    return match[1], f"https://www.nodeseek.com/post-{match[1]}-1"


def resolve_link(value, base):
    url = urljoin(base, html.unescape(value.strip()))
    parts = urlsplit(url)
    if parts.hostname in {"nodeseek.com", "www.nodeseek.com"} and parts.path == "/jump":
        url = parse_qs(parts.query).get("to", [url])[0]
    return url


def first_post(source):
    root = Parser(source).root
    posts = [n for n in root.all() if n.attrs.get("id") == "0"]
    if len(posts) != 1:
        raise ValueError("Cannot uniquely locate original post #0; no reply fallback")
    bodies = [n for n in posts[0].all() if n.tag == "article" and n.has_class("post-content")]
    if len(bodies) != 1:
        raise ValueError("Original post article.post-content missing or ambiguous")
    title = next((n.text().strip() for n in root.all() if n.tag == "h1"), None)
    author = next((n.text().strip() for n in posts[0].all() if n.has_class("author-name")), None)
    return bodies[0].markup(), bodies[0].text().strip(), title, author


def evidence_links(source, text, base):
    root = Parser(source).root
    images, links = [], []
    for node in root.all():
        if node.tag == "img":
            value = node.attrs.get("data-src") or node.attrs.get("src")
            if value:
                images.append(resolve_link(value, base))
        if node.tag in {"a", "iframe"}:
            value = node.attrs.get("href" if node.tag == "a" else "src")
            if value:
                links.append(resolve_link(value, base))
    # ANSI controls often immediately follow a plain URL in benchmark reports.
    links.extend(re.findall(r"https?://[^\s<>\"'`\x1b]+", text))
    records = []
    for url in dict.fromkeys(u.rstrip(".,;，。；)") for u in links):
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            continue
        kind = "report" if parts.hostname and parts.hostname.removeprefix("www.").lower() in REPORT_HOSTS else "other"
        if kind == "other" and re.search(r"(?:cart\.php|aff=|affiliate|/order|/buy)", url, re.I):
            kind = "purchase"
        records.append({"url": url, "kind": kind})
    return list(dict.fromkeys(images)), records


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ValueError("Only public HTTP(S) URLs without credentials are downloadable")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Local/private network URL is not downloadable")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        if "xviewer" in newurl.lower():
            raise ValueError("Image redirected to xviewer placeholder")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(self, delay=2):
        self.delay, self.last = max(1, delay), 0
        self.opener = build_opener(SafeRedirect())

    def get(self, url, referer):
        public_url(url)
        for attempt in range(3):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                req = Request(url, headers={"User-Agent": "VPSReviewArchive/1.0", "Referer": referer, "Accept-Encoding": "identity"})
                with self.opener.open(req, timeout=30) as response:
                    data = response.read(MAX_BYTES + 1)
                    if len(data) > MAX_BYTES:
                        raise ValueError("Response exceeds 20 MiB limit")
                    return data, response.headers.get_content_type(), response.url
            except HTTPError as error:
                error.close()
                if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
                retry_after = error.headers.get("Retry-After", "")
                time.sleep(min(30, int(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)))
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))


def image_type(data, declared, url):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        kind = "jpeg"
    elif data[:6] in {b"GIF87a", b"GIF89a"}:
        kind = "gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = "webp"
    else:
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            root = None
        if root is None or root.tag.split("}")[-1] != "svg":
            raise ValueError("Image bytes are not PNG/JPEG/GIF/WebP/SVG (possibly error HTML)")
        if re.search(r"access denied|hotlink|forbidden|防盗链", "".join(root.itertext()), re.I):
            raise ValueError("SVG contains an access-error/anti-hotlink message")
        kind = "svg+xml"
    mime = "image/" + kind
    if declared.lower().split(";")[0] not in {mime, "application/octet-stream", "image/jpg" if kind == "jpeg" else mime}:
        raise ValueError(f"Image MIME/signature mismatch: {declared} vs {mime}")
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix == ".webp" and kind != "webp":
        raise ValueError("WebP URL returned another image format; possible anti-hotlink placeholder")
    return mime, "svg" if kind == "svg+xml" else "jpg" if kind == "jpeg" else kind


def safe_local(base, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("Local paths must be relative and cannot contain '..', backslash or ':'")
    result = (base / path).resolve()
    if not result.is_relative_to(base.resolve()):
        raise ValueError("Local path escapes its source directory")
    return result


def add_file(manifest, directory, role, data, mime, suffix, url):
    digest = hashlib.sha256(data).hexdigest()
    path = role + "-" + digest[:16] + "." + suffix
    file_id = role + "-" + digest[:16] + "-" + hashlib.sha256(url.encode()).hexdigest()[:8]
    target = safe_local(directory, path)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Existing file differs; refusing overwrite: {target}")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    if not any(f["id"] == file_id and f["source_url"] == url for f in manifest["files"]):
        manifest["files"].append({"id": file_id, "role": role, "path": path, "source_url": url, "sha256": digest, "bytes": len(data), "content_type": mime})


def verify_existing(manifest, directory):
    if manifest.get("schema_version") != "vps-archive/1":
        raise ValueError("Unsupported existing manifest")
    for item in manifest["files"]:
        data = safe_local(directory, item["path"]).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Archive integrity failure: {item['path']}; use another output directory")


def archive(url, output, fetcher, retry=False, capture_path=None):
    post_id, url = normalize_post(url)
    directory = (output / "assets" / post_id).resolve()
    if not directory.is_relative_to(output.resolve()):
        raise ValueError("Archive directory escapes output directory")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "manifest.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8-sig")) if capture_path else None
    if capture and normalize_post(capture["source_url"])[1] != url:
        raise ValueError("Capture source URL does not match the selected post")
    if target.exists():
        manifest = json.loads(target.read_text(encoding="utf-8"))
        verify_existing(manifest, directory)
        if manifest.get("post_id") != post_id or manifest.get("source_url") != url:
            raise ValueError("Existing archive identity mismatch")
        if not retry and not capture:
            return manifest
    else:
        manifest = {"schema_version": "vps-archive/1", "post_id": post_id, "source_url": url, "title": None, "author": None, "captured_at": datetime.now(timezone.utc).isoformat(), "capture_method": "browser_import" if capture else "http", "status": "error", "files": [], "links": [], "failures": []}
    previous_failures = {f["url"]: f["reason"] for f in manifest["failures"]}
    manifest["failures"] = []
    try:
        saved_html = next((f for f in manifest["files"] if f["role"] == "first_post_html"), None)
        if saved_html:
            source = safe_local(directory, saved_html["path"]).read_text(encoding="utf-8")
            saved_text = next((f for f in manifest["files"] if f["role"] == "first_post_text"), None)
            text = safe_local(directory, saved_text["path"]).read_text(encoding="utf-8") if saved_text else Parser(source).root.text().strip()
        elif capture:
            source = capture.get("first_post_html") or "<article>" + html.escape(capture.get("first_post_text", "")) + "</article>"
            text = capture.get("first_post_text") or Parser(source).root.text().strip()
            manifest["title"], manifest["author"] = capture.get("title"), capture.get("author")
        else:
            data, mime, _ = fetcher.get(url, url)
            if mime not in {"text/html", "application/xhtml+xml"}:
                raise ValueError("Post response is not HTML")
            document = data.decode("utf-8-sig")
            if re.search(r"<title>\s*(?:Just a moment|Attention Required)|cf-chl-|challenge-platform", document, re.I):
                raise ValueError("Blocked by CAPTCHA/security challenge")
            source, text, manifest["title"], manifest["author"] = first_post(document)
        if not text.strip():
            raise ValueError("No readable first-post text; browser capture is required")
        if not any(f["role"] == "first_post_text" for f in manifest["files"]):
            manifest["captured_at"] = datetime.now(timezone.utc).isoformat()
        if capture:
            manifest["capture_method"] = "browser_import"
            if "capture_note" in capture:
                manifest["capture_note"] = capture["capture_note"]
        else:
            manifest.setdefault("capture_method", "http")
        add_file(manifest, directory, "first_post_html", source.encode(), "text/html", "html", url)
        add_file(manifest, directory, "first_post_text", text.encode(), "text/plain", "txt", url)
        images, manifest["links"] = evidence_links(source, text, url)
        imported = {}
        for role, key in (("image", "images"), ("report", "reports")):
            for entry in (capture or {}).get(key, []):
                asset_url = resolve_link(entry["source_url"], url)
                imported[asset_url] = (role, entry)
                if role == "image" and asset_url not in images:
                    images.append(asset_url)
                elif role == "report" and not any(l["url"] == asset_url for l in manifest["links"]):
                    manifest["links"].append({"url": asset_url, "kind": "report"})
        jobs = [(u, "image") for u in images] + [(l["url"], "report") for l in manifest["links"] if l["kind"] == "report" and l["url"] not in images]
        for asset_url, role in jobs:
            if any(f["source_url"] == asset_url and f["role"] in {"image", "report_text", "report_html"} for f in manifest["files"]) and asset_url not in previous_failures:
                continue
            try:
                if asset_url in imported:
                    entry = imported[asset_url][1]
                    data = safe_local(capture_path.parent, entry["path"]).read_bytes()
                    if len(data) > MAX_BYTES:
                        raise ValueError("Imported asset exceeds 20 MiB limit")
                    mime = entry.get("content_type", "application/octet-stream")
                    final_url = asset_url
                elif capture:
                    raise ValueError("Asset not included in local capture; capture import performs no network requests")
                else:
                    data, mime, final_url = fetcher.get(asset_url, url)
                if "xviewer" in final_url.lower():
                    raise ValueError("Image redirected to xviewer placeholder")
                if role == "image" or mime.startswith("image/") or urlsplit(asset_url).path.lower().endswith(".svg"):
                    mime, suffix = image_type(data, mime, asset_url)
                    add_file(manifest, directory, "image", data, mime, suffix, asset_url)
                elif mime in {"text/plain", "text/html", "application/xhtml+xml"}:
                    content = data.decode("utf-8-sig")
                    is_html = mime != "text/plain"
                    report_text = Parser(content).root.text().strip() if is_html else content.strip()
                    add_file(manifest, directory, "report_html" if is_html else "report_text", data, mime, "html" if is_html else "txt", asset_url)
                    if len(report_text) < 100 or re.search(r"^\s*(Just a moment|Access Denied)", report_text, re.I):
                        raise ValueError("Report is empty/dynamic/blocked; capture rendered report in browser")
                else:
                    raise ValueError(f"Unsupported report content type: {mime}")
            except (OSError, ValueError, URLError) as error:
                manifest["failures"].append({"url": asset_url, "reason": str(error)})
        manifest["status"] = "partial" if manifest["failures"] else "ready"
    except (OSError, ValueError, URLError) as error:
        reason = str(error)
        manifest["failures"].append({"url": url, "reason": reason})
        readable = any(f["role"] == "first_post_text" for f in manifest["files"])
        manifest["status"] = "partial" if readable else "blocked" if re.search(r"403|429|CAPTCHA|challenge|blocked", reason, re.I) else "error"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--url-file", type=Path, help="UTF-8 file: one URL per line; # comments permitted")
    parser.add_argument("--out", type=Path, required=True, help="Archive root")
    parser.add_argument("--capture", type=Path, help="Import one local browser capture JSON; no network")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--delay", type=float, default=2, help="Minimum request interval in seconds (>=1)")
    args = parser.parse_args()
    urls = args.urls[:]
    if args.url_file:
        urls.extend(s.strip() for s in args.url_file.read_text(encoding="utf-8-sig").splitlines() if s.strip() and not s.lstrip().startswith("#"))
    if args.capture:
        if urls:
            parser.error("--capture supplies its own source_url; do not also provide URLs")
        urls = [json.loads(args.capture.read_text(encoding="utf-8-sig"))["source_url"]]
    if not urls:
        parser.error("Provide post URLs, --url-file, or --capture")
    try:
        urls = list(dict.fromkeys(normalize_post(u)[1] for u in urls))
    except ValueError as error:
        parser.error(str(error))
    fetcher, failed = Fetcher(args.delay), False
    for url in urls:
        try:
            manifest = archive(url, args.out, fetcher, args.retry_failed, args.capture)
            result = {"post_id": manifest["post_id"], "status": manifest["status"], "files": len(manifest["files"]), "failures": manifest["failures"]}
            failed |= manifest["status"] != "ready"
        except (OSError, ValueError, KeyError) as error:
            result, failed = {"url": url, "status": "error", "reason": str(error)}, True
        print(json.dumps(result, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
