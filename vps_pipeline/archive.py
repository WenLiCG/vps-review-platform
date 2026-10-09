"""Offline NodeSeek first-post evidence archives; no networking or model calls.

Protocol and observed selector reference: vps-review-download/SKILL.md and
scripts/download.py, read on 2026-10-09. This is an independent implementation.
Only div#0 > ... > article.post-content proves first-post identity. HTML inputs
are untrusted evidence and must never be rendered as active management UI HTML.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import tempfile
from typing import Mapping
from urllib.parse import parse_qs, urljoin, urlsplit
import xml.etree.ElementTree as ET

MAX_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RESOURCES = 256
MAX_MANIFEST_BYTES = 1024 * 1024
REPORT_HOSTS = frozenset({'nodequality.com', 'report.check.place', 'browser.geekbench.com'})
ROLES = {
    'first_post_html': {'text/html'}, 'first_post_text': {'text/plain'},
    'image': {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml'},
    'report_html': {'text/html', 'application/xhtml+xml'}, 'report_text': {'text/plain'},
}
_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
_SKIP = frozenset({'script', 'style', 'template', 'noscript'})
_BLOCK = frozenset('article div p pre li tr h1 h2 h3 h4 section table br hr'.split())
_POST = re.compile(r'/post-([1-9][0-9]*)-1/?\Z')
_SHA = re.compile(r'[a-f0-9]{64}\Z')


class ArchiveError(ValueError):
    """Evidence could not be safely archived or verified."""


class ArchiveConflict(ArchiveError):
    """Existing immutable evidence differs; select a new archive root."""


def normalize_post_url(value: str) -> tuple[str, str]:
    """Validate an explicit first-page URL, returning ID and canonical URL."""
    if not isinstance(value, str) or value != value.strip():
        raise ArchiveError('Expected an explicit NodeSeek first-page URL')
    try:
        parts = urlsplit(value)
        match = _POST.fullmatch(parts.path)
        valid = (parts.scheme in {'http', 'https'}
                 and parts.hostname in {'nodeseek.com', 'www.nodeseek.com'}
                 and not parts.username and not parts.password
                 and parts.port in {None, 80 if parts.scheme == 'http' else 443}
                 and not parts.query and not parts.fragment and match)
    except ValueError as exc:
        raise ArchiveError('Malformed NodeSeek URL') from exc
    if not valid:
        raise ArchiveError('Only explicit NodeSeek post-<positive ID>-1 URLs are accepted')
    post_id = match.group(1)
    return post_id, f'https://www.nodeseek.com/post-{post_id}-1'


def _no_symlinks(path: Path) -> None:
    """Reject symlinks and Windows junction/reparse ancestors, including dangling ones."""
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ArchiveError('Symbolic links and reparse points are not accepted')


def _local_path(value: str | Path) -> Path:
    path = Path(value)
    if '..' in path.parts:
        raise ArchiveError('Parent traversal is not accepted in local paths')
    if any(':' in part for part in path.parts if part != path.anchor):
        raise ArchiveError('Alternate data streams are not accepted in local paths')
    _no_symlinks(path.absolute())
    return path.absolute()


def _read_bytes(path: Path, limit: int = MAX_BYTES) -> bytes:
    _no_symlinks(path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ArchiveError('Evidence must be a regular file')
        if path.stat().st_size > limit:
            raise ArchiveError(f'File exceeds {limit} byte limit')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise ArchiveError(f'Cannot read evidence file: {type(exc).__name__}') from exc
    if len(data) > limit:
        raise ArchiveError(f'File exceeds {limit} byte limit')
    return data


def _decode(data: bytes) -> str:
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ArchiveError('Text evidence must be UTF-8') from exc


class _Node:
    def __init__(self, tag: str = '', attrs: tuple = ()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list[_Node | str] = []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def has_class(self, value: str) -> bool:
        return value in (self.attrs.get('class') or '').split()

    def text(self) -> str:
        if self.tag in _SKIP or self.has_class('xterm-helpers'):
            return ''
        result = ''.join(c.text() if isinstance(c, _Node) else c for c in self.children)
        return '\n' + result + '\n' if self.tag in _BLOCK else result

    def markup(self) -> str:
        inner = ''.join(c.markup() if isinstance(c, _Node) else escape(c) for c in self.children)
        if not self.tag:
            return inner
        attrs = ''.join(f' {key}="{escape(value or "", quote=True)}"' for key, value in self.attrs.items())
        start = f'<{self.tag}{attrs}>'
        return start if self.tag in _VOID else start + inner + f'</{self.tag}>'


class _DOM(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        self.node_count = 0
        try:
            self.feed(source)
            self.close()
        except RecursionError as exc:
            raise ArchiveError('HTML nesting exceeds parser limit') from exc

    def handle_starttag(self, tag, attrs):
        self.node_count += 1
        if len(self.stack) > 128 or self.node_count > 100000:
            raise ArchiveError('HTML complexity limit exceeded')
        if len({k for k, _ in attrs}) != len(attrs):
            raise ArchiveError('Duplicate HTML attributes make evidence ambiguous')
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _first_post(document: str, source_url: str) -> tuple[str, str, str | None, str | None]:
    if re.search(r'<title>\s*(?:Just a moment|Attention Required)|cf-chl-|challenge-platform', document, re.I):
        raise ArchiveError('Access challenge encountered; stop and provide an authorized capture')
    root = _DOM(document).root
    for node in root.walk():
        if ((node.tag == 'link' and 'canonical' in (node.attrs.get('rel') or '').split())
                or (node.tag == 'meta' and node.attrs.get('property') == 'og:url')):
            identity_url = node.attrs.get('href' if node.tag == 'link' else 'content')
            if identity_url and normalize_post_url(urljoin(source_url, identity_url))[1] != source_url:
                raise ArchiveError('Document topic identity differs from source URL')
    markers = [node for node in root.walk() if node.attrs.get('id') == '0']
    if len(markers) != 1 or markers[0].tag != 'div':
        raise ArchiveError('Cannot uniquely locate explicit div#0 first-post marker; no reply fallback')
    marker = markers[0]
    bodies = [node for node in marker.walk() if node.tag == 'article' and node.has_class('post-content')]
    if len(bodies) != 1:
        raise ArchiveError('First-post article.post-content is missing or ambiguous')
    body = bodies[0]
    if any((n.attrs.get('id') or '').isdigit() for n in body.walk()):
        raise ArchiveError('Nested post markers in first-post body are ambiguous')
    text = body.text().strip()
    if not text:
        raise ArchiveError('First post has no readable text')
    title = next((n.text().strip() for n in root.walk() if n.tag == 'h1'), None)
    author = next((n.text().strip() for n in marker.walk() if n.has_class('author-name')), None)
    return body.markup(), text, title, author


def _resolve(value: str, base: str) -> str:
    url = urljoin(base, unescape(value.strip()))
    try:
        parts = urlsplit(url)
        if parts.hostname in {'nodeseek.com', 'www.nodeseek.com'} and parts.path == '/jump':
            url = parse_qs(parts.query).get('to', [url])[0]
    except ValueError:
        return value
    return url


def _public_url_syntax(url: str) -> None:
    """Syntax-only check. No DNS/network access; no URL is ever requested here."""
    try:
        p = urlsplit(url)
        if (p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password
                or p.port not in {None, 80 if p.scheme == 'http' else 443}
                or any(ord(c) < 33 or ord(c) == 127 for c in url) or '\\' in url):
            raise ArchiveError('Only public HTTP(S) resource URL syntax is accepted')
        host = p.hostname.rstrip('.').lower()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.test')) or '.' not in host:
            raise ArchiveError('Local resource hosts are not accepted')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ArchiveError('Private/local resource addresses are not accepted')
    except ValueError as exc:
        raise ArchiveError('Malformed or non-public resource URL') from exc


def _is_report(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
        return host in REPORT_HOSTS
    except ValueError:
        return False


def _discover(markup: str, text: str, base: str) -> tuple[list[str], list[dict]]:
    images, links = [], []
    for node in _DOM(markup).root.walk():
        if node.tag == 'img':
            value = node.attrs.get('data-src') or node.attrs.get('src')
            if value:
                images.append(_resolve(value, base))
        if node.tag in {'a', 'iframe'}:
            value = node.attrs.get('href' if node.tag == 'a' else 'src')
            if value:
                links.append(_resolve(value, base))
    links.extend(re.findall(r'https?://[^\s<>"\x27`\x1b]+', text))
    records = []
    for url in dict.fromkeys(u.rstrip('.,;，。；)）') for u in links):
        try:
            if urlsplit(url).scheme not in {'http', 'https'}:
                continue
        except ValueError:
            continue
        kind = 'report' if _is_report(url) else 'other'
        if kind == 'other' and re.search(r'cart\.php|aff=|affiliate|/order|/buy', url, re.I):
            kind = 'purchase'
        records.append({'url': url, 'kind': kind})
    images = list(dict.fromkeys(images))
    if len(images) + len(records) > MAX_RESOURCES:
        raise ArchiveError('First post exceeds resource/link count limit')
    return images, records


def _image_type(data: bytes, url: str) -> tuple[str, str]:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        kind, suffix = 'png', 'png'
    elif data.startswith(b'\xff\xd8\xff'):
        kind, suffix = 'jpeg', 'jpg'
    elif data[:6] in {b'GIF87a', b'GIF89a'}:
        kind, suffix = 'gif', 'gif'
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        kind, suffix = 'webp', 'webp'
    else:
        if b'<!ENTITY' in data.upper() or b'<!DOCTYPE' in data.upper():
            raise ArchiveError('SVG document types and entities are not accepted')
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            root = None
        if root is None or root.tag.split('}')[-1] != 'svg':
            raise ArchiveError('Image signature is not PNG/JPEG/GIF/WebP/SVG')
        if re.search(r'access denied|hotlink|forbidden|防盗链', ''.join(root.itertext()), re.I):
            raise ArchiveError('SVG contains an access-error/anti-hotlink message')
        kind, suffix = 'svg+xml', 'svg'
    if urlsplit(url).path.lower().endswith('.webp') and kind != 'webp':
        raise ArchiveError('WebP URL returned another image format')
    if 'xviewer' in url.lower():
        raise ArchiveError('xviewer placeholder URL is not evidence')
    return 'image/' + kind, suffix


def _report_type(data: bytes, path: Path) -> tuple[str, str, str]:
    content = _decode(data)
    is_html = path.suffix.lower() in {'.html', '.htm', '.xhtml'} or bool(re.match(r'\s*(?:<!doctype\s+html|<html\b)', content, re.I))
    readable = _DOM(content).root.text().strip() if is_html else content.strip()
    if len(readable) < 100 or re.search(r'^\s*(?:Just a moment|Access Denied)|cf-chl-|challenge-platform', readable, re.I):
        raise ArchiveError('Report is empty, dynamic or blocked; rendered evidence is required')
    return ('report_html', 'text/html', 'html') if is_html else ('report_text', 'text/plain', 'txt')


def _safe_relative(directory: Path, value: str) -> Path:
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
            or any(part in {'', '.', '..'} for part in value.split('/'))):
        raise ArchiveError('Evidence path must be relative without traversal or alternate streams')
    path = directory / value
    _no_symlinks(path)
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ArchiveError('Evidence path escapes the post directory')
    return path


def _file_entry(role: str, data: bytes, mime: str, suffix: str, source_url: str) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    return {'id': f'{role}-{digest[:16]}-{hashlib.sha256(source_url.encode()).hexdigest()[:8]}',
            'role': role, 'path': f'{role}-{digest[:16]}.{suffix}', 'source_url': source_url,
            'sha256': digest, 'bytes': len(data), 'content_type': mime}


def _json_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError('Duplicate JSON manifest keys are not accepted')
        result[key] = value
    return result


def _acquire_import_lock(path: Path):
    """Hold an OS lock until stream close; process termination releases the lock."""
    _no_symlinks(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    stream = os.fdopen(fd, 'r+b')
    try:
        if os.fstat(fd).st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise ArchiveError('Another process holds the archive import lock') from exc
    # Keep the lock file: unlinking it would let another process lock a new inode.
    return stream


def verify_archive(manifest_path: str | Path) -> dict:
    """Verify vps-archive/1 layout, safe paths, MIME, identities and file integrity.

    Returns the parsed manifest, or raises ArchiveError. This does not claim
    visual image review, OCR or accuracy of statements inside the evidence.
    """
    path = _local_path(manifest_path)
    if path.name != 'manifest.json' or path.parent.parent.name != 'assets':
        raise ArchiveError('Expected assets/<post_id>/manifest.json protocol directory')
    try:
        manifest = json.loads(_decode(_read_bytes(path, MAX_MANIFEST_BYTES)), object_pairs_hook=_json_unique)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ArchiveError('Invalid manifest JSON') from exc
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 'vps-archive/1':
        raise ArchiveError('Unsupported archive schema')
    post_id, canonical = normalize_post_url(manifest.get('source_url'))
    if manifest.get('post_id') != post_id or path.parent.name != post_id or manifest['source_url'] != canonical:
        raise ArchiveError('Manifest identity or protocol directory mismatch')
    if manifest.get('status') not in {'ready', 'partial'}:
        raise ArchiveError('Archive requires readable first-post ready/partial status')
    try:
        captured = datetime.fromisoformat(manifest['captured_at'])
        if captured.tzinfo is None:
            raise ValueError('Timezone required')
    except (KeyError, ValueError, TypeError) as exc:
        raise ArchiveError('captured_at must be an ISO timestamp with timezone') from exc
    if any(manifest.get(k) is not None and not isinstance(manifest[k], str) for k in ('title', 'author')):
        raise ArchiveError('Title and author must be strings or null')
    files = manifest.get('files')
    if not isinstance(files, list) or not 2 <= len(files) <= MAX_RESOURCES + 2:
        raise ArchiveError('Invalid evidence file list')
    ids, entries, data_by_role, total = set(), {}, {}, 0
    for item in files:
        if not isinstance(item, dict):
            raise ArchiveError('Invalid evidence file record')
        role, mime = item.get('role'), item.get('content_type')
        if not isinstance(role, str) or role not in ROLES or not isinstance(mime, str) or mime not in ROLES[role]:
            raise ArchiveError('Unsupported evidence role or MIME')
        file_id = item.get('id')
        if not isinstance(file_id, str) or not file_id or len(file_id) > 200 or file_id in ids:
            raise ArchiveError('Missing or duplicate evidence file ID')
        ids.add(file_id)
        digest, length = item.get('sha256'), item.get('bytes')
        if not isinstance(digest, str) or not _SHA.fullmatch(digest) or type(length) is not int or not 0 < length <= MAX_BYTES:
            raise ArchiveError('Invalid evidence digest or byte length')
        source = item.get('source_url')
        if not isinstance(source, str):
            raise ArchiveError('Evidence source URL is missing')
        if role.startswith('first_post_'):
            if source != canonical or role in data_by_role:
                raise ArchiveError('Missing/duplicate first-post identity')
        else:
            _public_url_syntax(source)
            if role.startswith('report_') and not _is_report(source):
                raise ArchiveError('Report host is not allowed')
        file_path = _safe_relative(path.parent, item.get('path'))
        contents = _read_bytes(file_path)
        if len(contents) != length or hashlib.sha256(contents).hexdigest() != digest:
            raise ArchiveError('Archive SHA256/byte integrity failure')
        total += length
        if total > MAX_TOTAL_BYTES:
            raise ArchiveError('Archive exceeds total evidence size limit')
        if role == 'image':
            if _image_type(contents, source)[0] != mime:
                raise ArchiveError('Image MIME differs from its signature')
        else:
            decoded = _decode(contents)
            if not decoded.strip():
                raise ArchiveError('Empty text evidence')
            if role == 'report_text' and re.match(r'\s*(?:<!doctype\s+html|<html\b)', decoded, re.I):
                raise ArchiveError('HTML cannot claim report_text MIME')
            if role.startswith('report_'):
                expected_role = _report_type(contents, file_path)[0]
                if expected_role != role:
                    raise ArchiveError('Report role does not match its content')
        if item['path'] in entries and entries[item['path']] != (digest, role):
            raise ArchiveError('Conflicting records for one evidence path')
        entries[item['path']] = (digest, role)
        if role.startswith('first_post_'):
            data_by_role[role] = _decode(contents)
    if set(data_by_role) != {'first_post_html', 'first_post_text'}:
        raise ArchiveError('Both first-post HTML and text are required')
    html_root = _DOM(data_by_role['first_post_html']).root
    body_nodes = [n for n in html_root.children if isinstance(n, _Node)]
    if (len(body_nodes) != 1 or body_nodes[0].tag != 'article' or not body_nodes[0].has_class('post-content')
            or any(isinstance(n, str) and n.strip() for n in html_root.children)
            or any(n.tag in {'html', 'body'} or (n.attrs.get('id') or '').isdigit() for n in html_root.walk())):
        raise ArchiveError('first_post_html must contain only the original article fragment')
    if html_root.text().strip() != data_by_role['first_post_text'].strip():
        raise ArchiveError('First-post HTML and text evidence disagree')
    images, discovered_links = _discover(data_by_role['first_post_html'], data_by_role['first_post_text'], canonical)
    links = manifest.get('links')
    if not isinstance(links, list) or links != discovered_links:
        raise ArchiveError('Manifest links do not match first-post links')
    expected = {(u, 'image') for u in images} | {(x['url'], 'report') for x in links if x['kind'] == 'report' and x['url'] not in images}
    observed = set()
    for item in files:
        if not item['role'].startswith('first_post_'):
            key = (item['source_url'], 'image' if item['role'] == 'image' else 'report')
            if key not in expected or key in observed:
                raise ArchiveError('Resource was not uniquely discovered in the first post')
            observed.add(key)
    failures = manifest.get('failures')
    if not isinstance(failures, list) or len(failures) > MAX_RESOURCES:
        raise ArchiveError('Invalid resource failures list')
    failed_urls = set()
    for failure in failures:
        if (not isinstance(failure, dict) or not isinstance(failure.get('url'), str)
                or not isinstance(failure.get('reason'), str) or not failure['reason'].strip()
                or failure['url'] in failed_urls or failure['url'] not in {u for u, _ in expected - observed}):
            raise ArchiveError('Failure does not identify a missing discovered resource')
        failed_urls.add(failure['url'])
    if failed_urls != {u for u, _ in expected - observed}:
        raise ArchiveError('Missing resources must have explicit failure reasons')
    if manifest['status'] != ('partial' if failures else 'ready'):
        raise ArchiveError('Status does not match resource failures')
    return manifest


def archive_from_html(html_path: str | Path, source_url: str,
                      destination_root: str | Path,
                      resources: Mapping[str, str | Path] | None = None) -> Path:
    """Import a local full-page capture without saving replies or requesting URLs.

    Resources map discovered URLs to files within html_path.parent. Extra map
    entries are ignored and never read. Missing/invalid resources produce partial
    archives. All completed snapshot bytes, including the manifest, are immutable.
    Missing assets can be supplied in a new snapshot root; identical repeat
    imports are idempotent. An OS lock is released automatically on process exit.
    """
    post_id, canonical = normalize_post_url(source_url)
    source_path = _local_path(html_path)
    document_bytes = _read_bytes(source_path)
    markup, body_text, title, author = _first_post(_decode(document_bytes), canonical)
    images, links = _discover(markup, body_text, canonical)
    if resources is not None and not isinstance(resources, Mapping):
        raise ArchiveError('resources must map URLs to local file paths')
    resources = resources or {}
    output = _local_path(destination_root)
    directory = output / 'assets' / post_id
    _no_symlinks(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'manifest.json'
    _no_symlinks(target)
    lock_stream = _acquire_import_lock(directory / '.import.lock')
    try:
        existing = verify_archive(target) if target.exists() else None
        manifest = existing or {
            'schema_version': 'vps-archive/1', 'post_id': post_id, 'source_url': canonical,
            'title': title, 'author': author, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'capture_method': 'saved_html_first_post_extraction',
            'capture_note': 'First-post fragment reconstructed from supplied HTML; full page not retained.',
            'capture_metadata': {'selector': 'div#0 article.post-content', 'source_document_stored': False,
                                 'input_html_sha256': hashlib.sha256(document_bytes).hexdigest(),
                                 'source_document_bytes': len(document_bytes), 'visual_review': 'not_performed'},
            'status': 'partial', 'files': [], 'links': links, 'failures': [],
        }
        pending: list[tuple[dict, bytes]] = []
        total_bytes = sum(f['bytes'] for f in manifest['files'])
        for role, value, mime, suffix in [('first_post_html', markup, 'text/html', 'html'),
                                          ('first_post_text', body_text, 'text/plain', 'txt')]:
            data = value.encode('utf-8')
            item = _file_entry(role, data, mime, suffix, canonical)
            prior = next((x for x in manifest['files'] if x['role'] == role), None)
            if prior and prior['sha256'] != item['sha256']:
                raise ArchiveConflict('First-post evidence changed; use a new archive root')
            if not prior:
                total_bytes += len(data)
                if total_bytes > MAX_TOTAL_BYTES:
                    raise ArchiveError('Archive exceeds total evidence size limit')
                pending.append((item, data))
        jobs = [(u, 'image') for u in images] + [(x['url'], 'report') for x in links if x['kind'] == 'report' and x['url'] not in images]
        failures = []
        for url, kind in jobs:
            previous = next((f for f in manifest['files'] if f['source_url'] == url and not f['role'].startswith('first_post_')), None)
            if previous and url not in resources:
                continue
            try:
                _public_url_syntax(url)
                if url not in resources:
                    raise ArchiveError('Resource not supplied; offline import performs no network requests')
                raw_path = Path(resources[url])
                if '..' in raw_path.parts:
                    raise ArchiveError('Resource path traversal is not accepted')
                resource_path = _local_path(raw_path if raw_path.is_absolute() else source_path.parent / raw_path)
                if not resource_path.resolve().is_relative_to(source_path.parent.resolve()):
                    raise ArchiveError('Resource must remain inside the HTML import directory')
                # Bound each read by the still-available archive budget before
                # allocating or retaining its bytes. Each source reference
                # counts, even when content-addressed files share a disk path,
                # matching verify_archive's accounting. Existing resources are
                # already counted, so allow their bytes during reverification.
                remaining = MAX_TOTAL_BYTES - total_bytes + (previous['bytes'] if previous else 0)
                resource_limit = min(MAX_BYTES, remaining)
                try:
                    data = _read_bytes(resource_path, resource_limit)
                except ArchiveError as exc:
                    if resource_limit < MAX_BYTES and str(exc) == f'File exceeds {resource_limit} byte limit':
                        raise ArchiveError('Resource exceeds remaining archive total evidence size limit') from exc
                    raise
                if not data:
                    raise ArchiveError('Resource is empty')
                if kind == 'image':
                    mime, suffix = _image_type(data, url)
                    role = 'image'
                else:
                    role, mime, suffix = _report_type(data, resource_path)
                item = _file_entry(role, data, mime, suffix, url)
                if previous:
                    if previous['sha256'] != item['sha256'] or previous['role'] != role:
                        raise ArchiveConflict('Saved resource differs; use a new archive root')
                else:
                    total_bytes += len(data)
                    pending.append((item, data))
            except ArchiveConflict:
                raise
            except (ArchiveError, OSError, TypeError, ValueError) as exc:
                if previous:
                    raise ArchiveConflict('Replacement resource is invalid; existing evidence retained') from exc
                # OSError messages may contain absolute source paths. Failures
                # are public evidence metadata, so retain only a stable class
                # and errno for operating-system errors.
                failure_reason = (f'{type(exc).__name__} (errno={exc.errno})'
                                  if isinstance(exc, OSError) else str(exc))
                failures.append({'url': url, 'reason': failure_reason})
        if sum(f['bytes'] for f in manifest['files']) + sum(len(data) for _, data in pending) > MAX_TOTAL_BYTES:
            raise ArchiveError('Archive exceeds total evidence size limit')
        if existing:
            if not pending and failures == manifest['failures']:
                return target
            raise ArchiveConflict('Archive snapshot is immutable; use a new root')
        for item, data in pending:
            asset_path = _safe_relative(directory, item['path'])
            if asset_path.exists():
                if _read_bytes(asset_path) != data:
                    raise ArchiveConflict('Existing hashed evidence file differs; refusing overwrite')
            else:
                try:
                    with asset_path.open('xb') as stream:
                        stream.write(data)
                except FileExistsError as exc:
                    raise ArchiveConflict('Evidence file appeared during import; retry verification') from exc
            manifest['files'].append(item)
        manifest['failures'] = failures
        manifest['status'] = 'partial' if failures else 'ready'
        payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if len(payload) > MAX_MANIFEST_BYTES:
            raise ArchiveError('Manifest exceeds size limit')
        fd, temporary_name = tempfile.mkstemp(prefix='.manifest-', suffix='.tmp', dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _no_symlinks(target)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        verify_archive(target)
        return target
    finally:
        lock_stream.close()
