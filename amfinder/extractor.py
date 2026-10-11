"""Ekstraksi tautan preset dari teks TikTok.

Modul ini adalah "otak" dari am-finder. Ia menerima teks mentah dari
deskripsi video, komentar, atau bio kreator, lalu mengembalikan daftar
kandidat tautan preset Alight Motion.

Fokus utama
-----------
Preset Alight Motion hampir selalu dibagikan lewat dua domain:

1. ``drive.google.com`` / ``docs.google.com`` — Google Drive (paling umum).
2. ``alightcreative.com`` — tautan resmi berbagi proyek Alight Motion.

Kedua domain ini diprioritaskan dan diletakkan paling atas pada hasil.
Tautan lain (MediaFire, Mega, link pendek, dsb.) tetap ditangkap, tetapi
diberi prioritas jauh lebih rendah.

Tantangan: tautan sering disamarkan atau tidak berupa URL utuh, misalnya
``drive.google.com/file/d/xxxx``, "link di bio", atau "cek komentar pin".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Tingkat prioritas (tier)
# ---------------------------------------------------------------------------

TIER_DRIVE = "drive"        # drive.google.com / docs.google.com
TIER_ALIGHT = "alight"      # alightcreative.com
TIER_OTHER = "other"        # domain lain (prioritas rendah)
TIER_HINT = "hint"          # tanpa URL, hanya petunjuk ("link di bio")

#: Urutan tier dari yang paling diprioritaskan.
TIER_ORDER = {TIER_DRIVE: 0, TIER_ALIGHT: 1, TIER_OTHER: 2, TIER_HINT: 3}

# ---------------------------------------------------------------------------
# Pola
# ---------------------------------------------------------------------------

# Domain yang menjadi fokus.
_DRIVE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:drive|docs)\.google\.com"
    r"(?:/[^\s<>\"'()\[\]]*)?",
    re.IGNORECASE,
)
_ALIGHT_RE = re.compile(
    r"(?:https?://)?(?:www\.)?alightcreative\.com"
    r"(?:/[^\s<>\"'()\[\]]*)?",
    re.IGNORECASE,
)

# Domain lain yang masih relevan (tapi prioritas rendah).
_OTHER_HOSTS = (
    r"mediafire\.com",
    r"mega\.nz",
    r"dropbox\.com",
    r"4shared\.com",
    r"gofile\.io",
    r"pixeldrain\.com",
    r"workupload\.com",
    r"1drv\.ms",
    r"disk\.yandex\.[a-z]+",
    r"bit\.ly",
    r"tinyurl\.com",
    r"cutt\.ly",
    r"s\.id",
    r"linktr\.ee",
    r"linktree\.[a-z.]+",
    r"t\.me",
    r"telegram\.me",
    r"github\.com",
    r"raw\.githubusercontent\.com",
    r"pastebin\.com",
)
_OTHER_BARE_RE = re.compile(
    r"(?:(?:https?://)|(?:www\.))?(?:" + "|".join(_OTHER_HOSTS) + r")"
    r"(?:/[^\s<>\"'()\[\]]*)?",
    re.IGNORECASE,
)
_ANY_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)

# ID berkas / folder Google Drive.
_DRIVE_FILE_ID = re.compile(r"(?:/file/d/|[?&]id=)([\w-]{10,})")
_DRIVE_FOLDER_ID = re.compile(r"/folders/([\w-]{10,})")

# Kata kunci yang menandakan konten terkait preset / proyek Alight Motion.
_PRESET_KEYWORDS = (
    "preset",
    "alight",
    "alight motion",
    "am",
    "project",
    "projek",
    "proyek",
    "xml",
    "template",
    "motion",
    "edit",
    "capcut",
    "after effect",
    "aep",
)

# Frasa yang menandakan tautan tidak tampak langsung ("tersembunyi").
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

# Ekstensi berkas proyek/preset.
_PRESET_EXT = re.compile(r"\.(xml|am|aep|zip|rar|7z)$", re.IGNORECASE)


@dataclass
class LinkCandidate:
    """Satu kandidat tautan yang ditemukan pada sebuah sumber teks."""

    url: str
    source: str          # "description" | "comment" | "bio" | "pinned_comment"
    tier: str = TIER_OTHER
    context: str = ""    # teks asli di sekitar tautan
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    indirect: bool = False

    def add(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


# ---------------------------------------------------------------------------
# Normalisasi
# ---------------------------------------------------------------------------

def _clean(raw: str) -> str:
    """Buang tanda baca di ujung dan tambahkan skema bila belum ada."""
    url = raw.strip().strip(".,;:!?)]}'\"")
    if not url:
        return url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    return url


def _normalize_drive(raw: str) -> str:
    """Ubah berbagai bentuk URL Google Drive jadi bentuk kanonik.

    - ``.../file/d/<id>/view``  -> tetap (dibersihkan)
    - ``.../open?id=<id>`` / ``.../uc?id=<id>`` -> ``/file/d/<id>/view``
    - ``.../folders/<id>``      -> tetap folder
    """
    url = _clean(raw)
    folder = _DRIVE_FOLDER_ID.search(url)
    if folder:
        return f"https://drive.google.com/drive/folders/{folder.group(1)}"
    file_id = _DRIVE_FILE_ID.search(url)
    if file_id:
        return f"https://drive.google.com/file/d/{file_id.group(1)}/view"
    return url


def _normalize_alight(raw: str) -> str:
    return _clean(raw)


def _has_preset_keyword(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _PRESET_KEYWORDS)


def _has_indirect_hint(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _INDIRECT_HINTS)


# ---------------------------------------------------------------------------
# Skoring per-tier
# ---------------------------------------------------------------------------

def _score_drive(cand: LinkCandidate) -> None:
    cand.add(70, "Google Drive — tempat berbagi preset paling umum")
    if _DRIVE_FILE_ID.search(cand.url) or _DRIVE_FOLDER_ID.search(cand.url):
        cand.add(10, "menunjuk berkas/folder spesifik")
    if _has_preset_keyword(cand.context):
        cand.add(10, "dikontekstual dengan preset")


def _score_alight(cand: LinkCandidate) -> None:
    cand.add(75, "Tautan resmi Alight Motion (alightcreative.com)")
    if re.search(r"/(share|project|preset|p|s)/", cand.url, re.IGNORECASE):
        cand.add(10, "menunjuk proyek/preset spesifik")
    if _has_preset_keyword(cand.context):
        cand.add(10, "dikontekstual dengan preset")


def _score_other(cand: LinkCandidate) -> None:
    low_url = cand.url.lower()
    if re.search(
        r"mediafire|mega\.nz|dropbox|4shared|gofile|pixeldrain|workupload|1drv|yandex",
        low_url,
    ):
        cand.add(25, "penyimpanan file lain (mungkin preset)")
    if "github" in low_url or "pastebin" in low_url:
        cand.add(10, "kemungkinan berisi tautan/berkas preset")
    if re.search(r"bit\.ly|tinyurl|cutt\.ly|s\.id|linktr\.ee|t\.me|telegram", low_url):
        cand.add(-5, "link pendek/agregator, isi belum dipastikan")
    if _PRESET_EXT.search(low_url.split("?")[0]):
        cand.add(15, "berakhiran ekstensi berkas preset")
    if _has_preset_keyword(cand.context):
        cand.add(5, "dikontekstual dengan preset")


# ---------------------------------------------------------------------------
# Ekstraksi
# ---------------------------------------------------------------------------

def _collect_matches(text: str) -> list[tuple[int, int, str, str, int]]:
    """Kumpulkan semua kecocokan tautan: (start, end, teks, tier, prioritas)."""
    found: list[tuple[int, int, str, str, int]] = []
    for rx, tier, priority in (
        (_DRIVE_RE, TIER_DRIVE, 0),
        (_ALIGHT_RE, TIER_ALIGHT, 0),
        (_OTHER_BARE_RE, TIER_OTHER, 1),
        (_ANY_URL_RE, TIER_OTHER, 2),
    ):
        for m in rx.finditer(text):
            found.append((m.start(), m.end(), m.group(0), tier, priority))
    # Utamakan posisi awal, lalu prioritas tier, lalu kecocokan terpanjang.
    found.sort(key=lambda t: (t[0], t[4], -(t[1] - t[0])))
    return found


def extract_links(text: str, source: str) -> list[LinkCandidate]:
    """Ambil semua kandidat tautan dari satu potongan teks.

    Args:
        text: teks mentah (deskripsi, komentar, bio, dsb.).
        source: label sumber, mis. "description", "comment", "bio".

    Returns:
        Daftar :class:`LinkCandidate`, sudah bertingkat (tier).
    """
    if not text:
        return []

    out: list[LinkCandidate] = []
    seen: set[str] = set()
    used: list[tuple[int, int]] = []

    for start, end, raw, tier, _prio in _collect_matches(text):
        # Lewati kecocokan yang tumpang-tindih dengan yang sudah diambil.
        if any(s < end and start < e for s, e in used):
            continue

        if tier == TIER_DRIVE:
            url = _normalize_drive(raw)
        elif tier == TIER_ALIGHT:
            url = _normalize_alight(raw)
        else:
            url = _clean(raw)

        if not url or url in seen:
            continue
        seen.add(url)
        used.append((start, end))

        ctx_start = max(0, start - 70)
        ctx_end = min(len(text), end + 70)
        context = text[ctx_start:ctx_end].replace("\n", " ").strip()

        cand = LinkCandidate(url=url, source=source, tier=tier, context=context)
        if tier == TIER_DRIVE:
            _score_drive(cand)
        elif tier == TIER_ALIGHT:
            _score_alight(cand)
        else:
            _score_other(cand)
        out.append(cand)

    # Petunjuk tanpa URL (mis. "link preset di bio") tetap dicatat.
    if not out and _has_indirect_hint(text) and _has_preset_keyword(text):
        hint = LinkCandidate(
            url="",
            source=source,
            tier=TIER_HINT,
            context=text.strip()[:200],
            indirect=True,
        )
        hint.add(5, "menyebut preset tapi tautan tidak tampak langsung")
        out.append(hint)

    return out


def rank(candidates: Iterable[LinkCandidate]) -> list[LinkCandidate]:
    """Urutkan kandidat: tier prioritas dulu, lalu skor, buang duplikat URL."""
    best: dict[str, LinkCandidate] = {}
    for c in candidates:
        key = c.url or ("HINT::" + c.source + c.context[:40])
        prev = best.get(key)
        if prev is None:
            best[key] = c
            continue
        # Pilih yang tier-nya lebih diprioritaskan, atau skornya lebih tinggi.
        if (TIER_ORDER[c.tier], -c.score) < (TIER_ORDER[prev.tier], -prev.score):
            best[key] = c
    return sorted(
        best.values(),
        key=lambda c: (TIER_ORDER[c.tier], -c.score, c.indirect),
    )


def is_priority_tier(tier: str) -> bool:
    """True bila tier termasuk yang diprioritaskan (Drive / Alight)."""
    return tier in (TIER_DRIVE, TIER_ALIGHT)