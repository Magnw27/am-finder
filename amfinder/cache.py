"""Cache sederhana di disk (tanpa dependensi) untuk am-finder.

Tujuan: hemat permintaan ke penyedia TikTok, sekaligus membuat respons lebih
cepat saat video yang sama diminta berulang. Cache disimpan sebagai berkas JSON
di direktori sementara, dengan masa berlaku (TTL) yang bisa diatur.

Mulai sekarang cache bersifat *best effort*: kalau gagal baca/tulis, aplikasi
tetap jalan seperti biasa.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

#: Lokasi cache. Bisa ditimpa lewat env AMFINDER_CACHE_DIR.
CACHE_DIR = Path(os.environ.get("AMFINDER_CACHE_DIR") or (Path(tempfile.gettempdir()) / "amfinder-cache"))

#: TTL bawaan: 6 jam.
DEFAULT_TTL = int(os.environ.get("AMFINDER_CACHE_TTL", "21600"))

#: Batas jumlah entri agar tidak menumpuk (dibersihkan saat menyimpan).
MAX_ENTRIES = 500


def _enabled() -> bool:
    return CACHE_DIR is not None and DEFAULT_TTL > 0


def _key(namespace: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    safe_ns = "".join(c for c in namespace if c.isalnum() or c in "-_")
    return f"{safe_ns}-{digest}.json"


def _path(namespace: str, value: str) -> Path:
    return CACHE_DIR / _key(namespace, value)


def get(namespace: str, value: str, ttl: int | None = None) -> Any | None:
    """Ambil entri cache; None bila tidak ada atau kedaluwarsa."""
    if not _enabled():
        return None
    path = _path(namespace, value)
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    age = time.time() - float(data.get("_cached_at", 0))
    if age > (ttl if ttl is not None else DEFAULT_TTL):
        return None
    return data.get("payload")


def set(namespace: str, value: str, payload: Any) -> None:  # noqa: A001
    """Simpan entri cache (best effort)."""
    if not _enabled():
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _path(namespace, value)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"_cached_at": time.time(), "payload": payload}, ensure_ascii=False),
            "utf-8",
        )
        tmp.replace(path)
        _maybe_prune()
    except OSError:
        return


def get_or_set(namespace: str, value: str, producer: Callable[[], Any], ttl: int | None = None) -> tuple[Any, bool]:
    """Kembalikan (payload, dari_cache). Bila belum ada, jalankan producer lalu simpan."""
    hit = get(namespace, value, ttl=ttl)
    if hit is not None:
        return hit, True
    payload = producer()
    set(namespace, value, payload)
    return payload, False


def _maybe_prune() -> None:
    """Buang entri tertua bila melebihi MAX_ENTRIES."""
    try:
        files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    if len(files) <= MAX_ENTRIES:
        return
    for path in files[: len(files) - MAX_ENTRIES]:
        try:
            path.unlink()
        except OSError:
            pass


def clear() -> int:
    """Hapus semua entri cache; kembalikan jumlah berkas yang dihapus."""
    count = 0
    try:
        for path in CACHE_DIR.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
    except OSError:
        pass
    return count


def stats() -> dict[str, Any]:
    """Ringkasan isi cache untuk endpoint /health."""
    try:
        files = list(CACHE_DIR.glob("*.json"))
    except OSError:
        files = []
    return {
        "enabled": _enabled(),
        "dir": str(CACHE_DIR),
        "entries": len(files),
        "ttl_seconds": DEFAULT_TTL,
    }