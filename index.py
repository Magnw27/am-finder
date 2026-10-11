"""Entrypoint WSGI untuk Vercel.

Vercel Python runtime memuat variabel ``app`` dari berkas entrypoint
(``index.py`` di root proyek). Berkas ini menjadi adaptor tipis di atas
logika inti :mod:`amfinder.finder` — kode inti yang dipakai secara lokal
tidak berubah sama sekali.

Rute:
    GET /                 -> UI
    GET /health           -> cek status
    GET /api/find?url=... -> jalankan pencarian (JSON)
"""

from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Iterable

from amfinder import __version__, finder, tiktok

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
        return _json(start_response, "200 OK", {"status": "ok", "version": __version__})

    if path == "/api/find":
        url = (query.get("url") or [""])[0].strip()
        if not url:
            return _json(start_response, "400 Bad Request", {"error": "Parameter 'url' wajib diisi."})
        try:
            limit = int((query.get("limit") or ["60"])[0])
            limit = max(10, min(limit, 200))
        except ValueError:
            limit = 60

        started = time.time()
        try:
            result = finder.find(url, comment_limit=limit)
        except tiktok.ProviderError as exc:
            return _json(
                start_response,
                "502 Bad Gateway",
                {"error": "Gagal mengambil data dari TikTok.", "detail": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001
            return _json(
                start_response,
                "500 Internal Server Error",
                {"error": "Kesalahan internal.", "detail": str(exc)},
            )

        payload = result.to_dict()
        payload["elapsed_ms"] = round((time.time() - started) * 1000)
        return _json(start_response, "200 OK", payload)

    return _json(start_response, "404 Not Found", {"error": "Tidak ditemukan"})


#: Alias umum untuk beberapa runtime.
application = app
handler = app