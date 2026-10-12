"""Logika inti: gabungkan data TikTok + ekstraksi link preset."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import cache, tiktok
from .extractor import (
    TIER_ALIGHT,
    TIER_DRIVE,
    TIER_OTHER,
    LinkCandidate,
    extract_links,
    is_priority_tier,
    rank,
)

#: Nama tampilan per tier. Hanya dua ini yang ditampilkan.
_DISPLAY_NAME = {
    TIER_DRIVE: "XML",
    TIER_ALIGHT: "Alight Motion",
}


@dataclass
class SourceHit:
    """Hasil ekstraksi dari satu sumber teks."""

    source: str
    label: str
    text: str
    candidates: list[LinkCandidate] = field(default_factory=list)


@dataclass
class FindResult:
    """Hasil lengkap pencarian untuk satu video."""

    video: tiktok.VideoInfo
    provider: str
    comments_scanned: int
    pinned_comments: int
    sources: list[SourceHit] = field(default_factory=list)
    links: list[LinkCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    from_cache: bool = False

    @property
    def priority_links(self) -> list[LinkCandidate]:
        """Tautan yang termasuk tier prioritas (Drive / Alight Motion)."""
        return [c for c in self.links if is_priority_tier(c.tier)]

    @property
    def visible_links(self) -> list[LinkCandidate]:
        """Hanya tautan yang layak ditampilkan: XML (Drive) & Alight Motion."""
        return self.priority_links

    @property
    def embed_url(self) -> str:
        """URL embed pemutar TikTok untuk pratinjau."""
        if not self.video.video_id:
            return ""
        return f"https://www.tiktok.com/embed/v2/{self.video.video_id}"

    def to_dict(self) -> dict[str, Any]:
        visible = self.visible_links
        return {
            "video": {
                "url": self.video.url,
                "video_id": self.video.video_id,
                "title": self.video.title,
                "author": self.video.author,
                "author_signature": self.video.author_signature,
                "duration": self.video.duration,
                "comment_count": self.video.comment_count,
                "cover": self.video.cover,
                "embed_url": self.embed_url,
            },
            "provider": self.provider,
            "from_cache": self.from_cache,
            "comments_scanned": self.comments_scanned,
            "pinned_comments": self.pinned_comments,
            "priority_count": len(visible),
            "hidden_count": len(self.links) - len(visible),
            "links": [
                {
                    "url": c.url,
                    "name": _DISPLAY_NAME.get(c.tier, "Lain"),
                    "source": c.source,
                    "tier": c.tier,
                    "priority": True,
                    "context": c.context,
                    "score": c.score,
                    "reasons": c.reasons,
                    "indirect": c.indirect,
                }
                for c in visible
            ],
            "sources": [
                {
                    "source": s.source,
                    "label": s.label,
                    "text": s.text,
                    "link_count": len(s.candidates),
                }
                for s in self.sources
            ],
            "warnings": self.warnings,
        }


def _comment_label(c: tiktok.Comment) -> str:
    if c.is_pinned:
        return "Komentar disematkan"
    if c.is_owner:
        return "Komentar kreator"
    return "Komentar"


def _run_find(url: str, comment_limit: int) -> FindResult:
    """Jalankan pencarian nyata (tanpa cache)."""
    canonical = tiktok.normalize_tiktok_url(url)
    video, provider_name = tiktok.get_video(canonical)
    warnings: list[str] = []

    comments: list[tiktok.Comment] = []
    try:
        comments = tiktok.get_comments(canonical, limit=comment_limit)
    except tiktok.ProviderError as exc:
        warnings.append(f"Komentar gagal diambil: {exc}")

    sources: list[SourceHit] = []

    # 1) Deskripsi video
    if video.title:
        sources.append(
            SourceHit(
                source="description",
                label="Deskripsi video",
                text=video.title,
                candidates=extract_links(video.title, "description"),
            )
        )

    # 2) Bio kreator
    if video.author_signature:
        sources.append(
            SourceHit(
                source="bio",
                label="Bio kreator",
                text=video.author_signature,
                candidates=extract_links(video.author_signature, "bio"),
            )
        )

    # 3) Komentar — prioritaskan yang disematkan / dari kreator.
    ordered = sorted(
        comments,
        key=lambda c: (c.is_pinned or c.is_owner, c.likes),
        reverse=True,
    )
    for c in ordered:
        if not c.text:
            continue
        cands = extract_links(c.text, "pinned_comment" if c.is_pinned else "comment")
        if cands:
            sources.append(
                SourceHit(
                    source="pinned_comment" if c.is_pinned else "comment",
                    label=_comment_label(c),
                    text=c.text,
                    candidates=cands,
                )
            )

    all_candidates = [c for s in sources for c in s.candidates]
    links = rank(all_candidates)

    has_visible = any(is_priority_tier(c.tier) for c in links)
    if not has_visible:
        warnings.append(
            "Tidak ditemukan tautan XML (Google Drive) atau Alight Motion. "
            "Tautan lain sengaja tidak ditampilkan."
        )

    return FindResult(
        video=video,
        provider=provider_name,
        comments_scanned=len(comments),
        pinned_comments=sum(1 for c in comments if c.is_pinned),
        sources=sources,
        links=links,
        warnings=warnings,
    )


def find(url: str, comment_limit: int = 100, use_cache: bool = True) -> FindResult:
    """Ambil video + komentar + bio, lalu ekstrak semua link preset.

    Hasil disimpan di cache agar permintaan berulang tidak menghabiskan kuota
    penyedia. Set ``use_cache=False`` untuk memaksa pengambilan baru.

    Args:
        url: URL video TikTok (berbagai bentuk).
        comment_limit: jumlah maksimum komentar yang dipindai.
        use_cache: pakai cache bila tersedia.
    """
    canonical = tiktok.normalize_tiktok_url(url)
    cache_key = f"{canonical}|limit={comment_limit}"

    if use_cache:
        cached = cache.get("find", cache_key)
        if cached is not None:
            result = _from_cache_dict(cached)
            if result is not None:
                result.from_cache = True
                return result

    result = _run_find(canonical, comment_limit)
    cache.set("find", cache_key, result.to_dict())
    return result


def _from_cache_dict(data: dict[str, Any]) -> FindResult | None:
    """Bangun kembali FindResult dari payload cache."""
    try:
        v = data.get("video") or {}
        video = tiktok.VideoInfo(
            url=v.get("url") or "",
            video_id=v.get("video_id") or "",
            title=v.get("title") or "",
            author=v.get("author") or "",
            author_signature=v.get("author_signature") or "",
            duration=int(v.get("duration") or 0),
            comment_count=int(v.get("comment_count") or 0),
            cover=v.get("cover") or "",
        )
        links = [
            LinkCandidate(
                url=c.get("url") or "",
                source=c.get("source") or "comment",
                tier=c.get("tier") or TIER_OTHER,
                context=c.get("context") or "",
                score=int(c.get("score") or 0),
                reasons=list(c.get("reasons") or []),
                indirect=bool(c.get("indirect")),
            )
            for c in (data.get("links") or [])
        ]
        sources = [
            SourceHit(
                source=s.get("source") or "",
                label=s.get("label") or "",
                text=s.get("text") or "",
            )
            for s in (data.get("sources") or [])
        ]
        return FindResult(
            video=video,
            provider=data.get("provider") or "cache",
            comments_scanned=int(data.get("comments_scanned") or 0),
            pinned_comments=int(data.get("pinned_comments") or 0),
            sources=sources,
            links=links,
            warnings=list(data.get("warnings") or []),
        )
    except Exception:  # noqa: BLE001 - cache rusak/kuno, anggap tidak ada
        return None


# ---------------------------------------------------------------------------
# Pencarian & penyisiran massal (by hashtag / username)
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Hasil penyisiran beberapa video dari hashtag atau username."""

    query: str
    kind: str                       # "hashtag" | "user"
    scanned: int = 0                # jumlah video yang dipindai
    items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "kind": self.kind,
            "scanned": self.scanned,
            "found": sum(1 for it in self.items if it.get("links")),
            "items": self.items,
            "warnings": self.warnings,
        }


def _scan_item(item: tiktok.SearchItem, comment_limit: int) -> dict[str, Any]:
    """Cari preset untuk satu hasil pencarian (dengan cache)."""
    base = {
        "video_id": item.video_id,
        "url": item.url,
        "title": item.title,
        "author": item.author,
        "cover": item.cover,
        "duration": item.duration,
        "play_count": item.play_count,
        "embed_url": f"https://www.tiktok.com/embed/v2/{item.video_id}" if item.video_id else "",
        "links": [],
        "error": "",
    }
    if not item.url:
        base["error"] = "URL video tidak diketahui"
        return base
    try:
        result = find(item.url, comment_limit=comment_limit)
    except tiktok.ProviderError as exc:
        base["error"] = str(exc)
        return base
    base["links"] = [
        {
            "url": c.url,
            "name": _DISPLAY_NAME.get(c.tier, "Lain"),
            "tier": c.tier,
            "source": c.source,
            "score": c.score,
        }
        for c in result.visible_links
    ]
    base["from_cache"] = result.from_cache
    return base


def search(
    query: str,
    kind: str = "hashtag",
    limit: int = 8,
    comment_limit: int = 60,
    per_video_cache: bool = True,
) -> ScanResult:
    """Cari video berdasarkan hashtag atau username, lalu sisir preset-nya.

    Args:
        query: nama hashtag atau username (boleh dengan awalan @ / #).
        kind: "hashtag" atau "user".
        limit: jumlah video maksimum yang disisir.
        comment_limit: jumlah komentar per video.
    """
    query = (query or "").strip()
    kind = "user" if kind == "user" else "hashtag"
    limit = max(1, min(limit, 20))

    if kind == "user":
        found = tiktok.search_user(query, count=limit)
    else:
        found = tiktok.search_hashtag(query, count=limit)

    result = ScanResult(query=query, kind=kind, scanned=len(found))
    if not found:
        result.warnings.append(
            "Tidak ada video ditemukan. Penyedia mungkin membatasi pencarian, "
            "atau nama hashtag/username tidak ada."
        )
        return result

    for item in found:
        result.items.append(_scan_item(item, comment_limit))

    if not any(it.get("links") for it in result.items):
        result.warnings.append("Tidak ditemukan preset XML/Alight Motion pada video-video tersebut.")

    return result