"""Optional, finite public NodeSeek first-page downloader (Python standard library).

Nothing is fetched on import. No proxy, cookie, credential, browser, retry, or
collector configuration is loaded. URL/DNS checks follow the design of the
reference ``forumcrawl/site_profiles.py``; its controller is never imported.
Only this module's explicit ``fetch_first_post`` call performs network I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import math
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import tempfile
import threading
import time


HOST = "www.nodeseek.com"
HARD_MAX_BYTES = 16 * 1024 * 1024
MAX_TIMEOUT = 120


class NetworkError(Exception):
    """A finite fetch failed. ``reason`` is a stable, credential-free code."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class NetworkBlocked(NetworkError):
    """Access or safety policy blocked the task; do not retry automatically."""


class NetworkFailure(NetworkError):
    """A transport/local-write failure; this module never retries it."""


def _canonical_url(url: str) -> str:
    # Exact syntax intentionally excludes credentials, queries, fragments,
    # ports, alternate hosts, encoded paths, and later pages.
    if (not isinstance(url, str) or len(url) > 2048
            or re.fullmatch(r"https://www\.nodeseek\.com/post-[0-9]+-1", url) is None):
        raise NetworkBlocked("url_out_of_scope")
    return url


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NetworkFailure("timeout")
    return remaining


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or "%" in value:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped is None or (mapped.is_global and not mapped.is_multicast)


def _resolve_public(deadline: float) -> tuple[int, str]:
    """Check every answer, then return one literal address to pin the socket.

    OS DNS cannot be interrupted portably. A daemon resolver thread bounds the
    caller's wait; a timed-out resolver can finish in the background but never
    opens an HTTP connection or starts a retry.
    """
    result: queue.Queue = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put((True, socket.getaddrinfo(
                HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)))
        except Exception as exc:
            result.put((False, exc))

    threading.Thread(target=resolve, name="vps-public-dns", daemon=True).start()
    try:
        ok, answers = result.get(timeout=_remaining(deadline))
    except queue.Empty:
        raise NetworkFailure("timeout") from None
    if not ok:
        raise NetworkFailure("dns_failure") from None
    addresses = set()
    for family, kind, protocol, _name, sockaddr in answers:
        if (family not in (socket.AF_INET, socket.AF_INET6)
                or kind != socket.SOCK_STREAM
                or protocol not in (0, socket.IPPROTO_TCP)
                or not sockaddr or not _public_ip(sockaddr[0])):
            raise NetworkBlocked("dns_non_public")
        address = ipaddress.ip_address(sockaddr[0])
        if (address.version == 4) != (family == socket.AF_INET):
            raise NetworkBlocked("dns_invalid_answer")
        addresses.add((family, address.compressed))
    if not addresses:
        raise NetworkFailure("dns_no_addresses")
    # One attempt only. All DNS results have already passed the safety check.
    return sorted(addresses, key=lambda item: (item[0] != socket.AF_INET, item[1]))[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, family: int, address: str, deadline: float):
        super().__init__(HOST, timeout=_remaining(deadline), context=ssl.create_default_context())
        self.family = family
        self.address = address
        self.deadline = deadline
        # HTTPConnection may clear ``sock`` on a Connection: close response
        # while HTTPResponse still owns its file wrapper. Keep a reference so
        # the deadline watchdog can interrupt that response too.
        self.transport_socket = None

    def connect(self) -> None:
        # Connect directly to a validated literal; never re-resolve HOST.
        raw = socket.socket(self.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.sock = raw
        self.transport_socket = raw
        try:
            raw.settimeout(_remaining(self.deadline))
            target = (self.address, 443) if self.family == socket.AF_INET else (self.address, 443, 0, 0)
            raw.connect(target)
            raw.settimeout(_remaining(self.deadline))
            self.sock = self._context.wrap_socket(raw, server_hostname=HOST, do_handshake_on_connect=False)
            self.transport_socket = self.sock
            self.sock.do_handshake()
        except BaseException:
            if self.transport_socket is not None:
                self.transport_socket.close()
            raw.close()
            self.sock = None
            raise


class _PageSignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title: list[str] = []
        self.password = False
        self.post_content = False
        self.challenge = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "input" and (values.get("type") or "").lower() == "password":
            self.password = True
        classes = (values.get("class") or "").split()
        if "post-content" in classes or "post-list-item" in classes:
            self.post_content = True
        if tag == "script" and "challenge-platform" in (values.get("src") or "").lower():
            self.challenge = True
        if (values.get("id") or "").lower() in {
                "challenge-form", "cf-challenge-running", "cf-chl-widget", "challenge-running"}:
            self.challenge = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title.append(data)


def _check_access_page(body: bytes) -> None:
    parser = _PageSignals()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        raise NetworkBlocked("invalid_html") from None
    title = " ".join("".join(parser.title).split()).lower()
    if parser.challenge or re.search(
            r"just a moment|attention required|access denied|checking your browser|"
            r"verify (?:that )?you are human|ddos.guard|安全验证|访问受限|人机验证", title):
        raise NetworkBlocked("challenge_page")
    if (re.fullmatch(r"(?:login|log in|sign in|登录|用户登录|登入|请先登录)(?:\s*[-|–—].*)?", title)
            or (parser.password and not parser.post_content)):
        raise NetworkBlocked("login_page")


def _publish(body: bytes, destination: Path) -> None:
    # Publish once: never replace an existing archived page, including symlinks.
    if destination.exists() or destination.is_symlink():
        raise NetworkFailure("destination_exists")
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".fetch-", suffix=".tmp", dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    except FileExistsError:
        raise NetworkFailure("destination_exists") from None
    except OSError:
        raise NetworkFailure("output_write_failed") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_first_post(url: str, output_path: str | os.PathLike, *,
                     max_bytes: int = 4 * 1024 * 1024, timeout: float = 20) -> dict:
    """Download one public first-page HTML response, never following redirects.

    The archive adapter must separately identify the first post in this page.
    No image/report resources are fetched. ``max_bytes`` is 1..16 MiB;
    ``timeout`` is the total network budget, greater than zero and at most 120s.
    Policy/access failures raise ``NetworkBlocked``; all other operational
    failures raise ``NetworkFailure``. No failure publishes a partial output.
    """
    url = _canonical_url(url)
    if type(max_bytes) is not int or not 1 <= max_bytes <= HARD_MAX_BYTES:
        raise ValueError("max_bytes must be an integer from 1 to 16777216")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT):
        raise ValueError("timeout must be finite, greater than zero, and at most 120 seconds")
    destination = Path(output_path)
    if destination.exists() or destination.is_symlink():
        raise NetworkFailure("destination_exists")
    deadline = time.monotonic() + timeout
    family, address = _resolve_public(deadline)
    connection = _PinnedHTTPSConnection(family, address, deadline)
    expired = threading.Event()
    response = None

    def expire() -> None:
        expired.set()
        sock = connection.transport_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    # A watchdog also stops slow trickle responses while http.client parses
    # headers/chunks, which a per-read timeout alone would not reliably bound.
    watchdog = threading.Timer(_remaining(deadline), expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.request("GET", url.removeprefix("https://" + HOST), headers={
            "User-Agent": "vps-review-pipeline/1.0 (finite public first-post archive)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = connection.getresponse()
        if expired.is_set():
            raise NetworkFailure("timeout")
        status = response.status
        if status in (401, 403, 429):
            raise NetworkBlocked(f"http_{status}")
        if 300 <= status <= 399:
            raise NetworkBlocked("redirect_blocked")
        # Cloudflare and similar gates may return 503 with a challenge page.
        # Inspect that bounded HTML response for the same access-stop signals.
        if status not in (200, 503):
            raise NetworkFailure(f"http_{status}")
        content_type = response.headers.get_content_type().lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise NetworkBlocked("unexpected_content_type")
        if response.getheader("Content-Encoding", "identity").strip().lower() not in {"", "identity"}:
            raise NetworkBlocked("encoded_body_blocked")
        transfer = response.getheader("Transfer-Encoding", "").strip().lower()
        if transfer not in {"", "chunked"}:
            raise NetworkBlocked("unsupported_transfer_encoding")
        lengths = response.headers.get_all("Content-Length", [])
        expected = None
        if lengths:
            if len(lengths) != 1 or re.fullmatch(r"[0-9]+", lengths[0]) is None or len(lengths[0]) > 20:
                raise NetworkBlocked("invalid_content_length")
            if transfer:
                raise NetworkBlocked("ambiguous_body_length")
            expected = int(lengths[0])
            if expected > max_bytes:
                raise NetworkBlocked("body_too_large")
        chunks: list[bytes] = []
        size = 0
        while True:
            if connection.transport_socket is not None:
                connection.transport_socket.settimeout(_remaining(deadline))
            chunk = response.read1(min(65536, max_bytes - size + 1))
            if expired.is_set():
                raise NetworkFailure("timeout")
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise NetworkBlocked("body_too_large")
            chunks.append(chunk)
        _remaining(deadline)
        if expected is not None and size != expected:
            raise NetworkFailure("incomplete_body")
        if not size:
            raise NetworkBlocked("empty_body")
        body = b"".join(chunks)
        _check_access_page(body)
        if status != 200:
            raise NetworkFailure(f"http_{status}")
    except NetworkError:
        raise
    except (TimeoutError, socket.timeout):
        raise NetworkFailure("timeout") from None
    except ssl.SSLError:
        raise NetworkFailure("timeout" if expired.is_set() else "tls_failure") from None
    except (OSError, http.client.HTTPException):
        raise NetworkFailure("timeout" if expired.is_set() else "transport_failure") from None
    finally:
        watchdog.cancel()
        if response is not None:
            response.close()
        connection.close()
    _publish(body, destination)
    return {
        "url": url, "path": str(destination), "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body), "status": status, "content_type": content_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(), "remote_ip": address,
        "scope": "first_page_html_only",
    }
