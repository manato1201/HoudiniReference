"""偽のフィード文字列による単体テスト(ネットワーク不要)。"""
import unittest
from datetime import datetime, timezone

from collector.feeds import FeedError, parse_date, parse_feed
from collector.items import normalize_entry
from collector.run import apply_retention, merge
from collector.tagging import auto_tags
from collector.textutil import EXCERPT_MAX, canonical_url, excerpt, safe_url, strip_html

NOW = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
SRC = {"id": "s", "name": "Src", "kind": "rss", "tab": "tips", "tags": ["T"]}

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>22.0.507: Fixes a bug</title><link>https://example.com/a?utm_source=x</link>
<description>&lt;p&gt;Fixes &lt;b&gt;VEX&lt;/b&gt; bug in Karma&lt;/p&gt;</description><pubDate>Tue, 17 Nov 2026 17:19:26 +0000</pubDate></item>
<item><title>No link</title></item>
<item><title>Bad scheme</title><link>javascript:alert(1)</link></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom entry</title>
<link href="https://example.com/t/1/" rel="alternate"/><published>2026-11-18T02:47:04+00:00</published>
<summary type="html">Hi!&lt;br&gt;&lt;br&gt;text</summary></entry></feed>"""

YT = """<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>XJt4t_ExMMA</yt:videoId><title>Vid</title><link rel="alternate" href="https://www.youtube.com/watch?v=XJt4t_ExMMA"/>
<published>2026-11-16T21:37:26+00:00</published><media:group><media:description>Desc &lt;script&gt;x&lt;/script&gt; here</media:description></media:group></entry></feed>"""


class ParseTests(unittest.TestCase):
    def test_rss_normalize(self):
        entries = parse_feed(RSS)
        self.assertEqual(len(entries), 3)
        it = normalize_entry(entries[0], SRC, NOW)
        self.assertEqual(it["published"], "2026-11-17T17:19:26Z")
        self.assertNotIn("<", it["excerpt"])
        self.assertEqual(it["excerpt"], "Fixes VEX bug in Karma")
        self.assertIn("VEX", it["tags"])
        self.assertIn("Karma", it["tags"])
        self.assertIn("H22.0", it["tags"])
        self.assertEqual(it["tags"][0], "T")

    def test_invalid_entries_dropped(self):
        entries = parse_feed(RSS)
        self.assertIsNone(normalize_entry(entries[1], SRC, NOW))  # URL 無し
        self.assertIsNone(normalize_entry(entries[2], SRC, NOW))  # javascript:

    def test_atom(self):
        it = normalize_entry(parse_feed(ATOM)[0], SRC, NOW)
        self.assertEqual(it["url"], "https://example.com/t/1/")
        self.assertEqual(it["excerpt"], "Hi! text")

    def test_youtube(self):
        src = dict(SRC, kind="youtube", name="Chan")
        it = normalize_entry(parse_feed(YT)[0], src, NOW)
        self.assertEqual(it["id"], "yt:XJt4t_ExMMA")
        self.assertEqual(it["url"], "https://www.youtube.com/watch?v=XJt4t_ExMMA")
        self.assertNotIn("script", it["excerpt"].lower())

    def test_broken_empty_huge_and_entity(self):
        for bad in ["<rss><channel><item>", "", "   ", "not xml at all", b""]:
            with self.assertRaises(FeedError):
                parse_feed(bad)
        with self.assertRaises(FeedError):
            parse_feed(b"<rss>" + b"a" * 2_100_000 + b"</rss>")
        bomb = '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel><item><title>&b;</title></item></channel></rss>'
        with self.assertRaises(FeedError):
            parse_feed(bomb)
        with self.assertRaises(FeedError):
            parse_feed("<html><body>hi</body></html>")

    def test_empty_channel(self):
        self.assertEqual(parse_feed('<rss version="2.0"><channel><title>x</title></channel></rss>'), [])


class TextTests(unittest.TestCase):
    def test_excerpt_limit(self):
        long = "あ" * 1000
        self.assertEqual(len(excerpt(long)), EXCERPT_MAX)
        self.assertTrue(excerpt(long).endswith("…"))
        self.assertEqual(excerpt("short"), "short")
        self.assertLessEqual(len(excerpt("<p>" + "x " * 5000 + "</p>")), EXCERPT_MAX)

    def test_html_stripped(self):
        s = strip_html('<div onclick="x()">A<script>alert(1)</script><style>p{}</style><b>B</b></div>&amp;&lt;i&gt;c')
        self.assertEqual(s, "AB &c")  # 二重エスケープのタグも除去
        self.assertNotIn("alert", s)
        self.assertEqual(strip_html(None), "")
        self.assertEqual(strip_html("a\x00b\x07c"), "abc")

    def test_urls(self):
        self.assertIsNone(safe_url("javascript:alert(1)"))
        self.assertIsNone(safe_url("data:text/html,x"))
        self.assertEqual(safe_url(" https://a.example/x "), "https://a.example/x")
        self.assertEqual(canonical_url("https://A.example/p?utm_source=x&id=1#f"), "https://a.example/p?id=1")

    def test_parse_date(self):
        self.assertEqual(parse_date("2026-11-18T02:47:04+09:00"), "2026-11-17T17:47:04Z")
        self.assertEqual(parse_date("2026-11-18T02:47:04Z"), "2026-11-18T02:47:04Z")
        self.assertIsNone(parse_date("garbage"))
        self.assertIsNone(parse_date(None))


class MergeTests(unittest.TestCase):
    def _it(self, i, url, pub="2026-11-17T00:00:00Z", sid="s", first="2026-11-01T00:00:00Z"):
        return {"id": i, "url": url, "published": pub, "source_id": sid, "first_seen": first, "tags": [], "title": "t", "excerpt": ""}

    def test_dedup_by_id_keeps_first_seen(self):
        old = [self._it("a", "u", first="2026-10-01T00:00:00Z")]
        new = [self._it("a", "u", first="2026-11-18T00:00:00Z"), self._it("b", "v")]
        out = merge(old, new)
        self.assertEqual(len(out), 2)
        a = next(i for i in out if i["id"] == "a")
        self.assertEqual(a["first_seen"], "2026-10-01T00:00:00Z")

    def test_feed_beats_api_for_same_video(self):
        old = [self._it("yt:X", "u", sid="youtube-sidefx")]
        out = merge(old, [self._it("yt:X", "u", sid="youtube-api")])
        self.assertEqual(out[0]["source_id"], "youtube-sidefx")

    def test_retention_and_cap(self):
        items = [self._it(f"i{n}", "u", pub=f"2026-11-{n:02d}T00:00:00Z") for n in range(1, 11)]
        out = apply_retention(items, NOW, {"s": 3})
        self.assertEqual([i["id"] for i in out], ["i10", "i9", "i8"])
        old_api = [self._it("yt:Z", "u", pub="2026-09-01T00:00:00Z", sid="youtube-api")]
        self.assertEqual(apply_retention(old_api, NOW, {}), [])


class TagTests(unittest.TestCase):
    def test_tags(self):
        t = auto_tags("Solaris and USD with Houdini 21.0 vellum", ["Base"])
        self.assertEqual(t[0], "Base")
        self.assertIn("Solaris", t)
        self.assertIn("Vellum", t)
        self.assertIn("H21.0", t)
        self.assertLessEqual(len(auto_tags("vex solaris karma apex kinefx vellum pyro flip rbd"), ), 6)
        self.assertEqual(auto_tags("nothing relevant here"), [])


if __name__ == "__main__":
    unittest.main()
