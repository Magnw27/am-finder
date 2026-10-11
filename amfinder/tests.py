"""Uji untuk amfinder tanpa dependensi eksternal.

Jalankan:
    python3 -m amfinder.tests
    python3 -m unittest amfinder.tests -v
"""

from __future__ import annotations

import unittest

from .extractor import extract_links, rank
from .tiktok import extract_video_id, normalize_tiktok_url


class TestExtractor(unittest.TestCase):
    def test_full_google_drive_url(self):
        cands = extract_links(
            "preset alight motion download di https://drive.google.com/file/d/1AbC/view",
            "description",
        )
        self.assertEqual(len(cands), 1)
        self.assertIn("drive.google.com", cands[0].url)
        self.assertGreaterEqual(cands[0].score, 40)
        self.assertFalse(cands[0].indirect)

    def test_bare_domain_gets_scheme(self):
        cands = extract_links("mediafire.com/file/abc/preset_am.zip", "comment")
        self.assertEqual(len(cands), 1)
        self.assertTrue(cands[0].url.startswith("https://mediafire.com"))
        self.assertTrue(cands[0].reasons)

    def test_indirect_hint_bio(self):
        cands = extract_links("link preset di bio ya gais", "description")
        self.assertEqual(len(cands), 1)
        self.assertTrue(cands[0].indirect)
        self.assertEqual(cands[0].url, "")

    def test_indirect_hint_pinned(self):
        cands = extract_links("cek komentar yang di pin buat link preset AM", "comment")
        self.assertEqual(len(cands), 1)
        self.assertTrue(cands[0].indirect)

    def test_no_link_plain_comment(self):
        cands = extract_links("keren banget editnya 🔥", "comment")
        self.assertEqual(cands, [])

    def test_multiple_links(self):
        text = "drive.google.com/file/d/A dan mediafire.com/file/preset.zip"
        cands = extract_links(text, "description")
        self.assertEqual(len(cands), 2)

    def test_rank_orders_by_score(self):
        cands = (
            extract_links("drive.google.com/file/d/xyz preset", "description")
            + extract_links("bit.ly/abcd", "comment")
        )
        ranked = rank(cands)
        self.assertGreater(ranked[0].score, ranked[-1].score)


class TestUrlNormalize(unittest.TestCase):
    def test_full_url(self):
        u = normalize_tiktok_url("https://www.tiktok.com/@user/video/123456789?is_from_webapp=1")
        self.assertEqual(u, "https://www.tiktok.com/@user/video/123456789")

    def test_missing_scheme(self):
        u = normalize_tiktok_url("tiktok.com/@user/video/987")
        self.assertTrue(u.startswith("https://"))
        self.assertIn("/video/987", u)

    def test_short_link_preserved(self):
        u = normalize_tiktok_url("https://vt.tiktok.com/ZSabc/")
        self.assertIn("vt.tiktok.com", u)

    def test_extract_video_id(self):
        self.assertEqual(extract_video_id("https://www.tiktok.com/@a/video/555"), "555")
        self.assertEqual(extract_video_id("https://vt.tiktok.com/ZSx/"), "")


if __name__ == "__main__":
    unittest.main()