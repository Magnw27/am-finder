"""Uji untuk amfinder tanpa dependensi eksternal.

Jalankan:
    python3 -m amfinder.tests
    python3 -m unittest amfinder.tests -v
"""

from __future__ import annotations

import unittest

from .extractor import (
    TIER_ALIGHT,
    TIER_DRIVE,
    TIER_HINT,
    TIER_OTHER,
    extract_links,
    rank,
)
from .tiktok import extract_video_id, normalize_tiktok_url


class TestDriveExtraction(unittest.TestCase):
    def test_drive_full_url(self):
        cands = extract_links(
            "preset download di https://drive.google.com/file/d/1AbCxyz12345/view",
            "description",
        )
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].tier, TIER_DRIVE)
        self.assertGreaterEqual(cands[0].score, 70)

    def test_drive_bare_domain(self):
        cands = extract_links("drive.google.com/file/d/1AbCxyz12345/view", "comment")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].tier, TIER_DRIVE)
        self.assertTrue(cands[0].url.startswith("https://drive.google.com"))

    def test_drive_open_id_normalized(self):
        cands = extract_links(
            "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQ", "description"
        )
        self.assertEqual(cands[0].url, "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQ/view")

    def test_drive_folder(self):
        cands = extract_links(
            "https://drive.google.com/drive/folders/1A2b3C4d5E6f7G8h9I", "bio"
        )
        self.assertEqual(cands[0].tier, TIER_DRIVE)
        self.assertIn("/folders/", cands[0].url)

    def test_docs_google(self):
        cands = extract_links("docs.google.com/document/d/abc123", "comment")
        self.assertEqual(cands[0].tier, TIER_DRIVE)


class TestAlightExtraction(unittest.TestCase):
    def test_alight_share_link(self):
        cands = extract_links(
            "projeknya di https://alightcreative.com/share/abc123", "description"
        )
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].tier, TIER_ALIGHT)
        self.assertGreaterEqual(cands[0].score, 75)

    def test_alight_bare(self):
        cands = extract_links("alightcreative.com/p/xyz", "comment")
        self.assertEqual(cands[0].tier, TIER_ALIGHT)


class TestOtherAndHints(unittest.TestCase):
    def test_other_host_low_priority(self):
        cands = extract_links("mediafire.com/file/abc/preset_am.zip", "comment")
        self.assertEqual(cands[0].tier, TIER_OTHER)

    def test_indirect_hint_bio(self):
        cands = extract_links("link preset di bio ya gais", "description")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].tier, TIER_HINT)
        self.assertTrue(cands[0].indirect)

    def test_no_link_plain_comment(self):
        self.assertEqual(extract_links("keren banget editnya 🔥", "comment"), [])

    def test_mixed_sources(self):
        text = "drive.google.com/file/d/A1234567890 dan mediafire.com/file/preset.zip"
        cands = extract_links(text, "description")
        tiers = {c.tier for c in cands}
        self.assertIn(TIER_DRIVE, tiers)
        self.assertIn(TIER_OTHER, tiers)


class TestRanking(unittest.TestCase):
    def test_drive_beats_other(self):
        cands = (
            extract_links("mediafire.com/file/preset.zip", "comment")
            + extract_links("drive.google.com/file/d/1GoodOne0000/view", "comment")
        )
        ranked = rank(cands)
        self.assertEqual(ranked[0].tier, TIER_DRIVE)

    def test_alight_and_drive_top(self):
        cands = (
            extract_links("bit.ly/abcd", "comment")
            + extract_links("alightcreative.com/share/x", "description")
            + extract_links("drive.google.com/file/d/1Xyz0000000/view", "comment")
        )
        ranked = rank(cands)
        self.assertEqual(ranked[-1].tier, TIER_OTHER)
        self.assertTrue(all(r.tier in (TIER_DRIVE, TIER_ALIGHT) for r in ranked[:2]))

    def test_dedup(self):
        text = "drive.google.com/file/d/1SameId0000/view dan drive.google.com/file/d/1SameId0000/view"
        self.assertEqual(len(rank(extract_links(text, "description"))), 1)


class TestUrlNormalize(unittest.TestCase):
    def test_full_url(self):
        u = normalize_tiktok_url("https://www.tiktok.com/@user/video/123456789?is_from_webapp=1")
        self.assertEqual(u, "https://www.tiktok.com/@user/video/123456789")

    def test_missing_scheme(self):
        u = normalize_tiktok_url("tiktok.com/@user/video/987")
        self.assertTrue(u.startswith("https://"))
        self.assertIn("/video/987", u)

    def test_short_link_preserved(self):
        self.assertIn("vt.tiktok.com", normalize_tiktok_url("https://vt.tiktok.com/ZSabc/"))

    def test_extract_video_id(self):
        self.assertEqual(extract_video_id("https://www.tiktok.com/@a/video/555"), "555")
        self.assertEqual(extract_video_id("https://vt.tiktok.com/ZSx/"), "")


if __name__ == "__main__":
    unittest.main()