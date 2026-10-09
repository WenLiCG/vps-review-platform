"""Offline invariants: first post only, truthful status, safe resume/import."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

import download as d

URL = "https://www.nodeseek.com/post-913633-1"
IMAGE = "https://cdn.example.com/report.png"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6z0AAAAASUVORK5CYII=")
HTML = '''<html><h1>Sample VPS</h1><div id="0"><a class="author-name">Tester</a>
<img src="https://cdn.example.com/avatar.png"><article class="post-content"><p>2 cores, 2 GB</p>
<img src="https://cdn.example.com/report.png"><script>IGNORE THIS SCRIPT</script></article></div>
<div id="1"><article class="post-content">REPLY TRAP<img src="https://cdn.example.com/reply.png"></article></div></html>'''


class FakeFetcher:
    def __init__(self, fail_image=False):
        self.calls = []
        self.fail_image = fail_image

    def get(self, url, referer):
        self.calls.append(url)
        if url == URL:
            return HTML.encode(), "text/html", url
        if url == IMAGE and not self.fail_image:
            return PNG, "image/png", url
        raise HTTPError(url, 403, "Forbidden", {}, None)


class ArchiveTests(unittest.TestCase):
    def test_first_post_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            out, fetcher = Path(temp), FakeFetcher()
            manifest = d.archive(URL.replace("-1", "-4") + "#5", out, fetcher)
            self.assertEqual(manifest["status"], "ready")
            self.assertEqual(fetcher.calls, [URL, IMAGE])
            self.assertEqual(manifest["author"], "Tester")
            text = next(f for f in manifest["files"] if f["role"] == "first_post_text")
            self.assertNotIn("REPLY", (out / "assets/913633" / text["path"]).read_text())
            self.assertNotIn("SCRIPT", (out / "assets/913633" / text["path"]).read_text())
            before = (out / "assets/913633/manifest.json").read_bytes()
            d.archive(URL, out, fetcher)
            self.assertEqual(fetcher.calls, [URL, IMAGE])
            self.assertEqual(before, (out / "assets/913633/manifest.json").read_bytes())
            (out / "assets/913633" / text["path"]).write_text("corrupt")
            with self.assertRaisesRegex(ValueError, "integrity"):
                d.archive(URL, out, fetcher, retry=True)

    def test_partial_and_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            out, fetcher = Path(temp), FakeFetcher(fail_image=True)
            manifest = d.archive(URL, out, fetcher)
            self.assertEqual(manifest["status"], "partial")
            fetcher.fail_image = False
            self.assertEqual(d.archive(URL, out, fetcher, retry=True)["status"], "ready")
            self.assertEqual(fetcher.calls.count(URL), 1)

    def test_blocked_no_fake_success(self):
        with tempfile.TemporaryDirectory() as temp:
            class Blocked:
                def get(self, url, referer):
                    raise HTTPError(url, 403, "Forbidden", {}, None)
            manifest = d.archive(URL, Path(temp), Blocked())
            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["files"], [])
        with self.assertRaises(ValueError):
            d.first_post('<div id="1"><article class="post-content">reply only</article></div>')
        with self.assertRaises(ValueError):
            d.image_type(b"<html>Access denied</html>", "image/png", IMAGE)
        with self.assertRaises(ValueError):
            d.image_type(PNG, "image/webp", IMAGE)
        with self.assertRaisesRegex(ValueError, "placeholder"):
            d.image_type(PNG, "image/png", "https://cdn.example.com/report.webp")

    def test_offline_capture_and_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "report.png").write_bytes(PNG)
            capture = root / "capture.json"
            capture.write_text(json.dumps({"source_url": URL, "title": "Captured", "first_post_html": '<p>2 cores</p><img src="' + IMAGE + '">', "images": [{"source_url": IMAGE, "path": "report.png", "content_type": "image/png"}]}), encoding="utf-8")
            fetcher = FakeFetcher()
            manifest = d.archive(URL, root / "out", fetcher, capture_path=capture)
            self.assertEqual(manifest["status"], "ready")
            self.assertEqual(fetcher.calls, [])
            for f in manifest["files"]:
                raw = d.safe_local(root / "out/assets/913633", f["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), f["sha256"])
            for bad in ("../secret", "/secret", "C:/secret", "..\\secret"):
                with self.assertRaises(ValueError):
                    d.safe_local(root, bad)
            with self.assertRaises(ValueError):
                d.public_url("http://127.0.0.1/secrets")
            with self.assertRaises(ValueError):
                d.normalize_post("https://nodeseek.com.evil.example/post-913633-1")

    def test_report_links(self):
        image_urls, links = d.evidence_links('<a href="/jump?to=https%3A%2F%2Fnodequality.com%2Fr%2Fabc">report</a>', "https://Report.Check.Place/hardware/abc.svg\x1b[0m", URL)
        self.assertEqual(image_urls, [])
        self.assertEqual([r["kind"] for r in links], ["report", "report"])
        self.assertEqual(links[1]["url"], "https://Report.Check.Place/hardware/abc.svg")

    def test_duplicate_content_and_full_capture_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = {"files": []}
            for url in (IMAGE, IMAGE + "?copy=1"):
                d.add_file(manifest, root, "image", PNG, "image/png", "png", url)
            self.assertEqual(len({f["id"] for f in manifest["files"]}), 2)
            self.assertEqual(len({f["path"] for f in manifest["files"]}), 1)
            capture = root / "capture.json"
            capture.write_text(json.dumps({"source_url": URL, "first_post_html": "<p>virtual visible row</p>", "first_post_text": "full report including rows beyond viewport"}), encoding="utf-8")
            d.archive(URL, root / "out", FakeFetcher(), capture_path=capture)
            result = d.archive(URL, root / "out", FakeFetcher(), retry=True)
            texts = [f for f in result["files"] if f["role"] == "first_post_text"]
            self.assertEqual(len(texts), 1)
            self.assertEqual((root / "out/assets/913633" / texts[0]["path"]).read_text(), "full report including rows beyond viewport")

    def test_capture_provenance_after_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            class Blocked:
                def get(self, url, referer):
                    raise ValueError("HTTP 403")
            blocked = d.archive(URL, root / "out", Blocked())
            self.assertEqual(blocked["capture_method"], "http")
            blocked["captured_at"] = "2000-01-01T00:00:00+00:00"
            manifest_path = root / "out/assets/913633/manifest.json"
            manifest_path.write_text(json.dumps(blocked), encoding="utf-8")
            capture = root / "capture.json"
            capture.write_text(json.dumps({"source_url": URL, "first_post_text": "actual captured post", "capture_note": "HTML reconstructed from observed DOM text"}), encoding="utf-8")
            result = d.archive(URL, root / "out", FakeFetcher(), capture_path=capture)
            self.assertEqual(result["capture_method"], "browser_import")
            self.assertEqual(result["capture_note"], "HTML reconstructed from observed DOM text")
            self.assertNotEqual(result["captured_at"], blocked["captured_at"])
            old_time, old_files = result["captured_at"], result["files"]
            result = d.archive(URL, root / "out", FakeFetcher(), capture_path=capture)
            self.assertEqual(result["captured_at"], old_time)
            self.assertEqual(result["files"], old_files)


if __name__ == "__main__":
    unittest.main()
