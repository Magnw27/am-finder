"""Antarmuka baris perintah (CLI) untuk am-finder.

Contoh:
    python3 -m amfinder.cli https://www.tiktok.com/@user/video/123
    python3 -m amfinder.cli <url> --limit 150 --json
    python3 -m amfinder.cli --scan alightmotion                # sisir hashtag
    python3 -m amfinder.cli --scan alightmotion --kind user    # sisir username
    python3 -m amfinder.cli <url> --no-cache                   # paksa ambil baru
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, cache, finder, tiktok
from .extractor import TIER_ALIGHT, TIER_DRIVE

_TIER_LABEL = {
    TIER_DRIVE: "XML",
    TIER_ALIGHT: "Alight Motion",
}


def _format(result: finder.FindResult) -> str:
    v = result.video
    lines = []
    lines.append("=" * 66)
    lines.append(f"Video   : {v.url}")
    lines.append(f"Kreator : @{v.author or '?'}")
    if v.author_signature:
        lines.append(f"Bio     : {v.author_signature}")
    if v.title:
        lines.append(f"Deskripsi: {v.title[:200]}")
    lines.append(
        f"Sumber  : {result.comments_scanned} komentar dipindai, "
        f"{result.pinned_comments} disematkan (via {result.provider}"
        + (", dari cache" if result.from_cache else "")
        + ")"
    )
    lines.append("=" * 66)

    priority = result.visible_links

    if priority:
        lines.append(f"\n{len(priority)} tautan ditemukan (XML / Alight Motion):\n")
        for i, c in enumerate(priority, 1):
            name = _TIER_LABEL.get(c.tier, c.tier)
            lines.append(f"{i:2d}. [{name}] skor={c.score:>3} sumber={c.source}")
            lines.append(f"    {c.url}")
            if c.context:
                lines.append(f"    konteks: {c.context[:160]}")
            lines.append("")
    else:
        lines.append(
            "\nTidak ditemukan tautan XML (Google Drive) atau Alight Motion."
        )

    for w in result.warnings:
        lines.append(f"! Peringatan: {w}")

    return "\n".join(lines)


def _format_scan(result: finder.ScanResult) -> str:
    label = ("@" + result.query) if result.kind == "user" else ("#" + result.query)
    lines = []
    lines.append("=" * 66)
    lines.append(f"Sisir   : {label} ({result.kind})")
    lines.append(f"Scanned : {result.scanned} video · {result.to_dict()['found']} berpreset")
    lines.append("=" * 66)

    for it in result.items:
        lines.append("")
        lines.append(f"@{it.get('author') or '?'} · {it.get('video_id')}")
        if it.get("title"):
            lines.append(f"  {it['title'][:90]}")
        if it.get("error"):
            lines.append(f"  ! {it['error']}")
        for link in it.get("links", []):
            lines.append(f"  [{link['name']}] skor={link['score']} {link['url']}")

    for w in result.warnings:
        lines.append(f"\n! Peringatan: {w}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amfinder",
        description="Cari link preset Alight Motion dari video TikTok.",
    )
    parser.add_argument("url", nargs="?", help="URL video TikTok")
    parser.add_argument("--scan", metavar="NAMA", help="sisir hashtag/username (bukan URL)")
    parser.add_argument("--kind", choices=["hashtag", "user"], default="hashtag",
                        help="jenis --scan (default: hashtag)")
    parser.add_argument("--limit", type=int, default=100, help="maksimum komentar (default 100)")
    parser.add_argument("--count", type=int, default=6, help="jumlah video untuk --scan (default 6)")
    parser.add_argument("--no-cache", action="store_true", help="abaikan cache, ambil data baru")
    parser.add_argument("--clear-cache", action="store_true", help="hapus cache lalu keluar")
    parser.add_argument("--version", action="version", version=f"am-finder {__version__}")
    parser.add_argument("--json", action="store_true", help="keluarkan JSON mentah")
    args = parser.parse_args(argv)

    if args.clear_cache:
        removed = cache.clear()
        print(f"Cache dibersihkan: {removed} entri dihapus.")
        return 0

    if args.scan:
        try:
            result = finder.search(
                args.scan, kind=args.kind, limit=args.count, comment_limit=min(args.limit, 150)
            )
        except tiktok.ProviderError as exc:
            print(f"Gagal: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(_format_scan(result))
        return 0

    if not args.url:
        parser.error("berikan URL video, atau gunakan --scan NAMA")

    try:
        result = finder.find(args.url, comment_limit=args.limit, use_cache=not args.no_cache)
    except tiktok.ProviderError as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_format(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())