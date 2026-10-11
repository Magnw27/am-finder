"""Ekstraksi link preset dari teks TikTok.

Modul ini adalah "otak" dari am-finder. Ia menerima teks mentah dari
deskripsi video, komentar, atau bio kreator, lalu mengembalikan daftar
kandidat link preset Alight Motion beserta skor kepercayaannya.

Tantangan utama: link preset sering disamarkan atau tidak dalam bentuk
URL utuh, misalnya:
    - "drive.google.com/file/d/xxxx"
    - "link di bio ya"
    - "cek komentar pin"
    - "me diafire / am.preset.by.xxx"
    - "kunjungi linktree saya"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Pola & kata kunci
# ---------------------------------------------------------------------------

# URL utuh (http/https) maupun domain telanjang yang umum dipakai berbagi file.
_HOSTS = (
    r"drive\.google\.com",
    r"docs\.google\.com",
    r"dropbox\.com",
    r"mediafire\.com",
    r"mega\.nz",
    r"4shared\.com",
    r"zippyshare\.com",
    r"1drv\.ms",
    r"disk\.yandex\.[a-z]+",
    r"mega\.nz",
    r"bit\.ly",
    r"tinyurl\.com",
    r"cutt\.ly",
    r"shorturl\.at",
    r"s\.id",
    r"linktr\.ee",
    r"linktree\.[a-z.]+",
    r"t\.me",
    r"telegram\.me",
    r"instagram\.com",
    r"youtube\.com",
    r"youtu\.be",
    r"github\.com",
    r"raw\.githubusercontent\.com",
    r"pastebin\.com",
    r"gofile\.io",
    r"pixeldrain\.com",
    r"workupload\.com",
    r"file\.io",
    r"krakenfiles\.com",
    r"anonfiles\.[a-z]+",
    r"gdrive\.[a-z.]+",
    r"alightcreative\.com",
)

_URL_RE = re.compile(
    r"(?:(?:https?://)|(?:www\.))?"          # skema opsional
    r"(?:" + "|".join(_HOSTS) + r")"          # host yang dikenal
    r"(?:/[^\s<>\"'()\[\]]*)?"                # path opsional
    r"|"
    r"https?://[^\s<>\"'()\[\]]+",            # URL apa pun yang jelas
    re.IGNORECASE,
)

# Kata kunci yang menandakan konten terkait preset / proyek Alight Motion.
_PRESET_KEYWORDS = (
    "preset",
    "alight",
    "alight motion",
    "am ",
    "project",
    "projek",
    "proyek",
    "xml",
    ".am",
    "template",
    "motion",
    "edit",
    "template",
    "god",
    "aep",
    "capcut",
    "after effect",
)

# Frasa yang menandakan link tidak ada di tempat yang terlihat ("tersembunyi").
_INDIRECT_HINTS = (
    "link di bio",
    "link in bio",
    "di bio",
    "in bio",
    "cek bio",
    "check bio",
    "komentar pin",
    "komentar yang di pin",
    "komentar yang dipin",
    "pinned comment",
    "pin comment",
    "fix pin",
    "di pin",
    "dipin",
    "cek komen",
    "cek komentar",
    "cek deskripsi",
    "di deskripsi",
    "dm",
    "direct message",
    "wa ",
    "whatsapp",
    "komen",
)

# Ekstensi file yang menandakan proyek/preset.
_PRESET_EXT = re.compile(r"\.(xml|am|aep|zip|rar|7z|mp4|mov)$", re.IGNORECASE)


@dataclass
class LinkCandidate:
    """Satu kandidat link yang ditemukan pada sebuah sumber teks."""

    url: str
    source: str          # "description" | "comment" | "bio" | "pinned_comment"
    context: str         # teks asli di sekitar link
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    indirect: bool = False

    def add(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


def _normalize_url(raw: str) -> str:
    """Bersihkan URL dari tanda baca di ujung dan tambahkan skema bila kurang."""
    url = raw.strip().strip(".,;:!?)]}'\"")
    if not url:
        return url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    return url


def _has_preset_keyword(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _PRESET_KEYWORDS)


def _has_indirect_hint(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _INDIRECT_HINTS)


def extract_links(text: str, source: str) -> list[LinkCandidate]:
    """Ambil semua kandidat link dari satu potongan teks.

    Args:
        text: teks mentah (deskripsi komentar, bio, dsb).
        source: label sumber, mis. "description", "comment", "bio".

    Returns:
        Daftar :class:`LinkCandidate`.
    """
    if not text:
        return []

    out: list[LinkCandidate] = []
    seen: set[str] = set()

    for match in _URL_RE.finditer(text):
        raw = match.group(0)
        url = _normalize_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)

        # Ambil sedikit konteks di sekitar link untuk penilaian.
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 60)
        context = text[start:end].replace("\n", " ").strip()

        cand = LinkCandidate(url=url, source=source, context=context)
        _score(cand, text)
        out.append(cand)

    # Deteksi isyarat "tidak langsung" walau tanpa URL (mis. "link di bio").
    if not out and _has_indirect_hint(text) and _has_preset_keyword(text):
        out.append(
            LinkCandidate(
                url="",
                source=source,
                context=text.strip()[:200],
                indirect=True,
            )
        )
        out[-1].add(5, "menyebut preset tapi link tidak langsung terlihat")

    return out


def _score(cand: LinkCandidate, full_text: str) -> None:
    """Beri skor ke sebuah kandidat berdasarkan sinyal-sinyal yang ada."""
    low_url = cand.url.lower()
    low_ctx = cand.context.lower()

    # File sharing / preset langsung = paling bernilai.
    if re.search(
        r"drive\.google|docs\.google|dropbox|mediafire|mega\.nz|4shared|"
        r"yandex|gofile|pixeldrain|workupload|1drv|gdrive",
        low_url,
    ):
        cand.add(40, "penyimpanan file (kemungkinan besar isi preset)")
    if "alightcreative" in low_url or ".am" in low_url or ".xml" in low_url:
        cand.add(35, "referensi langsung ke Alight Motion")
    if _PRESET_EXT.search(low_url.split("?")[0]):
        cand.add(25, "berakhiran ekstensi file preset/proyek")
    if "github" in low_url or "pastebin" in low_url:
        cand.add(10, "kemungkinan berisi tautan/berkas preset")

    # Kata kunci preset di sekitar link.
    if _has_preset_keyword(cand.context):
        cand.add(15, "ada kata kunci preset di sekitar link")
    if _has_preset_keyword(full_text):
        cand.add(5, "teks sumber membahas preset")

    # Link pendek perlu ditelusuri (belum pasti isinya).
    if re.search(r"bit\.ly|tinyurl|cutt\.ly|shorturl|s\.id|linktr\.ee|t\.me|telegram\.me", low_url):
        cand.add(-5, "link pendek/agregator, isi belum dipastikan")

    # Sinyal "link disembunyikan".
    if _has_indirect_hint(cand.context):
        cand.indirect = True
        cand.add(-10, "diarahkan ke bio/komentar (link tidak langsung)")

    # Sumber komentar bawahan sedikit lebih rendah daripada deskripsi/pin.
    if cand.source == "comment":
        cand.add(0, "dari komentar")


def rank(candidates: Iterable[LinkCandidate]) -> list[LinkCandidate]:
    """Urutkan kandidat dari skor tertinggi, buang duplikat URL."""
    best: dict[str, LinkCandidate] = {}
    for c in candidates:
        key = c.url or ("INDIRECT::" + c.source + c.context[:40])
        prev = best.get(key)
        if prev is None or c.score > prev.score:
            best[key] = c
    return sorted(best.values(), key=lambda c: (c.score, not c.indirect), reverse=True)