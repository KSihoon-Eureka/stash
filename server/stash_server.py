#!/usr/bin/env python3
"""Stash receiver: accepts captures from the iPhone share extension and
writes them into an Obsidian vault laid out as an LLM wiki.

Vault layout (filled from vault_template/ on first run):
  raw/        immutable captured sources, one markdown file per capture
  wiki/       LLM-maintained pages (written by the optional compile step)
  CLAUDE.md   schema that tells the LLM how to maintain wiki/

Flow: POST /capture writes raw/<file>.md and returns immediately, then a
single background worker enriches the note (yt-dlp / OpenGraph) and, with
--compile, asks `claude -p` to fold it into wiki/.

Python 3.9+, standard library only.
"""
import argparse
import datetime as dt
import hmac
import html
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import unicodedata
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 1 << 20
VAULT_TEMPLATE = Path(__file__).with_name("vault_template")
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def detect_source(url):
    if not url:
        return "text"
    host = urllib.parse.urlparse(url).netloc.lower()
    path = urllib.parse.urlparse(url).path
    if "instagram.com" in host:
        return "instagram-reel" if "/reel" in path else "instagram"
    for needle, name in (("youtube.com", "youtube"), ("youtu.be", "youtube"),
                         ("tiktok.com", "tiktok"), ("x.com", "x"),
                         ("twitter.com", "x"), ("threads.", "threads")):
        if needle in host:
            return name
    return "web"


def slugify(value, limit=50):
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[^\w가-힣]+", "-", value).strip("-")
    return value[:limit].strip("-") or "capture"


def yaml_str(value):
    return json.dumps(value, ensure_ascii=False)


def ensure_vault(vault):
    """Fill in any template file the vault lacks; never overwrites the user's edits."""
    for src in VAULT_TEMPLATE.rglob("*"):
        dest = vault / src.relative_to(VAULT_TEMPLATE)
        if src.is_dir() or src.name == ".gitkeep":
            (dest if src.is_dir() else dest.parent).mkdir(parents=True, exist_ok=True)
        elif not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)


def normalize_capture(data):
    """Validate the JSON body; returns (capture dict, error message)."""
    if not isinstance(data, dict):
        return None, "body must be a JSON object"
    url = (data.get("url") or "").strip()
    text = (data.get("text") or "").strip()
    if not url and text:
        found = URL_RE.search(text)
        url = found.group(0) if found else ""
    if not url and not text:
        return None, "url or text is required"
    if url and urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return None, "url must be http(s)"
    return {
        "url": url,
        "text": text,
        "title": (data.get("title") or "").strip(),
        "source_app": (data.get("source_app") or "").strip(),
        "captured_at": data.get("captured_at") or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": detect_source(url),
    }, None


def render_note(capture, meta=None, status="raw"):
    meta = meta or {}
    title = meta.get("title") or capture["title"] or capture["url"] or capture["text"][:60]
    lines = ["---", "type: capture", f"status: {status}", f"source: {capture['source']}"]
    for key in ("url", "source_app", "captured_at"):
        if capture[key]:
            lines.append(f"{key}: {yaml_str(capture[key])}")
    for key in ("author", "thumbnail", "duration"):
        if meta.get(key):
            lines.append(f"{key}: {yaml_str(meta[key])}")
    lines += ["tags: [stash]", "---", "", f"# {title}", ""]
    if capture["url"]:
        lines += [f"<{capture['url']}>", ""]
    if capture["text"] and capture["text"] != capture["url"]:
        lines += ["## Shared text", "", capture["text"], ""]
    if meta.get("description"):
        lines += ["## Description", "", meta["description"], ""]
    return "\n".join(lines)


def write_capture(vault, capture):
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    label = capture["title"] or capture["url"] or capture["text"]
    label = re.sub(r"^https?://(www\.)?", "", label)
    base = vault / "raw" / f"{stamp}-{slugify(label)}"
    path, n = base.with_suffix(".md"), 1
    while path.exists():
        n += 1
        path = Path(f"{base}-{n}.md")
    path.write_text(render_note(capture), encoding="utf-8")
    return path


def fetch_meta(url, timeout=20):
    """Best-effort metadata: yt-dlp for video platforms, OpenGraph otherwise."""
    if shutil.which("yt-dlp") and detect_source(url) in ("instagram-reel", "instagram", "youtube", "tiktok", "x"):
        try:
            # e.g. STASH_YTDLP_ARGS="--cookies-from-browser chrome" for Instagram, which needs a login.
            extra = shlex.split(os.environ.get("STASH_YTDLP_ARGS", ""))
            out = subprocess.run(["yt-dlp", "-J", "--skip-download", "--no-warnings", *extra, url],
                                 capture_output=True, text=True, timeout=timeout)
            if out.returncode == 0:
                info = json.loads(out.stdout)
                return {
                    "title": info.get("title") or "",
                    "description": info.get("description") or "",
                    "author": info.get("uploader") or info.get("channel") or "",
                    "thumbnail": info.get("thumbnail") or "",
                    "duration": info.get("duration") or "",
                }
        except (subprocess.TimeoutExpired, ValueError):
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "facebookexternalhit/1.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            page = resp.read(512 * 1024).decode("utf-8", "replace")
    except Exception:
        return {}

    def og(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:)?%s["\'][^>]+content=["\']([^"\']*)' % prop, page, re.I)
        return html.unescape(m.group(1)).strip() if m else ""

    return {k: v for k, v in {"title": og("title"), "description": og("description"),
                              "thumbnail": og("image")}.items() if v}


COMPILE_PROMPT = """You maintain the LLM wiki in this Obsidian vault. Follow CLAUDE.md.
A new source was captured: {rel}
Ingest it: read it, then create or update the relevant pages under wiki/,
update wiki/index.md and append one line to wiki/log.md.
Finally change `status: enriched` to `status: compiled` in {rel}. Do not edit
anything else under raw/."""


class Worker:
    """Serial background queue so enrich/compile never race on the vault."""

    def __init__(self, vault, enrich=True, compile_cmd=None):
        self.vault, self.enrich, self.compile_cmd = vault, enrich, compile_cmd
        self.jobs = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, path, capture):
        self.jobs.put((path, capture))

    def _run(self):
        while True:
            path, capture = self.jobs.get()
            try:
                self._process(path, capture)
            except Exception as exc:  # keep the worker alive
                log(f"worker error on {path.name}: {exc}")
            finally:
                self.jobs.task_done()

    def _process(self, path, capture):
        meta = fetch_meta(capture["url"]) if self.enrich and capture["url"] else {}
        path.write_text(render_note(capture, meta, status="enriched"), encoding="utf-8")
        log(f"enriched {path.name} ({'meta' if meta else 'no meta'})")
        if self.compile_cmd:
            rel = path.relative_to(self.vault).as_posix()
            # Prompt goes via stdin: --allowedTools is variadic and would swallow a trailing argument.
            out = subprocess.run(self.compile_cmd, input=COMPILE_PROMPT.format(rel=rel), cwd=self.vault,
                                 capture_output=True, text=True, timeout=600)
            if out.returncode == 0:
                log(f"compiled {path.name}")
            else:
                log(f"compile failed for {path.name} (exit {out.returncode}): {(out.stderr or out.stdout)[-500:]}")


def log(msg):
    print(f"[stash {dt.datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def make_handler(vault, token, worker):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            given = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return hmac.compare_digest(given.encode(), token.encode())

        def do_GET(self):
            if self.path != "/health":
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return self._send(401, {"error": "bad token"})
            self._send(200, {"ok": True, "vault": vault.name})

        def do_POST(self):
            if self.path != "/capture":
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return self._send(401, {"error": "bad token"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(413 if length > MAX_BODY else 400, {"error": "bad body size"})
            try:
                data = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send(400, {"error": "invalid json"})
            capture, err = normalize_capture(data)
            if err:
                return self._send(400, {"error": err})
            path = write_capture(vault, capture)
            log(f"captured {capture['source']} -> {path.name}")
            if worker:
                worker.submit(path, capture)
            self._send(201, {"ok": True, "path": path.relative_to(vault).as_posix()})

        def log_message(self, *args):
            pass

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(description="Receive iPhone captures into an Obsidian LLM wiki vault.")
    p.add_argument("--vault", default=os.environ.get("STASH_VAULT", "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Sihoon Archive"))
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=int(os.environ.get("STASH_PORT", "8765")))
    p.add_argument("--token", default=os.environ.get("STASH_TOKEN"))
    p.add_argument("--no-enrich", action="store_true", help="skip yt-dlp/OpenGraph metadata")
    p.add_argument("--compile", action="store_true", help="run `claude -p` to fold each capture into wiki/")
    args = p.parse_args(argv)
    if not args.token:
        p.error("--token or STASH_TOKEN is required")

    vault = Path(args.vault).expanduser().resolve()
    ensure_vault(vault)
    compile_cmd = None
    if args.compile:
        compile_cmd = ["claude", "-p", "--permission-mode", "acceptEdits",
                       "--allowedTools", "Read,Write,Edit,Glob,Grep"]
    worker = Worker(vault, enrich=not args.no_enrich, compile_cmd=compile_cmd)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(vault, args.token, worker))
    log(f"listening on {args.host}:{server.server_port} -> {vault}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
