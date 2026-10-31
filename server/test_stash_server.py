import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import stash_server as s

TOKEN = "test-token"


class PureFunctions(unittest.TestCase):
    def test_detect_source(self):
        self.assertEqual(s.detect_source("https://www.instagram.com/reel/ABC123/?igsh=x"), "instagram-reel")
        self.assertEqual(s.detect_source("https://youtu.be/xyz"), "youtube")
        self.assertEqual(s.detect_source("https://example.com/a"), "web")
        self.assertEqual(s.detect_source(""), "text")

    def test_url_pulled_out_of_text(self):
        cap, err = s.normalize_capture({"text": "이거 봐 https://www.instagram.com/reel/ABC/ 대박"})
        self.assertIsNone(err)
        self.assertEqual(cap["url"], "https://www.instagram.com/reel/ABC/")
        self.assertEqual(cap["source"], "instagram-reel")

    def test_rejects_empty_and_non_http(self):
        self.assertIsNotNone(s.normalize_capture({})[1])
        self.assertIsNotNone(s.normalize_capture({"url": "file:///etc/passwd"})[1])
        self.assertIsNotNone(s.normalize_capture([1])[1])

    def test_slugify_keeps_korean(self):
        self.assertEqual(s.slugify("LLM 위키 만들기!"), "llm-위키-만들기")


class HttpApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        s.ensure_vault(self.vault)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), s.make_handler(self.vault, TOKEN, None))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, token=TOKEN):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_vault_layout(self):
        for rel in ("CLAUDE.md", "AGENTS.md", "Home.md", "Inbox.base", "wiki/index.md", ".obsidian/app.json"):
            self.assertTrue((self.vault / rel).exists(), rel)
        self.assertTrue((self.vault / "raw").is_dir())
        self.assertFalse((self.vault / "raw" / ".gitkeep").exists())

    def test_ensure_vault_keeps_user_edits(self):
        (self.vault / "Home.md").write_text("내가 고친 홈", encoding="utf-8")
        s.ensure_vault(self.vault)
        self.assertEqual((self.vault / "Home.md").read_text(encoding="utf-8"), "내가 고친 홈")

    def test_health_requires_token(self):
        self.assertEqual(self.call("GET", "/health")[0], 200)
        self.assertEqual(self.call("GET", "/health", token="wrong")[0], 401)

    def test_capture_writes_raw_note(self):
        code, body = self.call("POST", "/capture", {
            "url": "https://www.instagram.com/reel/ABC123/",
            "text": "꼭 볼 릴스", "source_app": "com.burbn.instagram"})
        self.assertEqual(code, 201)
        note = (self.vault / body["path"]).read_text(encoding="utf-8")
        self.assertTrue(body["path"].startswith("raw/"))
        self.assertIn("source: instagram-reel", note)
        self.assertIn('url: "https://www.instagram.com/reel/ABC123/"', note)
        self.assertIn("꼭 볼 릴스", note)

    def test_same_second_captures_do_not_overwrite(self):
        p1 = self.call("POST", "/capture", {"url": "https://example.com/x"})[1]["path"]
        p2 = self.call("POST", "/capture", {"url": "https://example.com/x"})[1]["path"]
        self.assertNotEqual(p1, p2)

    def test_capture_rejects_bad_token_and_bad_body(self):
        self.assertEqual(self.call("POST", "/capture", {"url": "https://a.com"}, token="nope")[0], 401)
        self.assertEqual(self.call("POST", "/capture", {"title": "no url"})[0], 400)
        self.assertEqual(list((self.vault / "raw").glob("*.md")), [])


class WorkerEnrich(unittest.TestCase):
    def test_worker_marks_enriched_with_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            s.ensure_vault(vault)
            cap, _ = s.normalize_capture({"url": "https://example.com/post"})
            path = s.write_capture(vault, cap)
            original = s.fetch_meta
            s.fetch_meta = lambda url: {"title": "Fetched title", "description": "요약 설명"}
            try:
                w = s.Worker(vault)
                w.submit(path, cap)
                w.jobs.join()
            finally:
                s.fetch_meta = original
            note = path.read_text(encoding="utf-8")
            self.assertIn("status: enriched", note)
            self.assertIn("# Fetched title", note)
            self.assertIn("요약 설명", note)

    def test_compile_receives_prompt_on_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            s.ensure_vault(vault)
            cap, _ = s.normalize_capture({"url": "https://example.com/post"})
            path = s.write_capture(vault, cap)
            fake_llm = ["python3", "-c", "import sys; open('wiki/prompt.txt', 'w').write(sys.stdin.read())"]
            w = s.Worker(vault, enrich=False, compile_cmd=fake_llm)
            w.submit(path, cap)
            w.jobs.join()
            prompt = (vault / "wiki" / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn(path.relative_to(vault).as_posix(), prompt)


if __name__ == "__main__":
    unittest.main()
