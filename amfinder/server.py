"""Server web ringan (tanpa dependensi) untuk am-finder.

Menyediakan:
    GET  /                 -> halaman UI
    GET  /api/find?url=... -> cari preset untuk satu video
    GET  /api/search?q=...&kind=hashtag|user  -> cari & sisir banyak video
    GET  /health           -> cek status

Jalankan dengan:
    python3 -m amfinder.server
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, api

__version__ = api.__version__

STATIC_DIR = Path(__file__).parent / "static"


class RateLimiter:
    """Pembatas laju sederhana berbasis IP (sliding window)."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            return max(0, int(self.window - (time.monotonic() - q[0])))


#: Batas laju per IP untuk endpoint berat (find/search).
LIMITER = RateLimiter(max_requests=20, window_seconds=60)


class Handler(BaseHTTPRequestHandler):
    server_version = "amfinder/" + __version__

    # -- util ---------------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, payload: dict, extra: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8", extra)

    def log_message(self, fmt: str, *args) -> None:  # ringkas
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0]

    def _check_rate(self) -> bool:
        ip = self._client_ip()
        if not LIMITER.allow(ip):
            retry = LIMITER.retry_after(ip)
            self._json(
                429,
                {"error": "Terlalu banyak permintaan. Coba lagi sebentar lagi."},
                extra={"Retry-After": retry},
            )
            return False
        return True

    # -- routing ------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            return self._serve_index()
        if route == "/health":
            code, payload = api.health()
            return self._json(code, payload)
        if route == "/api/find":
            if not self._check_rate():
                return
            code, payload = api.handle_find(query)
            return self._json(code, payload)
        if route == "/api/search":
            if not self._check_rate():
                return
            code, payload = api.handle_search(query)
            return self._json(code, payload)
        return self._json(404, {"error": "Tidak ditemukan"})

    def do_HEAD(self) -> None:
        self.do_GET()

    # -- handlers -----------------------------------------------------------
    def _serve_index(self) -> None:
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return self._send(500, b"index.html hilang", "text/plain; charset=utf-8")
        self._send(200, index.read_bytes(), "text/html; charset=utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="am-finder web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"am-finder berjalan di http://{args.host}:{args.port}")
    print("Tekan Ctrl+C untuk berhenti.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()