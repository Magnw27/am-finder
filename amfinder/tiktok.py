"""Sumber data TikTok yang bisa dipasang-lepas (pluggable).

TikTok tidak menyediakan API publik resmi untuk mengambil deskripsi dan
komentar video. Karena itu modul ini membungkus beberapa penyedia pihak
ketiga di balik satu antarmuka. Bila satu penyedia mati/diblokir, penyedia
lain bisa dicoba tanpa mengubah kode pemanggil.

Penyedia yang tersedia saat ini:
    - TikWMProvider  : https://tikwm.com/api/  (tanpa login)

Untuk menambah penyedia baru, cukup buat kelas dengan metode
``fetch_video`` dan ``fetch_comments`` lalu daftarkan di ``PROVIDERS``.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class ProviderError(RuntimeError):
    """Dilempar ketika sebuah penyedia gagal mengambil data."""


class RateLimited(ProviderError):
    """Dilempar ketika penyedia membatasi laju permintaan."""


@dataclass
class VideoInfo:
    """Data yang sudah dinormalisasi dari sebuah video TikTok."""

    url: str
    video_id: str = ""
    title: str = ""
    author: str = ""
    author_id: str = ""
    author_signature: str = ""       # bio kreator
    duration: int = 0
    comment_count: int = 0
    cover: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Comment:
    """Satu komentar (sudah dinormalisasi)."""

    text: str = ""
    author: str = ""
    author_id: str = ""
    likes: int = 0
    is_pinned: bool = False       # komentar yang di-pin / oleh pemilik video
    is_owner: bool = False
    reply_to: str = ""            # id komentar induk bila ini balasan
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------

def normalize_tiktok_url(url: str) -> str:
    """Ubah berbagai bentuk URL TikTok menjadi bentuk kanonik /video/<id>.

    Mendukung:
        - https://www.tiktok.com/@user/video/123
        - https://vt.tiktok.com/ZSxxxx/   (link pendek)
        - https://vm.tiktok.com/xxxx/
        - tiktok.com/@user/video/123
    """
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    # Buang query/hash yang tidak perlu.
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path

    m = re.search(r"/video/(\d+)", path)
    if m:
        video_id = m.group(1)
        user_m = re.search(r"/@([^/]+)", path)
        user = user_m.group(1) if user_m else "user"
        return f"https://www.tiktok.com/@{user}/video/{video_id}"

    # Link pendek (vt./vm.) — biarkan, penyedia yang akan meng-expand.
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def extract_video_id(url: str) -> str:
    m = re.search(r"/video/(\d+)", url)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Penyedia
# ---------------------------------------------------------------------------

class TikWMProvider:
    """Penyedia berbasis tikwm.com (tanpa autentikasi)."""

    name = "tikwm"
    base = "https://tikwm.com/api/"

    #: tikwm menamai endpoint komentar secara khusus.
    comment_endpoint = "https://tikwm.com/api/comment/list"

    #: tikwm membatasi 1 permintaan/detik — kita beri jeda aman.
    min_interval = 1.15
    _last_request = 0.0

    #: kata kunci pada pesan error yang menandakan limit laju.
    _RATE_HINTS = ("limit", "too many", "rate", "slow down")

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - TikWMProvider._last_request)
        if wait > 0:
            time.sleep(wait)
        TikWMProvider._last_request = time.monotonic()

    def _get(self, url: str, timeout: int = 25, retries: int = 4) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(
                url, headers={"User-Agent": _UA, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                # 429 / 403 dari Cloudflare: coba lagi setelah jeda.
                if exc.code in (429, 403) and attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    last_exc = ProviderError(f"HTTP {exc.code} dari {self.name}")
                    continue
                raise ProviderError(f"HTTP {exc.code} dari {self.name}") from exc
            except urllib.error.URLError as exc:
                if attempt < retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                    last_exc = ProviderError(f"Gagal konek ke {self.name}: {exc.reason}")
                    continue
                raise ProviderError(f"Gagal konek ke {self.name}: {exc.reason}") from exc

            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    last_exc = ProviderError(f"Respons {self.name} bukan JSON (mungkin diblokir)")
                    continue
                raise ProviderError(f"Respons {self.name} bukan JSON (mungkin diblokir)") from exc

            code = data.get("code")
            if code not in (0, None):
                msg = str(data.get("msg") or "")
                if any(h in msg.lower() for h in self._RATE_HINTS) and attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    last_exc = RateLimited(f"{self.name} membatasi laju: {msg}")
                    continue
                raise ProviderError(f"{self.name} menolak permintaan: {msg}")
            return data

        raise last_exc or ProviderError(f"{self.name}: gagal setelah {retries} percobaan")

    def fetch_video(self, url: str) -> VideoInfo:
        data = self._get(self.base + "?url=" + urllib.parse.quote(url, safe=""))
        d = data.get("data") or {}
        if not d:
            raise ProviderError("tikwm tidak mengembalikan data video")
        author = d.get("author") or {}
        info = VideoInfo(
            url=url,
            video_id=str(d.get("id") or extract_video_id(url)),
            title=d.get("title") or "",
            author=author.get("unique_id") or author.get("nickname") or "",
            author_id=str(author.get("id") or ""),
            author_signature=author.get("signature") or "",
            duration=int(d.get("duration") or 0),
            comment_count=int(d.get("comment_count") or 0),
            cover=d.get("cover") or d.get("origin_cover") or "",
            raw=d,
        )
        return info

    def fetch_comments(self, url: str, limit: int = 100) -> list[Comment]:
        """Ambil komentar, memakai penomoran halaman berbasis cursor."""
        comments: list[Comment] = []
        cursor = 0
        seen_cursors: set[int] = set()
        per_page = 20

        while len(comments) < limit:
            if cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            q = urllib.parse.urlencode(
                {"url": url, "count": per_page, "cursor": cursor}
            )
            data = self._get(f"{self.comment_endpoint}?{q}")
            d = data.get("data") or {}
            batch = d.get("comments") or []
            if not batch:
                break
            for c in batch:
                comments.append(self._normalize_comment(c))
            if not d.get("hasMore"):
                break
            cursor = int(d.get("cursor") or 0) or cursor + per_page

        return comments[:limit]

    @staticmethod
    def _normalize_comment(c: dict[str, Any]) -> Comment:
        user = c.get("user") or {}
        # tikwm menandai komentar milik kreator lewat field "is_author".
        is_owner = bool(c.get("is_author") or c.get("author_pin"))
        return Comment(
            text=c.get("text") or "",
            author=user.get("unique_id") or user.get("nickname") or c.get("unique_id") or "",
            author_id=str(user.get("uid") or c.get("uid") or ""),
            likes=int(c.get("digg_count") or 0),
            is_pinned=bool(c.get("is_pinned") or c.get("author_pin")),
            is_owner=is_owner,
            reply_to=str(c.get("reply_id") or ""),
            raw=c,
        )


class OEmbedProvider:
    """Penyedia cadangan berbasis oEmbed resmi TikTok.

    Hanya menyediakan metadata ringkas (judul, penulis, sampul) dan **tidak**
    mengembalikan komentar. Berguna sebagai jaring pengaman bila penyedia utama
    gagal, dan untuk mengisi bio/penulis yang hilang.
    """

    name = "oembed"
    endpoint = "https://www.tiktok.com/oembed"

    def _get(self, url: str, timeout: int = 20) -> dict[str, Any]:
        full = self.endpoint + "?url=" + urllib.parse.quote(url, safe="")
        req = urllib.request.Request(full, headers={"User-Agent": _UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"HTTP {exc.code} dari {self.name}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Gagal konek ke {self.name}: {exc.reason}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Respons {self.name} bukan JSON") from exc

    def fetch_video(self, url: str) -> VideoInfo:
        d = self._get(url)
        if not d or not d.get("author_url"):
            raise ProviderError("oembed tidak mengembalikan data video")
        author = (d.get("author_url") or "").rstrip("/").split("/@")[-1]
        return VideoInfo(
            url=url,
            video_id=extract_video_id(url),
            title=d.get("title") or "",
            author=author,
            cover=d.get("thumbnail_url") or "",
            raw=d,
        )

    def fetch_comments(self, url: str, limit: int = 100) -> list[Comment]:
        raise ProviderError("oembed tidak menyediakan komentar")


#: Penyedia yang lebih kaya fitur, dicoba lebih dulu.
PROVIDERS: list[type] = [TikWMProvider]

#: Penyedia cadangan untuk metadata (hanya video, tanpa komentar).
METADATA_FALLBACKS: list[type] = [OEmbedProvider]


# ---------------------------------------------------------------------------
# Antarmuka tingkat tinggi
# ---------------------------------------------------------------------------

def get_video(url: str) -> tuple[VideoInfo, str]:
    """Ambil info video memakai penyedia pertama yang berhasil.

    Bila penyedia utama gagal, coba penyedia fallback (metadata saja).
    """
    errors = []
    for provider_cls in PROVIDERS + METADATA_FALLBACKS:
        provider = provider_cls()
        try:
            return provider.fetch_video(url), provider.name
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
    raise ProviderError("Semua penyedia gagal. " + " | ".join(errors))


def get_comments(url: str, limit: int = 100) -> list[Comment]:
    """Ambil komentar memakai penyedia pertama yang berhasil."""
    errors = []
    for provider_cls in PROVIDERS:
        provider = provider_cls()
        try:
            return provider.fetch_comments(url, limit=limit)
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
    raise ProviderError("Gagal mengambil komentar. " + " | ".join(errors))


# ---------------------------------------------------------------------------
# Pencarian (hashtag / username)
# ---------------------------------------------------------------------------

#: Entri hasil pencarian yang sudah dinormalisasi.
@dataclass
class SearchItem:
    video_id: str
    url: str = ""
    title: str = ""
    author: str = ""
    cover: str = ""
    duration: int = 0
    play_count: int = 0
    digg_count: int = 0
    create_time: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


def _item_from_tikwm(v: dict[str, Any]) -> SearchItem:
    author = v.get("author") or {}
    vid = str(v.get("video_id") or v.get("id") or "")
    user = author.get("unique_id") or author.get("nickname") or v.get("unique_id") or ""
    url = f"https://www.tiktok.com/@{user}/video/{vid}" if (user and vid) else (v.get("url") or "")
    return SearchItem(
        video_id=vid,
        url=url,
        title=v.get("title") or "",
        author=user,
        cover=v.get("cover") or v.get("origin_cover") or "",
        duration=int(v.get("duration") or 0),
        play_count=int(v.get("play_count") or 0),
        digg_count=int(v.get("digg_count") or 0),
        create_time=int(v.get("create_time") or 0),
        raw=v,
    )


def _clean_query(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("@"):
        value = value[1:]
    if value.startswith("#"):
        value = value[1:]
    return value


def _tikwm_base() -> str:
    provider_cls = PROVIDERS[0]
    return provider_cls.base  # type: ignore[attr-defined]


def search_hashtag(hashtag: str, count: int = 12) -> list[SearchItem]:
    """Cari video berdasarkan nama hashtag.

    Alur: resolve nama -> id lewat ``challenge/info``, lalu ambil
    ``challenge/posts``.
    """
    name = _clean_query(hashtag)
    if not name:
        return []
    base = _tikwm_base()
    provider = PROVIDERS[0]()

    info = provider._get(base + "challenge/info?challenge_name=" + urllib.parse.quote(name, safe=""))
    cid = str((info.get("data") or {}).get("id") or "")
    if not cid:
        return []

    data = provider._get(
        base + "challenge/posts?" + urllib.parse.urlencode({"challenge_id": cid, "count": max(1, min(count, 30))})
    )
    videos = (data.get("data") or {}).get("videos") or []
    return [_item_from_tikwm(v) for v in videos][:count]


def search_user(username: str, count: int = 12) -> list[SearchItem]:
    """Cari video terbaru milik seorang pengguna."""
    name = _clean_query(username)
    if not name:
        return []
    base = _tikwm_base()
    provider = PROVIDERS[0]()
    data = provider._get(
        base + "user/posts?" + urllib.parse.urlencode({"unique_id": name, "count": max(1, min(count, 30))})
    )
    d = data.get("data") or {}
    videos = d.get("videos") or (d if isinstance(d, list) else [])
    if isinstance(videos, dict):
        videos = videos.get("videos") or []
    return [_item_from_tikwm(v) for v in videos][:count]


def user_bio(username: str) -> str:
    """Ambil bio (signature) seorang pengguna bila tersedia."""
    name = _clean_query(username)
    if not name:
        return ""
    base = _tikwm_base()
    provider = PROVIDERS[0]()
    try:
        data = provider._get(base + "user/info?unique_id=" + urllib.parse.quote(name, safe=""))
    except ProviderError:
        return ""
    d = data.get("data") or {}
    user = d.get("user") or d
    return user.get("signature") or ""