"""Loopback-only interface tests; no public internet or real collector is used."""

from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from vps_pipeline.cli import _read_json, build_parser, main
from vps_pipeline.server import MAX_BODY, create_server


class FakeStore:
    def __init__(self):
        self.jobs = {"job1": {"id": "job1", "status": "pending_analysis", "source_url": "https://www.nodeseek.com/post-123-1"}}
        self.calls = []

    def list_jobs(self):
        return list(self.jobs.values())

    def get_job(self, job_id):
        return self.jobs[job_id]

    def enqueue(self, url):
        if url != "https://www.nodeseek.com/post-123-1":
            raise ValueError("URL is not allowed")
        self.calls.append(("enqueue", url))
        return self.jobs["job1"]

    def import_html(self, job_id, path, resources=None):
        result = self.get_job(job_id)
        self.calls.append(("ingest", Path(path), Path(path).read_text(encoding="utf-8"), resources))
        return result

    def export_task(self, job_id, path):
        self.get_job(job_id)
        self.calls.append(("task", Path(path)))
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("review.txt", "Real assistant review required")
        return {"path": str(path)}

    def submit(self, job_id, envelope):
        self.calls.append(("submit", envelope))
        return self.get_job(job_id)

    def cancel(self, job_id):
        self.calls.append(("cancel", job_id))
        return self.get_job(job_id)

    def retry(self, job_id):
        self.calls.append(("retry", job_id))
        return self.get_job(job_id)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp.name).resolve()
        self.store = FakeStore()
        self.server = create_server(self.store, self.data_root, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method="GET", path="/api/jobs", data=None, headers=None, authenticate=True, raw=None):
        request_headers = {}
        if authenticate:
            request_headers["X-VPS-Token"] = self.server.session_token
        if data is not None:
            raw = json.dumps(data).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        client = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        try:
            client.request(method, path, body=raw, headers=request_headers)
            response = client.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            client.close()

    def test_loopback_only_and_random_session_token(self):
        for host in ("0.0.0.0", "::", "localhost", "example.com"):
            with self.assertRaises(ValueError):
                create_server(self.store, self.data_root, host=host, port=0)
        other = create_server(self.store, self.data_root, port=0)
        try:
            self.assertNotEqual(other.session_token, self.server.session_token)
            self.assertGreaterEqual(len(other.session_token), 40)
        finally:
            other.server_close()

    def test_api_requires_token_in_header(self):
        self.assertEqual(self.request(authenticate=False)[0], 401)
        self.assertEqual(self.request(headers={"X-VPS-Token": "incorrect"})[0], 401)
        self.assertEqual(self.request(path="/api/jobs?token=" + self.server.session_token, authenticate=False)[0], 400)

    def test_management_page_contains_no_token_or_evidence(self):
        status, headers, body = self.request(path="/", authenticate=False)
        self.assertEqual(status, 200)
        self.assertNotIn(self.server.session_token.encode(), body)
        self.assertIn(b"sessionStorage", body)
        self.assertIn(b"textContent", body)
        self.assertNotIn(b"innerHTML", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("script-src 'nonce-", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_host_rebinding_and_cross_origin_are_rejected_even_with_token(self):
        self.assertEqual(self.request(headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request(headers={"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.request(headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request(headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request(headers={"Origin": self.server.management_url.rstrip("/")})[0], 200)
        self.assertEqual(self.request(headers={"Origin": "http://localhost:" + str(self.server.server_address[1])})[0], 403)

    def test_duplicate_host_and_token_headers_are_rejected(self):
        port = self.server.server_address[1]
        for extra_name, extra_value, expected in (("Host", f"127.0.0.1:{port}", 403), ("X-VPS-Token", self.server.session_token, 401)):
            client = HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                client.putrequest("GET", "/api/jobs")
                client.putheader("X-VPS-Token", self.server.session_token)
                client.putheader(extra_name, extra_value)
                client.endheaders()
                response = client.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                client.close()

    def test_job_operations_use_store(self):
        status, _, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)[0]["id"], "job1")
        self.assertEqual(self.request(path="/api/jobs/job1")[0], 200)
        self.assertEqual(self.request(path="/api/jobs/missing")[0], 404)
        url = "https://www.nodeseek.com/post-123-1"
        self.assertEqual(self.request("POST", data={"source_url": url})[0], 201)
        self.assertIn(("enqueue", url), self.store.calls)
        for action in ("cancel", "retry"):
            self.assertEqual(self.request("POST", "/api/jobs/job1/" + action, data={})[0], 200)
            self.assertIn((action, "job1"), self.store.calls)

    def test_content_type_json_and_size_enforced(self):
        self.assertEqual(self.request("POST", raw=b"{}")[0], 415)
        self.assertEqual(self.request("POST", raw=b"x", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", data=[])[0], 400)
        self.assertEqual(self.request("POST", raw=b"{}", headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY + 1)})[0], 413)
        for raw in (b'{"source_url":"a","source_url":"b"}', b'{"source_url":NaN}', b'{"source_url":1e999}'):
            self.assertEqual(self.request("POST", raw=raw, headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", data={}, headers={"Transfer-Encoding": "chunked"})[0], 400)

    def test_routes_cannot_select_local_paths_or_execute_commands(self):
        for path in ("/api/jobs/../../discovery.json", "/api/jobs/%2e%2e/task", "/api/jobs/job1/task?output=C:/secret", "/api/collect", "/api/export-public", "/api/jobs/job1/collect"):
            self.assertIn(self.request(path=path)[0], (400, 404))
        self.assertEqual(self.request("POST", data={"source_url": "file:///C:/secret"})[0], 400)
        self.assertEqual(self.request("POST", data={"source_url": "https://www.nodeseek.com/post-123-1", "command": "echo no"})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs/job1/ingest", data={"html_path": "C:/secret"})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs/job1/ingest", data={"html": "<p>x</p>", "resources": {"https://x": "C:/secret"}})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs/job1/cancel", data={"path": "../"})[0], 400)
        self.assertFalse(self.store.calls)

    def test_ingest_creates_and_removes_owned_temporary_file(self):
        evidence = '<article><script>alert("untrusted")</script>首帖</article>'
        self.assertEqual(self.request("POST", "/api/jobs/job1/ingest", data={"html": evidence})[0], 200)
        _, path, content, resources = self.store.calls[-1]
        self.assertTrue(path.is_relative_to(self.data_root / "api-tmp"))
        self.assertEqual(content, evidence)
        self.assertIsNone(resources)
        self.assertFalse(path.exists())
        self.assertEqual(list((self.data_root / "api-tmp").iterdir()), [])

    def test_task_download_is_a_fixed_attachment(self):
        status, headers, body = self.request(path="/api/jobs/job1/task")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="analysis-task-job1.zip"')
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            self.assertEqual(bundle.read("review.txt"), b"Real assistant review required")
        self.assertFalse(self.store.calls[-1][1].exists())

    def test_submit_requires_envelope_and_preserves_unknown_values(self):
        envelope = {"result": {"unknown": None, "raw_unit": "MB/s"}, "evidence": []}
        self.assertEqual(self.request("POST", "/api/jobs/job1/submit", data={"envelope": envelope})[0], 200)
        self.assertEqual(self.store.calls[-1], ("submit", envelope))
        self.assertEqual(self.request("POST", "/api/jobs/job1/submit", data={"file": "C:/secret"})[0], 400)

    def test_unsupported_methods_and_no_cors(self):
        for method in ("PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            status, headers, _ = self.request(method)
            self.assertEqual(status, 405)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("HEAD", authenticate=False)[0], 401)


class CLITests(unittest.TestCase):
    def test_collect_needs_explicit_network_opt_in_before_store_is_opened(self):
        with redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as raised:
                main(["collect"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("requires --allow-network", output.getvalue())

    def test_collect_is_bounded_and_server_cannot_bind_publicly(self):
        for argv in (["collect", "--allow-network", "--limit", "0"], ["collect", "--allow-network", "--limit", "101"], ["serve", "--host", "0.0.0.0"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(argv)

    def test_resource_paths_are_available_only_in_cli(self):
        args = build_parser().parse_args(["--data", "private", "ingest", "job1", "first.html", "--resources", "mapping.json"])
        self.assertEqual(args.resources, "mapping.json")
        self.assertEqual(args.data, "private")

    def test_json_files_reject_ambiguous_and_non_finite_values(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "input.json"
            for payload in ('{"value":1,"value":2}', '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}'):
                source.write_text(payload, encoding="utf-8")
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    _read_json(str(source))
            source.write_text('{"unknown":null,"zero":0}', encoding="utf-8-sig")
            self.assertEqual(_read_json(str(source)), {"unknown": None, "zero": 0})

    def test_data_directory_symlink_is_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            target = base / "target"
            target.mkdir()
            link = base / "linked-data"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Creating directory symlinks is unavailable on this host")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as output:
                result = main(["--data", str(link), "init"])
            self.assertEqual(result, 2)
            self.assertIn("symlinks", output.getvalue())
            self.assertFalse((target / "pipeline.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
