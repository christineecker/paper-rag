"""paper-rag library dashboard CLI.

python scripts/dashboard.py [--home PATH] [--home-name NAME] [--out DIR] [--open]

Scans $PAPER_RAG_HOME into skills/paper-rag/templates/dashboard.html's JSON shape
and writes a self-contained <home>/dashboard/index.html (plus copied figure
covers under dashboard/figs/).
"""
from __future__ import annotations

import functools
import json
import secrets
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config as cfg  # noqa: E402
from lib import dashboard_data  # noqa: E402
from lib.attach import AttachError, attach_pdf  # noqa: E402

app = typer.Typer(add_completion=False)

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "skills" / "paper-rag" / "templates" / "dashboard.html"
DEFAULT_ATTACH_PORT = 8420


def build_dashboard(
    home: Path, out_dir: Path, attach_port: Optional[int] = None, attach_token: Optional[str] = None
) -> dict:
    """Scan `home` and write out_dir/index.html + out_dir/figs/*. Returns a JSON
    summary (paper count, storage, out_dir).

    attach_port: if set, the dashboard's PDF-attach drop zone targets a local
    upload server on that port (see serve_dashboard) instead of staying
    session-only. Baked into the page at generation time since the page may be
    published elsewhere (e.g. a claude.ai artifact) and can't discover it.

    attach_token: required alongside attach_port. Sent back as a header on every
    attach request; the server rejects requests without the matching token. CORS
    on the attach route is wide open (any origin can preflight successfully) so
    without this a malicious page open in the same browser could silently write
    into the library while the server is running - the token is the only thing
    that stops that, so never render the page without one when attach_port is set."""
    papers = dashboard_data.scan_papers(home)
    storage = dashboard_data.storage_summary(home)

    figs_dir = out_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)
    for existing in figs_dir.glob("*.png"):
        existing.unlink()

    papers_json = []
    for paper in papers:
        cover_src = paper.pop("_cover_src", None)
        if cover_src:
            shutil.copy(cover_src, figs_dir / f"{paper['doc_key']}.png")
        figure_srcs = paper.pop("_figure_srcs", [])
        for i, src in enumerate(figure_srcs):
            shutil.copy(src, figs_dir / f"{paper['doc_key']}_{i}.png")
        papers_json.append(paper)

    template = TEMPLATE_PATH.read_text()
    html = template.replace("__PAPERS_JSON__", json.dumps(papers_json, indent=2))
    html = html.replace("__STORAGE_JSON__", json.dumps(storage, indent=2))
    html = html.replace("__ATTACH_PORT__", json.dumps(attach_port))
    html = html.replace("__ATTACH_TOKEN__", json.dumps(attach_token))
    html = html.replace("__GENERATED_AT__", json.dumps(datetime.now().strftime("%d %b %Y %H:%M")))

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.html"
    index_path.write_text(html)

    return {
        "home": str(home),
        "out": str(index_path),
        "n_papers": len(papers_json),
        "n_fulltext": sum(1 for p in papers_json if p["has_fulltext"]),
        "n_figures": sum(1 for p in papers_json if p["n_figures"] > 0),
        "storage": storage,
    }


class _AttachHandler(SimpleHTTPRequestHandler):
    """Static file server rooted at <home> (so the dashboard's relative
    ../papers/<doc_key>/source.pdf links resolve), plus one write route:
    POST /attach/<doc_key>[?force=1] with the raw PDF bytes as the body.

    CORS is wide open (Access-Control-Allow-Origin: *) because the page making
    the request is commonly a published claude.ai artifact (cross-origin from
    this localhost server), not a same-origin file - the browser won't let a
    fixed origin allowlist cover that case reliably. Wildcard CORS alone would
    let *any* site open in the same browser forge a write here (classic
    localhost CSRF / DNS-rebinding target), so two things gate the actual
    write: the X-Attach-Token header must match the token baked into this run's
    dashboard.html (unknown to a random attacker page), and the Host header
    must be 127.0.0.1:<port> (defeats DNS rebinding onto this port). Also bound
    to 127.0.0.1 only, so it's reachable solely from the machine running it."""

    def __init__(self, *args, home: Path, token: str, **kwargs):
        self._home = home
        self._token = token
        super().__init__(*args, directory=str(home), **kwargs)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()  # CORS headers added by the end_headers() override below

    def do_POST(self):
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        if len(parts) != 2 or parts[0] != "attach" or not parts[1]:
            self._send_json(404, {"error": "not_found"})
            return

        host = self.headers.get("Host", "")
        if host.split(":", 1)[0] not in ("127.0.0.1", "localhost"):
            self._send_json(403, {"error": "bad_host", "hint": "request must target 127.0.0.1"})
            return
        if not secrets.compare_digest(self.headers.get("X-Attach-Token", ""), self._token):
            self._send_json(403, {"error": "bad_token", "hint": "missing or stale X-Attach-Token"})
            return

        doc_key = parts[1]
        force = "force=1" in self.path
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        try:
            result = attach_pdf(self._home, doc_key, data, force=force)
            self._send_json(200, result)
        except AttachError as exc:
            self._send_json(409, exc.payload)
        except Exception as exc:  # keep the server alive on unexpected errors
            self._send_json(500, {"error": "internal", "detail": str(exc)})

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Attach-Token")

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()  # CORS headers added by the end_headers() override below
        self.wfile.write(body)

    def end_headers(self):
        # static GETs (index.html, figs/*, papers/*/source.pdf) also need CORS
        # so a claude.ai-hosted copy of the page can still show local figures.
        self._cors_headers()
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


def serve_dashboard(home: Path, port: int, token: str) -> None:
    handler = functools.partial(_AttachHandler, home=home, token=token)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/dashboard/index.html"
    print(json.dumps({"serving": url, "home": str(home)}, indent=2))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


@app.command()
def main(
    home: Optional[str] = typer.Option(None, "--home", help="paper-rag home dir override (see config.py)"),
    home_name: Optional[str] = typer.Option(None, "--home-name", help="named home from homes.json"),
    out: Optional[str] = typer.Option(None, "--out", help="output dir (default: <home>/dashboard)"),
    open_browser: bool = typer.Option(False, "--open", help="open the generated dashboard in the default browser"),
    serve: bool = typer.Option(
        False, "--serve", help="run a local server so the dashboard's PDF drop zone can save into the library"
    ),
    port: int = typer.Option(DEFAULT_ATTACH_PORT, "--port", help="port for --serve"),
):
    resolved_home = cfg.resolve_home(home=home, home_name=home_name)
    if serve and out:
        print(json.dumps({"error": "serve_ignores_out", "hint": "--serve always uses <home>/dashboard"}))
        raise typer.Exit(code=1)
    out_dir = Path(out).expanduser().resolve() if out else resolved_home / "dashboard"
    token = secrets.token_urlsafe(24) if serve else None

    summary = build_dashboard(resolved_home, out_dir, attach_port=port if serve else None, attach_token=token)
    print(json.dumps(summary, indent=2))

    if serve:
        url = f"http://127.0.0.1:{port}/dashboard/index.html"
        webbrowser.open(url)
        serve_dashboard(resolved_home, port, token)
    elif open_browser:
        webbrowser.open(Path(summary["out"]).as_uri())


if __name__ == "__main__":
    app()
