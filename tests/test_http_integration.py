"""Real Store over loopback HTTP using explicitly synthetic review declarations.

No collector, model, OCR or external connection is used. The accepted record is
test data in a disposable directory; all 61 measurement/plan facts remain unknown.
"""

from http.client import HTTPConnection
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from vps_pipeline.server import create_server
from vps_pipeline.store import Store


class HTTPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.store = Store(self.root)
        self.server = create_server(self.store, self.root, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        original_connect = socket.socket.connect
        def loopback_only(connection, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                raise AssertionError("HTTP integration test attempted an external connection")
            return original_connect(connection, address)
        self.connections = patch.object(socket.socket, "connect", loopback_only)
        self.connections.start()
        self.addCleanup(self.connections.stop)
        self.collector = patch("vps_pipeline.network.fetch_first_post",
                               side_effect=AssertionError("Collector must not run in HTTP integration tests"))
        self.fetch = self.collector.start()
        self.addCleanup(self.collector.stop)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, payload=None):
        headers = {"X-VPS-Token": self.server.session_token,
                   "Origin": self.server.management_url.rstrip("/")}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, dict(response.getheaders()), raw
        finally:
            connection.close()

    def json_request(self, method, path, payload=None, expected=200):
        status, _, raw = self.request(method, path, payload)
        self.assertEqual(status, expected, raw.decode("utf-8", errors="replace"))
        return json.loads(raw)

    def test_queue_ingest_package_submit_and_persist_unknown_facts(self):
        url = "https://www.nodeseek.com/post-900001-1"
        job = self.json_request("POST", "/api/jobs", {"source_url": url}, expected=201)
        job_id = job["id"]
        route = "/api/jobs/" + job_id
        self.assertEqual(job["status"], "queued")
        duplicate = self.json_request("POST", "/api/jobs", {"source_url": url}, expected=201)
        self.assertEqual(duplicate["id"], job_id)
        self.assertEqual(len(self.json_request("GET", "/api/jobs")), 1)

        html = (Path(__file__).parent / "fixtures" / "nodeseek_first_post.html").read_text(encoding="utf-8")
        archived = self.json_request("POST", route + "/ingest", {"html": html})
        self.assertEqual(archived["status"], "awaiting_analysis")
        self.assertEqual(len(archived["archive_sha256"]), 64)
        self.assertEqual(list((self.root / "api-tmp").iterdir()), [])

        status, headers, raw = self.request("GET", route + "/task")
        self.assertEqual(status, 200, raw[:1000])
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertEqual(list((self.root / "api-tmp").iterdir()), [])
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            metadata = json.loads(package.read("package.json"))
            envelope = json.loads(package.read("envelope.json"))
            manifest_bytes = package.read(metadata["manifest"])
            manifest = json.loads(manifest_bytes)
            self.assertEqual(metadata["status"], "needs_ai")
            self.assertEqual(metadata["archive_status"], "partial")
            self.assertTrue(manifest["failures"])
            self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), archived["archive_sha256"])
            self.assertEqual(envelope["archive_sha256"], archived["archive_sha256"])
            self.assertIs(envelope["analysis"]["ai_review"]["completed"], False)
            self.assertEqual(len(envelope["analysis"]["facts"]), 61)
            self.assertTrue(all(fact["status"] == "unknown" and fact["value"] is None
                                for fact in envelope["analysis"]["facts"].values()))
            self.assertEqual(envelope["review_log"], [])
            self.assertEqual(envelope["observations"], [])
            for record in manifest["files"]:
                evidence = package.read("assets/900001/" + record["path"])
                self.assertEqual(hashlib.sha256(evidence).hexdigest(), record["sha256"])
                self.assertNotIn(b"REPLY_MUST_NOT_BE_ARCHIVED", evidence)
                self.assertNotIn(b"SIDEBAR_MUST_NOT_BE_ARCHIVED", evidence)

        # The exported draft must be rejected while it still requests real AI
        # review. A failed submit must retain the usable archive and pending state.
        self.json_request("POST", route + "/submit", {"envelope": envelope}, expected=400)
        pending = self.json_request("GET", route)
        self.assertEqual(pending["status"], "awaiting_analysis")
        self.assertTrue(pending["last_error"])

        # Contract exercise only: deliberately label every declaration synthetic,
        # without claiming real review or populating any source facts.
        declaration = "SYNTHETIC HTTP TEST DECLARATION; NO REAL ASSISTANT REVIEW"
        envelope["test_fixture"] = True
        envelope["analysis"]["summary"] = declaration
        envelope["analysis"]["ai_review"] = {
            "completed": True, "agent": declaration,
            "reviewed_files": [record["id"] for record in manifest["files"]],
        }
        envelope["review_log"] = [
            {"file_id": record["id"], "sha256": record["sha256"],
             "reviewer": declaration, "reviewed_at": "2026-10-09T00:00:00+00:00",
             "coverage": "full", "regions": ["Synthetic whole-file test declaration only"],
             "issues": ["No actual review performed: fixture validates the HTTP import contract only."]}
            for record in manifest["files"]
        ]
        accepted = self.json_request("POST", route + "/submit", {"envelope": envelope})
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["version"], 1)
        self.assertIs(accepted["duplicate"], False)
        resubmitted = self.json_request("POST", route + "/submit", {"envelope": envelope})
        self.assertEqual(resubmitted["version"], 1)
        self.assertIs(resubmitted["duplicate"], True)
        final = self.json_request("GET", route)
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["accepted_version"], 1)
        self.assertIsNone(final["last_error"])
        self.assertEqual(final["archive_sha256"], archived["archive_sha256"])
        self.assertIn("review_package_exported", [event["event"] for event in final["events"]])
        self.assertIn("accepted", [event["event"] for event in final["events"]])
        self.assertEqual(Store(self.root).get_job(job_id)["status"], "accepted")

        # Verify the actual persisted result, not only the success response.
        with self.store._db() as db:
            row = db.execute("SELECT normalized,validation,envelope FROM analyses WHERE job_id=?", (job_id,)).fetchone()
        normalized = json.loads(row["normalized"])
        validation = json.loads(row["validation"])
        self.assertEqual(len(normalized["facts"]), 61)
        self.assertTrue(all(fact["value"] is None for fact in normalized["facts"].values()))
        self.assertIs(validation["ai_invoked"], False)
        self.assertIs(validation["review_attestation_verified"], False)
        self.assertEqual(json.loads(row["envelope"]), envelope)
        self.fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
