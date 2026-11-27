#!/usr/bin/env python3
"""Serve the owner portal on this machine (standard library; live mode also needs the project's psycopg2).

    python frontend/serve.py              snapshot: the recorded run, no database (http://127.0.0.1:8080)
    python frontend/serve.py --live       live: the page reads the warehouse through /api/data, as lue_reader
    python frontend/serve.py --port 9000 --no-browser

Live mode answers GET /api/data with the portal's JSON, read from lue_reporting (frontend/live_data.py) and
kept for --cache seconds (default 20); the page asks again every 60 seconds and shows "Live" with the time of
the last read. Without --live there is no /api/data and the page falls back to frontend/data.js.
Listens on 127.0.0.1 only; serves index.html, data.js and /api/data, GET only.
"""

import argparse
import http.server
import json
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {"/": "index.html", "/index.html": "index.html", "/data.js": "data.js"}
TYPES = {"index.html": "text/html; charset=utf-8", "data.js": "text/javascript; charset=utf-8"}


class Cache:
    """Keeps the last good answer for ttl seconds; a failed read serves the last good one if it is under 10 minutes old."""

    def __init__(self, provider, ttl):
        self.provider, self.ttl, self.lock = provider, ttl, threading.Lock()
        self.value, self.at = None, 0.0

    def get(self, force=False):
        with self.lock:
            now = time.time()
            if self.value is not None and not force and now - self.at < self.ttl:
                return self.value, None
            try:
                self.value, self.at = self.provider(), now
                return self.value, None
            except Exception as exc:  # noqa: BLE001  (any database failure: tell the page, keep serving)
                if self.value is not None and now - self.at < 600:
                    return self.value, str(exc).strip()
                raise


def make_handler(cache):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "LUEPortal"

        def log_message(self, fmt, *args):
            pass  # keep the terminal quiet; errors are returned to the page

        def send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path, _, query = self.path.partition("?")
            if path == "/api/data":
                if cache is None:
                    return self.send(404, b'{"error":"live mode is off: start with --live"}', "application/json")
                try:
                    data, warning = cache.get(force="refresh=1" in query)
                except Exception as exc:  # noqa: BLE001
                    body = json.dumps({"error": f"cannot read the warehouse: {str(exc).strip()}"}).encode()
                    return self.send(503, body, "application/json")
                extra = {"X-Stale-Reason": warning.replace("\n", " ")[:200]} if warning else None
                return self.send(200, json.dumps(data, separators=(",", ":")).encode(), "application/json", extra)
            name = FILES.get(path)
            if not name:
                return self.send(404, b"not found", "text/plain")
            self.send(200, (HERE / name).read_bytes(), TYPES[name])

        def _no(self):
            self.send(405, b"read-only: GET only", "text/plain", {"Allow": "GET"})

        do_POST = do_PUT = do_DELETE = do_PATCH = _no  # noqa: N815

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--live", action="store_true", help="read the warehouse through /api/data")
    ap.add_argument("--cache", type=float, default=20, help="seconds to keep a read (live mode)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args()

    cache = None
    if args.live:
        from live_data import fetch_live

        print("reading the warehouse as lue_reader ...")
        try:
            fetch_live()
        except Exception as exc:  # noqa: BLE001
            print(f"cannot read the warehouse: {str(exc).strip()}\n"
                  "Check .env (PGHOST, PGPORT, LUE_READER_PASSWORD), that the warehouse is loaded, and that "
                  "python scripts/db_deploy.py has applied sql/50_reporting/02_owner_portal.sql.")
            return 1
        cache = Cache(fetch_live, args.cache)
    elif not (HERE / "data.js").exists():
        print("frontend/data.js is missing: run  python frontend/build_data.py  first")
        return 1
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(cache))
    except OSError as exc:
        print(f"cannot listen on port {args.port}: {exc}. Try --port {args.port + 1}")
        return 1
    url = f"http://127.0.0.1:{args.port}/"
    print(f"LUE owner portal ({'live' if cache else 'snapshot'}): {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
