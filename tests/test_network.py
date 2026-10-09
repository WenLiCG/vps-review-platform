"""Offline network-policy tests. Every DNS/socket operation is replaced locally."""

from email.message import Message
import hashlib
import io
import os
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from vps_pipeline import network


URL = "https://www.nodeseek.com/post-12345-1"
PAGE = b'<html><title>Public review - NodeSeek</title><div class="post-content">Evidence</div></html>'
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]


class FakeResponse:
    def __init__(self, body=PAGE, status=200, headers=None):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        for key, value in (headers or []):
            if key.lower() == "content-type":
                del self.headers["Content-Type"]
            self.headers[key] = value
        self.stream = io.BytesIO(body)
        self.reads = 0

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        self.reads += 1
        return self.stream.read(size)

    def close(self):
        self.stream.close()


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "archive" / "page.html"
        # Test-wide guard: an overlooked transport call must fail, never connect.
        self.raw_socket = patch.object(network.socket, "socket", side_effect=AssertionError("real socket forbidden"))
        self.raw_socket.start()
        self.addCleanup(self.raw_socket.stop)
        self.dns = patch.object(network.socket, "getaddrinfo", return_value=PUBLIC).start()
        self.addCleanup(patch.stopall)

    def fetch(self, response=None, **kwargs):
        connection = MagicMock()
        connection.sock = MagicMock()
        connection.transport_socket = connection.sock
        connection.getresponse.return_value = response or FakeResponse()
        with patch.object(network, "_PinnedHTTPSConnection", return_value=connection) as factory:
            metadata = network.fetch_first_post(URL, self.destination, **kwargs)
        return metadata, connection, factory

    def assert_blocked(self, reason, response=None, **kwargs):
        with self.assertRaises(network.NetworkBlocked) as raised:
            self.fetch(response, **kwargs)
        self.assertEqual(raised.exception.reason, reason)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(Path(self.temp.name).rglob("*.tmp")), [])

    def test_success_fixed_headers_and_evidence_hash(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9999", "ALL_PROXY": "socks5://127.0.0.1:8888"}):
            result, connection, factory = self.fetch()
        self.assertEqual(self.destination.read_bytes(), PAGE)
        self.assertEqual(result["sha256"], hashlib.sha256(PAGE).hexdigest())
        self.assertEqual(result["bytes"], len(PAGE))
        self.assertEqual(result["remote_ip"], "93.184.216.34")
        self.assertEqual(result["scope"], "first_page_html_only")
        self.assertEqual(factory.call_args.args[:2], (socket.AF_INET, "93.184.216.34"))
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ("GET", "/post-12345-1"))
        self.assertNotIn("Cookie", kwargs["headers"])
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_scope_rejected_before_dns(self):
        invalid = [
            "http://www.nodeseek.com/post-12345-1", "https://nodeseek.com/post-12345-1",
            "https://www.nodeseek.com:443/post-12345-1", URL + "?x=1", URL + "#x",
            "https://name:secret@www.nodeseek.com/post-12345-1", URL + "/",
            "https://www.nodeseek.com/post-12345-2", "https://127.0.0.1/post-12345-1",
            "https://www.nodeseek.com.evil.example/post-12345-1",
            "https://www.nodeseek.com./post-12345-1", "https://WWW.NODESEEK.COM/post-12345-1",
            "https://www.nodeseek.com/%70ost-12345-1", URL + "\n",
            "https://www.nodeseek.com\\@127.0.0.1/post-12345-1",
            "https://www.nodeseek.com/post-１２３-1", "file:///etc/passwd", None,
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(network.NetworkBlocked) as raised:
                network.fetch_first_post(url, self.destination)
            self.assertEqual(raised.exception.reason, "url_out_of_scope")
        self.dns.assert_not_called()

    def test_mixed_private_dns_answer_blocks_all_connection_attempts(self):
        for address, family in [
            ("127.0.0.1", socket.AF_INET), ("10.2.3.4", socket.AF_INET),
            ("169.254.169.254", socket.AF_INET), ("192.168.1.5", socket.AF_INET),
            ("224.0.0.1", socket.AF_INET), ("0.0.0.0", socket.AF_INET),
            ("::1", socket.AF_INET6), ("fe80::1", socket.AF_INET6),
            ("ff02::1", socket.AF_INET6), ("::ffff:127.0.0.1", socket.AF_INET6),
        ]:
            with self.subTest(address=address):
                self.dns.return_value = PUBLIC + [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]
                with patch.object(network, "_PinnedHTTPSConnection") as factory:
                    with self.assertRaises(network.NetworkBlocked) as raised:
                        network.fetch_first_post(URL, self.destination)
                    self.assertEqual(raised.exception.reason, "dns_non_public")
                    factory.assert_not_called()

    def test_redirect_never_followed_even_to_same_host(self):
        for status in (301, 302, 303, 307, 308):
            for location in (URL, "http://127.0.0.1/secret", "https://www.nodeseek.com/post-999-1"):
                with self.subTest(status=status, location=location):
                    response = FakeResponse(status=status, headers=[("Location", location)])
                    self.assert_blocked("redirect_blocked", response)
                    self.assertEqual(response.reads, 0)

    def test_auth_rate_limit_and_forbidden_stop_without_body_read(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                response = FakeResponse(status=status)
                self.assert_blocked(f"http_{status}", response)
                self.assertEqual(response.reads, 0)

    def test_challenge_and_login_pages_blocked(self):
        for body, reason in [
            (b"<title>Just a moment...</title>", "challenge_page"),
            (b'<script src="/cdn-cgi/challenge-platform/a.js"></script>', "challenge_page"),
            (b'<form id="challenge-form">verify</form>', "challenge_page"),
            (b"<title>Login - NodeSeek</title>", "login_page"),
            ('<title>用户登录 - NodeSeek</title>'.encode(), "login_page"),
            (b'<form><input type="password"></form>', "login_page"),
        ]:
            with self.subTest(body=body):
                self.assert_blocked(reason, FakeResponse(body))

    def test_503_challenge_is_access_block_not_transient_retry(self):
        self.assert_blocked("challenge_page", FakeResponse(b"<title>Just a moment...</title>", status=503))

    def test_normal_login_navigation_not_mistaken_for_gate(self):
        body = PAGE + b'<a href="/login">Login</a><form><input type="password"></form>'
        result, _, _ = self.fetch(FakeResponse(body))
        self.assertEqual(result["bytes"], len(body))

    def test_declared_body_cap_rejected_before_read(self):
        response = FakeResponse(headers=[("Content-Length", "101")])
        self.assert_blocked("body_too_large", response, max_bytes=100)
        self.assertEqual(response.reads, 0)

    def test_streamed_body_cap_rejected_and_not_published(self):
        response = FakeResponse(b"A" * 101)
        self.assert_blocked("body_too_large", response, max_bytes=100)
        self.assertEqual(response.reads, 1)
        self.assertTrue(response.stream.closed)

    def test_exact_cap_is_allowed(self):
        result, _, _ = self.fetch(FakeResponse(PAGE), max_bytes=len(PAGE))
        self.assertEqual(result["bytes"], len(PAGE))

    def test_ambiguous_or_compressed_responses_blocked(self):
        for headers, reason in [
            ([("Content-Length", "x")], "invalid_content_length"),
            ([("Content-Length", "10"), ("Content-Length", "10")], "invalid_content_length"),
            ([("Transfer-Encoding", "chunked"), ("Content-Length", "10")], "ambiguous_body_length"),
            ([("Transfer-Encoding", "gzip")], "unsupported_transfer_encoding"),
            ([("Content-Encoding", "gzip")], "encoded_body_blocked"),
            ([("Content-Type", "application/octet-stream")], "unexpected_content_type"),
        ]:
            with self.subTest(headers=headers):
                self.assert_blocked(reason, FakeResponse(headers=headers))

    def test_truncated_response_is_not_saved(self):
        with self.assertRaises(network.NetworkFailure) as raised:
            self.fetch(FakeResponse(PAGE, headers=[("Content-Length", str(len(PAGE) + 1))]))
        self.assertEqual(raised.exception.reason, "incomplete_body")
        self.assertFalse(self.destination.exists())

    def test_transport_timeout_no_retry_and_no_file(self):
        connection = MagicMock()
        connection.getresponse.side_effect = socket.timeout("fixture")
        with patch.object(network, "_PinnedHTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(network.NetworkFailure) as raised:
                network.fetch_first_post(URL, self.destination)
        self.assertEqual(raised.exception.reason, "timeout")
        factory.assert_called_once()
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        self.assertFalse(self.destination.exists())

    def test_dns_timeout_bounded_without_http_connection(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def delayed(*args, **kwargs):
            release.wait(1)
            return PUBLIC

        self.dns.side_effect = delayed
        start = time.monotonic()
        with patch.object(network, "_PinnedHTTPSConnection") as factory:
            with self.assertRaises(network.NetworkFailure) as raised:
                network.fetch_first_post(URL, self.destination, timeout=0.02)
            factory.assert_not_called()
        self.assertEqual(raised.exception.reason, "timeout")
        self.assertLess(time.monotonic() - start, 0.5)
        release.set()

    def test_watchdog_closes_response_after_connection_sock_is_cleared(self):
        stopped = threading.Event()
        connection = MagicMock()
        connection.sock = None  # HTTPConnection may clear this on getresponse.
        connection.transport_socket.shutdown.side_effect = lambda _: stopped.set()
        response = FakeResponse()

        def blocked_read(_size):
            if not stopped.wait(0.5):
                self.fail("deadline watchdog did not stop the response")
            raise OSError("fixture closed")

        response.read1 = blocked_read
        connection.getresponse.return_value = response
        with patch.object(network, "_PinnedHTTPSConnection", return_value=connection):
            with self.assertRaises(network.NetworkFailure) as raised:
                network.fetch_first_post(URL, self.destination, timeout=0.03)
        self.assertEqual(raised.exception.reason, "timeout")
        connection.transport_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        self.assertTrue(response.stream.closed)
        self.assertFalse(self.destination.exists())

    def test_existing_evidence_never_overwritten_and_dns_not_called(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(b"original")
        with self.assertRaises(network.NetworkFailure) as raised:
            network.fetch_first_post(URL, self.destination)
        self.assertEqual(raised.exception.reason, "destination_exists")
        self.assertEqual(self.destination.read_bytes(), b"original")
        self.dns.assert_not_called()

    def test_invalid_budgets_rejected_before_dns(self):
        for kwargs in ({"max_bytes": 0}, {"max_bytes": True}, {"max_bytes": network.HARD_MAX_BYTES + 1},
                       {"timeout": 0}, {"timeout": float("nan")}, {"timeout": 121}, {"timeout": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                network.fetch_first_post(URL, self.destination, **kwargs)
        self.dns.assert_not_called()

    def test_pinned_transport_keeps_original_tls_hostname(self):
        self.raw_socket.stop()
        raw, tls, context = MagicMock(), MagicMock(), MagicMock()
        context.wrap_socket.return_value = tls
        with patch.object(network.socket, "socket", return_value=raw) as factory, \
                patch.object(network.ssl, "create_default_context", return_value=context):
            connection = network._PinnedHTTPSConnection(socket.AF_INET, "93.184.216.34", time.monotonic() + 5)
            connection.connect()
        factory.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        raw.connect.assert_called_once_with(("93.184.216.34", 443))
        context.wrap_socket.assert_called_once_with(raw, server_hostname="www.nodeseek.com", do_handshake_on_connect=False)
        tls.do_handshake.assert_called_once()
        self.assertIs(connection.sock, tls)
        self.assertIs(connection.transport_socket, tls)
        self.dns.assert_not_called()

    def test_ipv6_connection_also_pins_literal(self):
        self.raw_socket.stop()
        raw, context = MagicMock(), MagicMock()
        with patch.object(network.socket, "socket", return_value=raw), \
                patch.object(network.ssl, "create_default_context", return_value=context):
            connection = network._PinnedHTTPSConnection(socket.AF_INET6, "2606:4700:4700::1111", time.monotonic() + 5)
            connection.connect()
        raw.connect.assert_called_once_with(("2606:4700:4700::1111", 443, 0, 0))
        self.dns.assert_not_called()


if __name__ == "__main__":
    unittest.main()
