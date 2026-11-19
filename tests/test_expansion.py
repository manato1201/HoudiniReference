"""情報源の拡張(日本語フィード・GitHub リリース API・題名の重複除去・言語・ホストの交互取得)。偽のフィード/偽サーバーだけで、ネットワーク不要。"""
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collector.feeds import parse_feed
from collector.github import fetch_github_releases, github_sources
from collector.httpclient import FetchError, Fetcher
from collector.items import fetch_feed_source, normalize_entry
from collector.run import dedupe_titles, interleave_by_host, run
from collector.tagging import auto_tags
from collector.textutil import detect_lang, title_key

from .fakeserver import FakeServer

NOW = datetime(2026, 11, 19, 3, 0, tzinfo=timezone.utc)


def fetcher():
    return Fetcher({}, allow_local_http=True, host_delays={}, default_delay=0)


def gh_src(base, repo="o/r", **kw):
    cfg = {"api_base": base, "repos": [dict({"repo": repo, "label": "Tool", "limit": 5}, **kw)]}
    return github_sources(cfg)[0]


def release(tag, name=None, pre=False, draft=False, url=None, pub="2026-11-18T05:00:00Z", repo="o/r", body="LONG BODY TEXT"):
    return {"tag_name": tag, "name": name if name is not None else tag, "prerelease": pre, "draft": draft, "body": body,
            "published_at": pub, "html_url": url or f"https://github.com/{repo}/releases/tag/{tag}"}


QIITA = """<?xml version="1.0" encoding="UTF-8"?>
<feed xml:lang="ja-JP" xmlns="http://www.w3.org/2005/Atom"><title>HOUDINIタグ</title>
<entry><id>tag:qiita.com,2005:PublicArticle/1</id><published>2026-11-18T06:57:14+09:00</published>
<link rel="alternate" type="text/html" href="https://qiita.com/u/items/abc"/>
<title>[Houdini] VEXのWrangleで流体シミュレーション</title><content type="html">&lt;h1&gt;はじめに&lt;/h1&gt;&lt;p&gt;本文&lt;/p&gt;</content></entry></feed>"""

ZENN = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<title><![CDATA[Zennの「Houdini」のフィード]]></title>
<item><title><![CDATA[【Houdini】Copernicusの基本]]></title><link>https://zenn.dev/u/articles/xyz</link>
<description><![CDATA[調べたこと <b>COP</b> の使い方]]></description><pubDate>Mon, 25 May 2026 23:20:43 GMT</pubDate></item></channel></rss>"""


class LangAndTagTests(unittest.TestCase):
    def test_detect_lang(self):
        self.assertEqual(detect_lang("VEXの使い方"), "ja")
        self.assertEqual(detect_lang("ハイトフィールド"), "ja")
        self.assertEqual(detect_lang("How to use VEX"), "en")
        self.assertEqual(detect_lang(""), "en")
        self.assertEqual(detect_lang(None), "en")

    def test_title_key_ignores_case_and_symbols(self):
        self.assertEqual(title_key("Houdini 22 — Update!"), title_key("houdini 22 update"))
        self.assertEqual(title_key("【Houdini】基本"), title_key("Houdini 基本"))
        self.assertEqual(title_key(None), "")

    def test_japanese_vocabulary_tags(self):
        self.assertIn("VEX", auto_tags("VEXの使い方"))  # 日本語が続いても境界が働く
        t = auto_tags("流体シミュレーションとコペルニクス")
        for tag in ("FLIP", "Simulation", "Copernicus"):
            self.assertIn(tag, t)
        self.assertIn("H22.0", auto_tags("Houdini22.0の新機能"))
        self.assertIn("RBD", auto_tags("破壊エフェクト"))
        self.assertEqual(auto_tags("firefox ubiquitous"), [])  # 英語の部分一致は増やしていない


class JapaneseFeedTests(unittest.TestCase):
    def test_qiita_atom(self):
        src = {"id": "q", "name": "Qiita", "kind": "rss", "tab": "tips", "tags": ["Qiita"], "lang": "ja"}
        it = normalize_entry(parse_feed(QIITA)[0], src, NOW)
        self.assertEqual(it["published"], "2026-11-17T21:57:14Z")
        self.assertEqual(it["lang"], "ja")
        self.assertEqual(it["excerpt"], "はじめに 本文")
        self.assertIn("VEX", it["tags"])
        self.assertEqual(it["tags"][0], "Qiita")

    def test_zenn_rss_cdata(self):
        src = {"id": "z", "name": "Zenn", "kind": "rss", "tab": "tips", "tags": ["Zenn"]}
        it = normalize_entry(parse_feed(ZENN)[0], src, NOW)
        self.assertEqual(it["title"], "【Houdini】Copernicusの基本")
        self.assertNotIn("<", it["excerpt"])
        self.assertEqual(it["lang"], "ja")  # 設定が無くても判定
        self.assertIn("Copernicus", it["tags"])

    def test_lang_from_config_wins_and_defaults_to_detection(self):
        raw = {"title": "English title", "url": "https://e.example/a", "summary": ""}
        self.assertEqual(normalize_entry(raw, {"id": "s", "name": "S", "kind": "rss", "lang": "ja"}, NOW)["lang"], "ja")
        self.assertEqual(normalize_entry(raw, {"id": "s", "name": "S", "kind": "rss"}, NOW)["lang"], "en")
        self.assertEqual(normalize_entry(raw, {"id": "s", "name": "S", "kind": "rss", "lang": "xx"}, NOW)["lang"], "en")

    def test_post_feed_same_title_collapsed_and_limit(self):
        entries = "".join(
            f'<entry><title>{"Topic A" if n < 3 else "Topic " + str(n)}</title><link href="https://f.example/post/{n}/" rel="alternate"/>'
            f"<updated>2026-11-18T0{n % 10}:00:00+00:00</updated></entry>" for n in range(30)
        )
        feed = f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'
        with FakeServer() as s:
            s.routes["/f"] = (200, feed, {})
            base = {"id": "f", "name": "F", "kind": "rss", "url": s.base + "/f", "limit": 15}
            plain, _ = fetch_feed_source(fetcher(), base, NOW)
            self.assertEqual(len(plain), 15)  # 上限
            dedup, _ = fetch_feed_source(fetcher(), dict(base, dedupe_title=True), NOW)
            self.assertEqual(len(dedup), 13)  # Topic A の 3 件が 1 件に
            self.assertEqual(sum(1 for i in dedup if i["title"] == "Topic A"), 1)


class GithubTests(unittest.TestCase):
    def test_releases_mapped_without_body(self):
        data = [release("22.0.508", pre=True), release("v4.0.3", "Version 4.0.3 - Houdini 22.0.466", repo="o/r"),
                release("draft1", draft=True)]
        with FakeServer() as s:
            s.routes["/repos/o/r/releases"] = (200, data, {})
            src = gh_src(s.base, tags=["Labs"])
            items, nm = fetch_github_releases(fetcher(), src, NOW)
            req = s.requests[0]
            self.assertEqual(req["headers"]["Accept"], "application/vnd.github+json")
            self.assertNotIn("Authorization", req["headers"])
            self.assertEqual(req["query"]["per_page"], ["5"])
        self.assertFalse(nm)
        self.assertEqual(len(items), 2)  # draft は捨てる
        a, b = items
        self.assertEqual(a["title"], "Tool: 22.0.508")
        self.assertEqual(a["kind"], "github")
        self.assertEqual(a["lang"], "en")
        self.assertEqual(a["excerpt"], "")  # 本文は保存しない
        self.assertNotIn("LONG BODY", json.dumps(items))
        self.assertIn("Pre-release", a["tags"])
        self.assertIn("H22.0", a["tags"])
        self.assertEqual(a["tags"][:2], ["GitHub", "Release notes"])
        self.assertEqual(a["published"], "2026-11-18T05:00:00Z")
        self.assertEqual(a["tab"], "reference")
        self.assertEqual(a["source"], "Tool")
        self.assertTrue(b["title"].startswith("Tool: Version 4.0.3"))
        self.assertNotEqual(a["id"], b["id"])

    def test_label_not_duplicated_in_title(self):
        with FakeServer() as s:
            s.routes["/repos/o/r/releases"] = (200, [release("v1", "Tool v1")], {})
            items, _ = fetch_github_releases(fetcher(), gh_src(s.base), NOW)
        self.assertEqual(items[0]["title"], "Tool v1")

    def test_limit_and_foreign_or_unsafe_urls_dropped(self):
        data = [release(f"1.{n}") for n in range(10)]
        data[0]["html_url"] = "https://evil.example/o/r/releases/tag/x"
        data[1]["html_url"] = "javascript:alert(1)"
        data[2]["html_url"] = None
        with FakeServer() as s:
            s.routes["/repos/o/r/releases"] = (200, data, {})
            items, _ = fetch_github_releases(fetcher(), gh_src(s.base), NOW)  # limit 5
        self.assertEqual([i["url"].rsplit("/", 1)[1] for i in items], ["1.3", "1.4"])

    def test_empty_and_malformed(self):
        with FakeServer() as s:
            s.routes["/repos/o/r/releases"] = (200, [], {})
            self.assertEqual(fetch_github_releases(fetcher(), gh_src(s.base), NOW), ([], False))
            for body in ("{bad", {"message": "x"}, '"str"'):
                s.routes["/repos/o/r/releases"] = (200, body, {})
                with self.assertRaises(FetchError):
                    fetch_github_releases(fetcher(), gh_src(s.base), NOW)
            s.routes["/repos/o/r/releases"] = (200, [release("a", None, body=None), {"x": 1}, "str", release("")], {})
            items, _ = fetch_github_releases(fetcher(), gh_src(s.base), NOW)
            self.assertEqual(len(items), 1)

    def test_rate_limit_and_not_found_are_fetch_errors_without_query(self):
        with FakeServer() as s:
            src = gh_src(s.base)
            s.routes["/repos/o/r/releases"] = (403, {"message": "API rate limit exceeded"}, {})
            with self.assertRaises(FetchError) as cm:
                fetch_github_releases(fetcher(), src, NOW)
            self.assertIn("HTTP 403", str(cm.exception))
            self.assertIn("rate limited", str(cm.exception))
            self.assertNotIn("per_page", str(cm.exception))
            s.routes["/repos/o/r/releases"] = (404, {"message": "Not Found"}, {})
            with self.assertRaises(FetchError):
                fetch_github_releases(fetcher(), src, NOW)

    def test_etag_second_request_is_304(self):
        with FakeServer() as s:
            s.routes["/repos/o/r/releases"] = (200, [release("a")], {"ETag": '"e1"'})
            f = fetcher()
            src = gh_src(s.base)
            self.assertEqual(len(fetch_github_releases(f, src, NOW)[0]), 1)
            self.assertEqual(fetch_github_releases(f, src, NOW), ([], True))

    def test_sources_config_validation(self):
        cfg = {"repos": [{"repo": "sideeffects/SideFXLabs", "label": "SideFX Labs", "tags": ["Labs"]}, {"repo": "../etc/passwd"},
                         {"repo": "no-slash"}, {"repo": "a/b?x=1"}, {"repo": "../x"}, {"repo": "a/.."}, {"repo": 5}, {"repo": "a/b", "enabled": False}, "junk", {"repo": "o/r.js"}]}
        out = github_sources(cfg)
        self.assertEqual([s["repo"] for s in out], ["sideeffects/SideFXLabs", "o/r.js"])
        self.assertTrue(out[0]["url"].startswith("https://api.github.com/repos/sideeffects/SideFXLabs/releases?per_page="))
        self.assertEqual(out[0]["id"], "github-sideeffects-sidefxlabs")
        self.assertEqual(github_sources({"repos": "x"}), [])
        self.assertEqual(github_sources({}), [])
        big = github_sources({"repos": [{"repo": "a/b", "limit": 999}]})[0]
        self.assertIn("per_page=30", big["url"])  # 1 回の取得は最大 30 件


class DedupeAndOrderTests(unittest.TestCase):
    def _it(self, i, title, sid, pub="2026-11-10T00:00:00Z", kind="rss"):
        return {"id": i, "title": title, "source_id": sid, "published": pub, "kind": kind}

    def test_cross_source_same_title_keeps_earlier_source(self):
        items = [self._it("1", "Houdini 22 is out!", "topics"), self._it("2", "houdini 22 is out", "forum-x"),
                 self._it("3", "Different title here", "forum-x")]
        out = dedupe_titles(items, {"topics": 1, "forum-x": 5})
        self.assertEqual(sorted(i["id"] for i in out), ["1", "3"])

    def test_same_source_keeps_newest(self):
        items = [self._it("old", "Same topic title", "f", pub="2026-11-01T00:00:00Z"), self._it("new", "Same topic title", "f", pub="2026-11-09T00:00:00Z")]
        self.assertEqual([i["id"] for i in dedupe_titles(items, {"f": 1})], ["new"])

    def test_not_applied_to_youtube_github_x_or_short_titles(self):
        items = [self._it("y1", "Houdini tutorial", "a", kind="youtube"), self._it("y2", "Houdini tutorial", "b", kind="youtube"),
                 self._it("g1", "Tool: 1.0", "a", kind="github"), self._it("g2", "Tool: 1.0", "b", kind="github"),
                 self._it("s1", "FAQ", "a"), self._it("s2", "FAQ", "b")]
        self.assertEqual(len(dedupe_titles(items, {})), 6)

    def test_interleave_by_host_keeps_per_host_order(self):
        def S(i, h):
            return {"id": i, "url": f"https://{h}/{i}"}
        out = interleave_by_host([S("s1", "sidefx.com"), S("s2", "sidefx.com"), S("s3", "sidefx.com"), S("y1", "yt.com"), S("y2", "yt.com"), S("g1", "gh.com")])
        self.assertEqual([s["id"] for s in out], ["s1", "y1", "g1", "s2", "y2", "s3"])
        self.assertEqual(interleave_by_host([]), [])


FEED_A = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Shared Topic Title</title><link href="https://a.example/topic/1/" rel="alternate"/>
<updated>2026-11-18T00:00:00+00:00</updated><summary>VEXの話</summary></entry>
<entry><title>Only in A</title><link href="https://a.example/topic/2/" rel="alternate"/><updated>2026-11-17T00:00:00+00:00</updated></entry></feed>"""
FEED_B = """<rss version="2.0"><channel><item><title>Shared topic title</title><link>https://b.example/post/9</link>
<pubDate>Wed, 18 Nov 2026 01:00:00 +0000</pubDate></item></channel></rss>"""


class RunIntegrationTests(unittest.TestCase):
    def setup_dir(self, s, github_status=200):
        d = Path(tempfile.mkdtemp())
        (d / "sources.json").write_text(json.dumps({"sources": [
            {"id": "a", "name": "A", "url": s.base + "/a.xml", "tab": "tips"},
            {"id": "b", "name": "B", "url": s.base + "/b.xml", "tab": "tips", "lang": "ja"},
        ]}))
        (d / "sources.youtube.json").write_text(json.dumps({"channels": []}))
        (d / "sources.x.json").write_text(json.dumps({"enabled": False}))
        (d / "sources.github.json").write_text(json.dumps({"api_base": s.base, "repos": [
            {"repo": "o/r", "label": "Tool", "limit": 3}, {"repo": "o/gone", "label": "Gone"}]}))
        s.routes["/a.xml"] = (200, FEED_A, {})
        s.routes["/b.xml"] = (200, FEED_B, {})
        s.routes["/repos/o/r/releases"] = (github_status, [release(f"1.{n}") for n in range(8)] if github_status == 200 else {"message": "rate"}, {})
        s.routes["/repos/o/gone/releases"] = (404, {"message": "Not Found"}, {})
        return d

    def run_it(self, d):
        out = io.StringIO()
        code = run(d, d / "site", env={}, now=NOW, allow_local_http=True, host_delays={}, default_delay=0, out=out)
        return code, json.loads((d / "items.json").read_text(encoding="utf-8"))

    def test_full_run_dedupes_tags_languages_and_survives_failures(self):
        with FakeServer() as s:
            d = self.setup_dir(s)
            code, doc = self.run_it(d)
            self.assertEqual(code, 0)
            titles = [i["title"].lower() for i in doc["items"]]
            self.assertEqual(titles.count("shared topic title"), 1)  # 別の情報源から来た同じ題名は 1 件
            kept = next(i for i in doc["items"] if i["title"].lower() == "shared topic title")
            self.assertEqual(kept["source_id"], "a")  # 設定の並びが先
            gh = [i for i in doc["items"] if i["kind"] == "github"]
            self.assertEqual(len(gh), 3)  # limit
            self.assertTrue(all(i["lang"] == "en" and "GitHub" in i["tags"] for i in gh))
            self.assertTrue(all(i["lang"] in ("ja", "en") for i in doc["items"]))
            self.assertEqual(next(i for i in doc["items"] if i["id"] and i["title"] == "Only in A")["lang"], "en")
            st = [x["id"] for x in doc["sources"]]
            self.assertEqual(st, ["a", "b", "github-o-r", "github-o-gone", "x"])  # 設定の並び順
            bad = next(x for x in doc["sources"] if x["id"] == "github-o-gone")
            self.assertFalse(bad["ok"])
            self.assertIn("HTTP 404", bad["error"])
            second_code, doc2 = self.run_it(d)  # 2 回目(重複しない)
            self.assertEqual(len(doc2["items"]), len(doc["items"]))

    def test_old_items_get_lang_backfilled(self):
        with FakeServer() as s:
            d = self.setup_dir(s)
            (d / "items.json").write_text(json.dumps({"items": [
                {"id": "old1", "tab": "tips", "kind": "rss", "source_id": "gone", "source": "G", "title": "古い記事", "url": "https://e.example/1",
                 "published": "2026-11-01T00:00:00Z", "excerpt": "", "tags": [], "first_seen": "2026-11-01T00:00:00Z"}]}))
            _, doc = self.run_it(d)
            self.assertEqual(next(i for i in doc["items"] if i["id"] == "old1")["lang"], "ja")

    def test_github_rate_limited_other_sources_continue(self):
        with FakeServer() as s:
            d = self.setup_dir(s, github_status=403)
            code, doc = self.run_it(d)
            self.assertEqual(code, 0)
            st = {x["id"]: x for x in doc["sources"]}
            self.assertFalse(st["github-o-r"]["ok"])
            self.assertIn("rate limited", st["github-o-r"]["error"])
            self.assertTrue(st["a"]["ok"])
            self.assertTrue(any(i["source_id"] == "a" for i in doc["items"]))


if __name__ == "__main__":
    unittest.main()
