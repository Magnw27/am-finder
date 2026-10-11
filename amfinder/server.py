"""Server web ringan (tanpa dependensi) untuk am-finder.

Menyediakan:
    GET  /                 -> halaman UI
    GET  /api/find?url=... -> jalankan pencarian, kembalikan JSON
    GET  /health           -> cek status

Jalankan dengan:
    python3 -m amfinder.server
"""

from __future__ import annotations

import json
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, finder, tiktok

STATIC_DIR = Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    server_version = "amfinder/" + __version__

    # -- util ---------------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:  # ringkas
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    # -- routing ------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            return self._serve_index()
        if route == "/health":
            return self._json(200, {"status": "ok", "version": __version__})
        if route == "/api/find":
            return self._api_find(query)
        return self._json(404, {"error": "Tidak ditemukan"})

    def do_HEAD(self) -> None:
        self.do_GET()

    # -- handlers -----------------------------------------------------------
    def _serve_index(self) -> None:
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return self._send(500, b"index.html hilang", "text/plain; charset=utf-8")
        self._send(200, index.read_bytes(), "text/html; charset=utf-8")

    def _api_find(self, query: dict) -> None:
        url = (query.get("url") or [""])[0].strip()
        if not url:
            return self._json(400, {"error": "Parameter 'url' wajib diisi."})

        try:
            limit = int((query.get("limit") or ["100"])[0])
            limit = max(10, min(limit, 300))
        except ValueError:
            limit = 100

        started = time.time()
        try:
            result = finder.find(url, comment_limit=limit)
        except tiktok.ProviderError as exc:
            return self._json(
                502,
                {"error": "Gagal mengambil data dari TikTok.", "detail": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - laporkan apa adanya ke UI
            return self._json(500, {"error": "Kesalahan internal.", "detail": str(exc)})

        payload = result.to_dict()
        payload["elapsed_ms"] = round((time.time() - started) * 1000)
        return self._json(200, payload)


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