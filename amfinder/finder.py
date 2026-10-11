"""Logika inti: gabungkan data TikTok + ekstraksi link preset."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import tiktok
from .extractor import (
    LinkCandidate,
    extract_links,
    is_priority_tier,
    rank,
)


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

    @property
    def priority_links(self) -> list[LinkCandidate]:
        """Tautan yang termasuk tier prioritas (Drive / Alight Motion)."""
        return [c for c in self.links if is_priority_tier(c.tier)]

    def to_dict(self) -> dict[str, Any]:
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
            },
            "provider": self.provider,
            "comments_scanned": self.comments_scanned,
            "pinned_comments": self.pinned_comments,
            "priority_count": len(self.priority_links),
            "links": [
                {
                    "url": c.url,
                    "source": c.source,
                    "tier": c.tier,
                    "priority": is_priority_tier(c.tier),
                    "context": c.context,
                    "score": c.score,
                    "reasons": c.reasons,
                    "indirect": c.indirect,
                }
                for c in self.links
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


def find(url: str, comment_limit: int = 100) -> FindResult:
    """Ambil video + komentar + bio, lalu ekstrak semua link preset.

    Args:
        url: URL video TikTok (berbagai bentuk).
        comment_limit: jumlah maksimum komentar yang dipindai.
    """
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

    has_priority = any(is_priority_tier(c.tier) for c in links)
    if comments and not links:
        warnings.append(
            "Tidak ada tautan yang jelas. Tautan mungkin ada di dalam video "
            "(harus dibaca manual) atau di bio kreator."
        )
    elif links and not has_priority:
        warnings.append(
            "Tidak ditemukan tautan Drive/Alight Motion. Tautan lain tetap "
            "ditampilkan sebagai prioritas rendah."
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