"""Tiny localhost-only HTTP server so triage.html can actually save triage.json
straight into its search_dir, instead of going through a browser download
dialog. Only used when explicitly requested (`triage.py --serve`) — the
default flow still just writes a static triage.html for the browser's
File System Access API / download fallback to handle.

GET  /<anything>  -> serves search_dir/<anything> (triage.html, etc.)
POST /save        -> writes the request body as-is to search_dir/triage.json
"""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


def _make_handler(search_dir: Path, on_save: Callable[[Path], None]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
            pass  # keep stdout to our own explicit prints, not per-request access logs

        def do_GET(self):  # noqa: N802 - stdlib method name
            rel = self.path.lstrip("/") or "triage.html"
            target = (search_dir / rel).resolve()
            try:
                target.relative_to(search_dir.resolve())
            except ValueError:
                self.send_error(403, "outside search_dir")
                return
            if not target.is_file():
                self.send_error(404, "not found")
                return
            content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "application/octet-stream"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 - stdlib method name
            if self.path != "/save":
                self.send_error(404, "not found")
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            try:
                json.loads(body)  # validate before writing
            except json.JSONDecodeError as exc:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())
                return

            out_path = search_dir / "triage.json"
            out_path.write_bytes(body)
            on_save(out_path)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "path": str(out_path)}).encode())

    return Handler


def serve_triage(search_dir: Path, *, port: int = 0, open_browser: bool = True) -> None:
    """Serve search_dir/triage.html on 127.0.0.1 until interrupted (Ctrl+C).
    Each successful save prints a confirmation line to stdout."""

    def on_save(path: Path) -> None:
        print(f"saved {path}", flush=True)

    handler = _make_handler(search_dir, on_save)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/triage.html"

    print(f"serving {search_dir} at {url}", flush=True)
    print("Click 'Save triage.json' in the page to write directly into the search folder.", flush=True)
    print("Ctrl+C to stop.", flush=True)

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("stopped", flush=True)
