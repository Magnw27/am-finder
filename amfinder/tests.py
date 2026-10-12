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
from .tiktok import extract_video_id, normalize_tiktok_url, _clean_query


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


class TestQueryClean(unittest.TestCase):
    def test_strip_prefixes(self):
        self.assertEqual(_clean_query("@user"), "user")
        self.assertEqual(_clean_query("#hashtag"), "hashtag")
        self.assertEqual(_clean_query("  plain  "), "plain")

    def test_empty(self):
        self.assertEqual(_clean_query(""), "")
        self.assertEqual(_clean_query(None), "")


class TestCache(unittest.TestCase):
    def setUp(self):
        from . import cache
        cache.clear()

    def test_set_get_roundtrip(self):
        from . import cache
        cache.set("testns", "key-rt", {"a": 1})
        self.assertEqual(cache.get("testns", "key-rt"), {"a": 1})

    def test_missing(self):
        from . import cache
        self.assertIsNone(cache.get("testns", "tidak-ada-key"))

    def test_ttl_expiry(self):
        from . import cache
        cache.set("testns", "key-ttl", {"a": 1})
        self.assertIsNone(cache.get("testns", "key-ttl", ttl=-1))

    def test_get_or_set(self):
        from . import cache
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return {"v": calls["n"]}

        v1, c1 = cache.get_or_set("testns", "key-gos", producer)
        v2, c2 = cache.get_or_set("testns", "key-gos", producer)
        self.assertFalse(c1)
        self.assertTrue(c2)
        self.assertEqual(v1, v2)
        self.assertEqual(calls["n"], 1)


class TestApi(unittest.TestCase):
    def test_health(self):
        from . import api
        code, payload = api.health()
        self.assertEqual(code, 200)
        self.assertEqual(payload["status"], "ok")

    def test_find_requires_url(self):
        from . import api
        code, payload = api.handle_find({})
        self.assertEqual(code, 400)
        self.assertIn("url", payload["error"])

    def test_find_rejects_non_tiktok(self):
        from . import api
        code, _ = api.handle_find({"url": ["https://example.com/x"]})
        self.assertEqual(code, 400)

    def test_find_accepts_tiktok_shapes(self):
        from . import api
        self.assertTrue(api.TIKTOK_URL_RE.match("https://www.tiktok.com/@a/video/1"))
        self.assertTrue(api.TIKTOK_URL_RE.match("https://vt.tiktok.com/ZSx/"))
        self.assertTrue(api.TIKTOK_URL_RE.match("vt.tiktok.com/ZSx/"))
        self.assertFalse(api.TIKTOK_URL_RE.match("https://youtube.com/x"))

    def test_search_requires_q(self):
        from . import api
        code, _ = api.handle_search({})
        self.assertEqual(code, 400)

    def test_search_kind_normalized(self):
        # Pastikan kind aneh tidak error sebelum menyentuh jaringan: kita monkeypatch.
        from . import api, finder
        captured = {}

        class FakeScan:
            def to_dict(self):
                return {}

        def fake_search(q, kind="hashtag", limit=6, comment_limit=50, per_video_cache=True):
            captured["kind"] = kind
            return FakeScan()

        original = finder.search
        finder.search = fake_search
        try:
            code, _ = api.handle_search({"q": ["x"], "kind": ["aneh"]})
        finally:
            finder.search = original
        self.assertEqual(code, 200)
        self.assertEqual(captured["kind"], "hashtag")


class TestServerRateLimit(unittest.TestCase):
    def test_limiter_blocks_after_max(self):
        from .server import RateLimiter
        rl = RateLimiter(max_requests=3, window_seconds=60)
        self.assertTrue(rl.allow("ip1"))
        self.assertTrue(rl.allow("ip1"))
        self.assertTrue(rl.allow("ip1"))
        self.assertFalse(rl.allow("ip1"))
        self.assertTrue(rl.allow("ip2"))  # IP lain tidak terpengaruh


if __name__ == "__main__":
    unittest.main()