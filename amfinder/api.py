"""Logika dispatch HTTP bersama untuk server lokal & adaptor Vercel.

Modul ini memisahkan *routing & validasi* dari *transport*, sehingga server
stdlib (:mod:`amfinder.server`) dan entrypoint WSGI (``index.py``) memakai jalur
yang sama persis. Setiap fungsi mengembalikan ``(http_status, payload)``.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import __version__, cache, finder, tiktok

#: Pola URL TikTok yang diterima (penuh maupun pendek).
TIKTOK_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.|vt\.|vm\.|m\.)?tiktok\.com/",
    re.IGNORECASE,
)


def _clamp(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def health() -> tuple[int, dict]:
    return 200, {"status": "ok", "version": __version__, "cache": cache.stats()}


def handle_find(query: dict) -> tuple[int, dict]:
    """Tangani pencarian satu video. ``query`` berisi list nilai (parse_qs)."""
    url = (query.get("url") or [""])[0].strip()
    if not url:
        return 400, {"error": "Parameter 'url' wajib diisi."}
    if not TIKTOK_URL_RE.match(url):
        return 400, {"error": "URL harus berupa tautan TikTok yang valid."}

    limit = _clamp((query.get("limit") or ["100"])[0], 100, 10, 300)
    nocache = (query.get("nocache") or ["0"])[0] in ("1", "true")

    started = time.time()
    try:
        result = finder.find(url, comment_limit=limit, use_cache=not nocache)
    except tiktok.ProviderError as exc:
        return 502, {"error": "Gagal mengambil data dari TikTok.", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - laporkan apa adanya ke UI
        return 500, {"error": "Kesalahan internal.", "detail": str(exc)}

    payload = result.to_dict()
    payload["elapsed_ms"] = round((time.time() - started) * 1000)
    return 200, payload


def handle_search(query: dict) -> tuple[int, dict]:
    """Tangani pencarian by hashtag/username lalu sisir preset-nya."""
    q = (query.get("q") or query.get("query") or [""])[0].strip()
    if not q:
        return 400, {"error": "Parameter 'q' (hashtag/username) wajib diisi."}

    kind = (query.get("kind") or ["hashtag"])[0].lower()
    if kind not in ("hashtag", "user"):
        kind = "hashtag"
    limit = _clamp((query.get("limit") or ["6"])[0], 6, 1, 20)
    comment_limit = _clamp((query.get("comment_limit") or ["50"])[0], 50, 10, 150)

    started = time.time()
    try:
        result = finder.search(q, kind=kind, limit=limit, comment_limit=comment_limit)
    except tiktok.ProviderError as exc:
        return 502, {"error": "Gagal mencari data dari TikTok.", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return 500, {"error": "Kesalahan internal.", "detail": str(exc)}

    payload = result.to_dict()
    payload["elapsed_ms"] = round((time.time() - started) * 1000)
    return 200, payload