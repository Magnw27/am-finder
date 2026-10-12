"""Entrypoint WSGI untuk Vercel.

Vercel Python runtime memuat variabel ``app`` dari berkas entrypoint
(``index.py`` di root proyek). Berkas ini menjadi adaptor tipis di atas logika
berbagi :mod:`amfinder.api` — kode inti yang dipakai secara lokal tidak berubah.

Rute:
    GET /                 -> UI
    GET /health           -> cek status
    GET /api/find?url=... -> cari preset untuk satu video (JSON)
    GET /api/search?q=... -> cari & sisir by hashtag/username (JSON)
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Callable, Iterable

from amfinder import api

# Cari index.html relatif terhadap proyek (cwd di Vercel = root proyek).
_HERE = Path(__file__).resolve().parent
_HTML_CANDIDATES = (
    _HERE / "amfinder" / "static" / "index.html",
    _HERE / "static" / "index.html",
)

StartResponse = Callable[..., object]
Environ = dict


def _load_html() -> bytes:
    for path in _HTML_CANDIDATES:
        if path.exists():
            return path.read_bytes()
    return b"index.html tidak ditemukan di bundle"


def _respond(start_response: StartResponse, status: str, body: bytes, ctype: str) -> list[bytes]:
    start_response(
        status,
        [
            ("Content-Type", ctype),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _json(start_response: StartResponse, status: str, payload: dict) -> list[bytes]:
    return _respond(
        start_response,
        status,
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        "application/json; charset=utf-8",
    )


def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
    """Aplikasi WSGI utama."""
    path = environ.get("PATH_INFO", "/") or "/"
    query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))

    if path in ("/", "/index.html"):
        return _respond(start_response, "200 OK", _load_html(), "text/html; charset=utf-8")

    if path == "/health":
        code, payload = api.health()
        return _json(start_response, _status(code), payload)

    if path == "/api/find":
        code, payload = api.handle_find(query)
        return _json(start_response, _status(code), payload)

    if path == "/api/search":
        code, payload = api.handle_search(query)
        return _json(start_response, _status(code), payload)

    return _json(start_response, "404 Not Found", {"error": "Tidak ditemukan"})


_STATUS_TEXT = {
    200: "200 OK",
    400: "400 Bad Request",
    429: "429 Too Many Requests",
    500: "500 Internal Server Error",
    502: "502 Bad Gateway",
}


def _status(code: int) -> str:
    return _STATUS_TEXT.get(code, f"{code} OK")


#: Alias umum untuk beberapa runtime.
application = app
handler = app