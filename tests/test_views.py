"""YouTube フィードの再生数(media:statistics の views)の解析。ネットワーク不要。"""
import unittest
from datetime import datetime, timezone

from collector.feeds import parse_feed
from collector.items import normalize_entry

NOW = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
SRC = {"id": "s", "name": "Chan", "kind": "youtube", "tab": "tips", "tags": ["YouTube"]}

HEAD = ('<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" '
        'xmlns="http://www.w3.org/2005/Atom">')


def entry(vid, stats_xml):
    return (f'<entry><yt:videoId>{vid}</yt:videoId><title>Vid {vid}</title>'
            f'<link rel="alternate" href="https://www.youtube.com/watch?v={vid}"/>'
            f'<published>2026-11-16T21:37:26+00:00</published>'
            f'<media:group><media:description>d</media:description>{stats_xml}</media:group></entry>')


def feed(*entries):
    return HEAD + "".join(entries) + "</feed>"


class ViewsTests(unittest.TestCase):
    def views_of(self, stats_xml):
        raw = parse_feed(feed(entry("XJt4t_ExMMA", stats_xml)))[0]
        return raw, normalize_entry(raw, SRC, NOW)

    def test_views_parsed(self):
        raw, it = self.views_of('<media:community><media:starRating count="5" average="5.0" min="1" max="5"/>'
                                '<media:statistics views="12345"/></media:community>')
        self.assertEqual(raw["views"], 12345)
        self.assertEqual(it["views"], 12345)

    def test_views_missing_is_none(self):
        raw, it = self.views_of("")
        self.assertIsNone(raw["views"])
        self.assertNotIn("views", it)  # 無いものは項目に出さない(省略)

    def test_statistics_without_attribute_is_none(self):
        raw, it = self.views_of('<media:community><media:statistics/></media:community>')
        self.assertIsNone(raw["views"])
        self.assertNotIn("views", it)

    def test_non_numeric_views_is_none(self):
        for bad in ("abc", "12x", "-5", "1.5", "", "1e3", "０１２"):
            raw, it = self.views_of(f'<media:community><media:statistics views="{bad}"/></media:community>')
            self.assertIsNone(raw["views"], bad)
            self.assertNotIn("views", it, bad)

    def test_zero_views_kept(self):
        raw, it = self.views_of('<media:community><media:statistics views="0"/></media:community>')
        self.assertEqual(it["views"], 0)

    def test_absurd_views_rejected(self):
        raw, it = self.views_of('<media:community><media:statistics views="99999999999999999999"/></media:community>')
        self.assertIsNone(raw["views"])

    def test_non_youtube_has_no_views(self):
        rss = ('<rss version="2.0"><channel><item><title>T title here</title><link>https://example.com/a</link>'
               '<pubDate>Tue, 17 Nov 2026 17:19:26 +0000</pubDate></item></channel></rss>')
        it = normalize_entry(parse_feed(rss)[0], dict(SRC, kind="rss"), NOW)
        self.assertNotIn("views", it)

    def test_merge_keeps_old_views_when_new_has_none_and_updates_when_present(self):
        from collector.run import merge
        base = {"id": "yt:a", "source_id": "s", "first_seen": "2026-11-01T00:00:00Z", "published": "2026-11-01T00:00:00Z"}
        out = merge([dict(base, views=10)], [dict(base)])
        self.assertEqual(out[0]["views"], 10)
        out = merge([dict(base, views=10)], [dict(base, views=99)])
        self.assertEqual(out[0]["views"], 99)


if __name__ == "__main__":
    unittest.main()
