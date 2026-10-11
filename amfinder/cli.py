"""Antarmuka baris perintah (CLI) untuk am-finder.

Contoh:
    python3 -m amfinder.cli https://www.tiktok.com/@user/video/123
    python3 -m amfinder.cli <url> --limit 150 --json
"""

from __future__ import annotations

import argparse
import json
import sys

from . import finder, tiktok
from .extractor import TIER_ALIGHT, TIER_DRIVE

_TIER_LABEL = {
    TIER_DRIVE: "Drive",
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
        f"{result.pinned_comments} disematkan (via {result.provider})"
    )
    lines.append("=" * 66)

    priority = result.priority_links
    _pid = {id(c) for c in priority}
    others = [c for c in result.links if id(c) not in _pid]

    if priority:
        lines.append(f"\n{len(priority)} tautan prioritas (Drive / Alight Motion):\n")
        for i, c in enumerate(priority, 1):
            lines.append(f"{i:2d}. [{_TIER_LABEL.get(c.tier, c.tier)}] skor={c.score:>3} sumber={c.source}")
            lines.append(f"    {c.url}")
            if c.context:
                lines.append(f"    konteks: {c.context[:160]}")
            lines.append("")

    if others:
        lines.append(f"{len(others)} tautan lain (prioritas rendah):\n")
        for i, c in enumerate(others, 1):
            tag = " [PETUNJUK]" if c.indirect else ""
            lines.append(f"{i:2d}. skor={c.score:>3} sumber={c.source}{tag}")
            lines.append(f"    {c.url or '(lihat konteks)'}")
            lines.append("")

    if not result.links:
        lines.append("\nTidak ada tautan yang ditemukan.")

    for w in result.warnings:
        lines.append(f"! Peringatan: {w}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amfinder",
        description="Cari link preset Alight Motion dari sebuah video TikTok.",
    )
    parser.add_argument("url", help="URL video TikTok")
    parser.add_argument("--limit", type=int, default=100, help="maksimum komentar (default 100)")
    parser.add_argument("--json", action="store_true", help="keluarkan JSON mentah")
    args = parser.parse_args(argv)

    try:
        result = finder.find(args.url, comment_limit=args.limit)
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