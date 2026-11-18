"""X API・YouTube API・収集全体を、偽サーバーで検証する。実際の X / YouTube API は呼ばない。"""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.httpclient import Fetcher
from collector.items import iso
from collector.run import run
from collector.xapi import XCollector

from .fakeserver import FakeServer

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)
TOKEN = "TESTTOKEN_abcdef123456"


def fetcher():
    return Fetcher({}, secrets=[TOKEN], allow_local_http=True, host_delays={}, default_delay=0)


def cfg(base, **kw):
    c = {"enabled": True, "api_base": base + "/2", "accounts": [{"handle": "sidefx", "tab": "news"}], "queries": []}
    c.update(kw)
    return c


def tweets(ids, user="sidefx", text="Houdini 22 news <b>x</b>"):
    return {
        "data": [{"id": str(i), "text": text, "created_at": "2026-11-17T10:00:00.000Z", "author_id": "u1"} for i in ids],
        "includes": {"users": [{"id": "u1", "username": user}]},
    }


def stored(pid, days_old=1, text="old"):
    return {"id": f"x:{pid}", "kind": "x", "source_id": "x", "source": "X", "tab": "news", "title": text, "excerpt": text,
            "url": f"https://x.com/sidefx/status/{pid}", "published": iso(NOW - timedelta(days=days_old)), "tags": [],
            "first_seen": iso(NOW), "handle": "sidefx"}


class XTests(unittest.TestCase):
    def test_disabled_and_no_token_do_nothing(self):
        with FakeServer() as s:
            r = XCollector(cfg(s.base, enabled=False), TOKEN, fetcher(), {}, NOW).run([])
            self.assertEqual(r.status["skipped"], "disabled")
            r = XCollector(cfg(s.base), None, fetcher(), {}, NOW).run([stored(1)])
            self.assertIn("no X_BEARER_TOKEN", r.status["skipped"])
            self.assertIsNone(r.status["ok"])  # エラーではない
            self.assertEqual(r.removed_ids, set())
            self.assertEqual(s.requests, [])

    def test_search_sends_bearer_and_maps_items(self):
        with FakeServer() as s:
            s.routes["/2/tweets/search/recent"] = (200, tweets([101, 102]), {})
            usage = {}
            r = XCollector(cfg(s.base), TOKEN, fetcher(), usage, NOW).run([])
            req = s.requests[0]
            self.assertEqual(req["headers"]["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(req["query"]["query"], ["from:sidefx -is:retweet"])
            self.assertEqual(req["query"]["tweet.fields"], ["created_at,lang"])
            self.assertEqual(len(r.new_items), 2)
            it = r.new_items[0]
            self.assertEqual(it["url"], "https://x.com/sidefx/status/101")
            self.assertEqual(it["handle"], "sidefx")
            self.assertEqual(it["source"], "X")
            self.assertEqual(it["tab"], "news")
            self.assertNotIn("<", it["excerpt"])
            self.assertEqual(usage["months"]["2026-11"]["posts_read"], 2)
            self.assertEqual(usage["since_ids"]["from:sidefx"], "102")

    def test_since_id_used_next_time(self):
        with FakeServer() as s:
            s.routes["/2/tweets/search/recent"] = (200, {"meta": {"result_count": 0}}, {})
            XCollector(cfg(s.base), TOKEN, fetcher(), {"since_ids": {"from:sidefx": "555"}}, NOW).run([])
            self.assertEqual(s.requests[0]["query"]["since_id"], ["555"])

    def test_per_run_cap(self):
        with FakeServer() as s:
            s.routes["/2/tweets/search/recent"] = (200, tweets(range(200, 240)), {})  # 40 件返る
            usage = {}
            r = XCollector(cfg(s.base, max_posts_per_run=15), TOKEN, fetcher(), usage, NOW).run([])
            self.assertEqual(len(r.new_items), 15)
            self.assertEqual(usage["months"]["2026-11"]["posts_read"], 15)
            self.assertEqual(s.requests[0]["query"]["max_results"], ["15"])

    def test_monthly_budget(self):
        with FakeServer() as s:
            s.routes["/2/tweets/search/recent"] = (200, tweets([1]), {})
            over = {"months": {"2026-11": {"posts_read": 1500, "requests": 30}}}
            r = XCollector(cfg(s.base), TOKEN, fetcher(), over, NOW).run([stored(9)])
            self.assertIn("monthly budget", r.status["skipped"])
            self.assertEqual(s.requests, [])
            self.assertEqual(r.removed_ids, set())
            # 残りが検索の最小(10)未満なら検索しない
            low = {"months": {"2026-11": {"posts_read": 1495, "requests": 30}}}
            r = XCollector(cfg(s.base), TOKEN, fetcher(), low, NOW).run([])
            self.assertEqual(s.requests, [])
            self.assertLessEqual(low["months"]["2026-11"]["posts_read"], 1500)
            # 別の月は別カウント
            nxt = {"months": {"2026-10": {"posts_read": 1500, "requests": 1}}}
            XCollector(cfg(s.base), TOKEN, fetcher(), nxt, NOW).run([])
            self.assertEqual(len(s.requests), 1)

    def test_deleted_posts_removed_and_counted(self):
        with FakeServer() as s:
            s.routes["/2/tweets"] = (200, {"data": [{"id": "1", "text": "edited text"}, {"id": "3", "text": "c"}],
                                           "errors": [{"resource_id": "2", "title": "Not Found Error"}]}, {})
            usage = {}
            r = XCollector(cfg(s.base, accounts=[]), TOKEN, fetcher(), usage, NOW).run([stored(1), stored(2), stored(3)])
            self.assertEqual(r.removed_ids, {"x:2"})
            self.assertEqual(r.updated["x:1"], "edited text")
            self.assertEqual(usage["months"]["2026-11"]["posts_read"], 3)  # 照会も予算に数える

    def test_lookup_in_chunks_of_100(self):
        with FakeServer() as s:
            s.routes["/2/tweets"] = (200, lambda req: {"data": [{"id": i, "text": "t"} for i in req["query"]["ids"][0].split(",")]}, {})
            items = [stored(1000 + n) for n in range(150)]
            r = XCollector(cfg(s.base, accounts=[], max_posts_per_run=500), TOKEN, fetcher(), {}, NOW).run(items)
            sizes = [len(q["query"]["ids"][0].split(",")) for q in s.requests]
            self.assertEqual(sorted(sizes), [50, 100])
            self.assertEqual(r.removed_ids, set())

    def test_lookup_limited_by_run_cap(self):
        with FakeServer() as s:
            s.routes["/2/tweets"] = (200, lambda req: {"data": [{"id": i, "text": "t"} for i in req["query"]["ids"][0].split(",")]}, {})
            items = [stored(1000 + n) for n in range(30)]
            XCollector(cfg(s.base, accounts=[], max_posts_per_run=20), TOKEN, fetcher(), {}, NOW).run(items)
            self.assertEqual(len(s.requests[0]["query"]["ids"][0].split(",")), 20)

    def test_retention_30_days(self):
        with FakeServer() as s:
            s.routes["/2/tweets"] = (200, {"data": [{"id": "5", "text": "t"}]}, {})
            r = XCollector(cfg(s.base, accounts=[]), TOKEN, fetcher(), {}, NOW).run([stored(4, days_old=40), stored(5, days_old=2)])
            self.assertEqual(r.removed_ids, {"x:4"})
            self.assertEqual(s.requests[0]["query"]["ids"], ["5"])  # 古いものは照会しない

    def test_errors_do_not_leak_token_and_do_not_delete(self):
        with FakeServer() as s:
            s.routes["/2/tweets"] = (401, "Unauthorized " + TOKEN, {})
            s.routes["/2/tweets/search/recent"] = (500, "boom", {})
            r = XCollector(cfg(s.base), TOKEN, fetcher(), {}, NOW).run([stored(1)])
            self.assertFalse(r.status["ok"])
            self.assertEqual(r.removed_ids, set())  # 失敗時は消さない
            self.assertNotIn(TOKEN, json.dumps(r.status))

    def test_invalid_responses(self):
        for body in ("not json", "[1,2]", '{"data": "x"}'):
            with FakeServer() as s:
                s.routes["/2/tweets"] = (200, body, {})
                s.routes["/2/tweets/search/recent"] = (200, body, {})
                r = XCollector(cfg(s.base), TOKEN, fetcher(), {}, NOW).run([stored(1)])
                self.assertFalse(r.status["ok"], body)
                self.assertEqual(r.removed_ids, set(), body)
                self.assertEqual(r.new_items, [])

    def test_dry_run_makes_no_requests(self):
        with FakeServer() as s:
            r = XCollector(cfg(s.base), TOKEN, fetcher(), {}, NOW).run([stored(1), stored(2)], dry_run=True)
            self.assertEqual(s.requests, [])
            self.assertTrue(r.status["dry_run"])
            self.assertEqual(r.status["would_lookup"], 2)
            self.assertEqual(r.status["est_posts"], 2 + 48)

    def test_bad_handle_ignored(self):
        with FakeServer() as s:
            c = cfg(s.base, accounts=[{"handle": "a b; DROP"}, {"handle": "ok_user"}])
            qs = XCollector(c, TOKEN, fetcher(), {}, NOW).queries()
            self.assertEqual([q["key"] for q in qs], ["from:ok_user"])


FEED = """<rss version="2.0"><channel><title>t</title><item><title>Hello Karma</title><link>{base}/a</link>
<description>d</description><pubDate>Tue, 17 Nov 2026 17:19:26 +0000</pubDate></item></channel></rss>"""


class RunTests(unittest.TestCase):
    def setup_dir(self, s, extra_youtube=None, x_enabled=False):
        d = Path(tempfile.mkdtemp())
        (d / "sources.json").write_text(json.dumps({"sources": [
            {"id": "good", "name": "Good", "url": s.base + "/good.xml", "tab": "news", "limit": 10},
            {"id": "bad", "name": "Bad", "url": s.base + "/bad.xml", "tab": "tips"},
            {"id": "broken", "name": "Broken", "url": s.base + "/broken.xml", "tab": "tips"},
        ]}))
        (d / "sources.youtube.json").write_text(json.dumps(extra_youtube or {"channels": []}))
        (d / "sources.x.json").write_text(json.dumps({"enabled": x_enabled, "api_base": s.base + "/2", "accounts": [{"handle": "sidefx"}]}))
        s.routes["/good.xml"] = (200, FEED.format(base=s.base), {"ETag": '"v1"'})
        s.routes["/bad.xml"] = (500, "err", {})
        s.routes["/broken.xml"] = (200, "<rss><channel><item>", {})
        return d

    def run_it(self, d, env=None, **kw):
        out = io.StringIO()
        code = run(d, d / "site", env=env or {}, now=NOW, allow_local_http=True, host_delays={}, default_delay=0, out=out, **kw)
        return code, out.getvalue()

    def test_one_source_down_others_continue_and_old_data_kept(self):
        with FakeServer() as s:
            d = self.setup_dir(s)
            old = {"schema_version": 1, "generated_at": "2026-11-10T00:00:00Z", "sources": [{"id": "bad", "last_ok": "2026-11-10T00:00:00Z"}],
                   "items": [{"id": "keepme", "tab": "tips", "kind": "rss", "source_id": "bad", "source": "Bad", "title": "old", "url": "https://e.example/o",
                              "published": "2026-11-09T00:00:00Z", "excerpt": "", "tags": [], "first_seen": "2026-11-09T00:00:00Z"}]}
            (d / "items.json").write_text(json.dumps(old))
            code, _ = self.run_it(d)
            self.assertEqual(code, 0)
            doc = json.loads((d / "items.json").read_text())
            ids = {i["id"] for i in doc["items"]}
            self.assertIn("keepme", ids)  # 失敗した情報源の古いデータは消さない
            self.assertEqual(len(doc["items"]), 2)
            st = {x["id"]: x for x in doc["sources"]}
            self.assertTrue(st["good"]["ok"])
            self.assertFalse(st["bad"]["ok"])
            self.assertIn("HTTP 500", st["bad"]["error"])
            self.assertEqual(st["bad"]["last_ok"], "2026-11-10T00:00:00Z")
            self.assertFalse(st["broken"]["ok"])
            self.assertEqual(st["x"]["skipped"], "disabled")
            self.assertTrue((d / "site" / "items.json").exists())

    def test_etag_second_run_not_modified_and_no_duplicates(self):
        with FakeServer() as s:
            d = self.setup_dir(s)
            self.run_it(d)
            self.run_it(d)
            doc = json.loads((d / "items.json").read_text())
            self.assertEqual(len([i for i in doc["items"] if i["source_id"] == "good"]), 1)
            st = {x["id"]: x for x in doc["sources"]}
            self.assertTrue(st["good"]["not_modified"])

    def test_all_fail_returns_1_and_keeps_file(self):
        with FakeServer() as s:
            d = self.setup_dir(s)
            s.routes["/good.xml"] = (503, "x", {})
            code, _ = self.run_it(d)
            self.assertEqual(code, 1)

    def test_youtube_api_skipped_without_key_and_capped_with_key(self):
        yt = {"channels": [], "api_search": {"enabled": True, "queries": ["a", "b", "c", "d"], "max_requests_per_run": 2,
                                              "api_base": "PLACEHOLDER", "max_results": 5}}
        with FakeServer() as s:
            yt["api_search"]["api_base"] = s.base + "/youtube/v3"
            s.routes["/youtube/v3/search"] = (200, {"items": [{"id": {"videoId": "abcDEFghi_1"}, "snippet": {
                "publishedAt": "2026-11-17T01:00:00Z", "channelTitle": "Some Chan", "title": "Houdini &amp; tips", "description": "d <b>x</b>"}}]}, {})
            d = self.setup_dir(s, yt)
            self.run_it(d)  # キー無し → 黙ってスキップ
            self.assertEqual([r for r in s.requests if "youtube" in r["path"]], [])
            doc = json.loads((d / "items.json").read_text())
            self.assertEqual({x["id"]: x for x in doc["sources"]}["youtube-api"]["skipped"], "no YOUTUBE_API_KEY")
            code, out = self.run_it(d, env={"YOUTUBE_API_KEY": "KEY_SECRET_999"})
            self.assertEqual(len([r for r in s.requests if "youtube" in r["path"]]), 2)  # 上限 2 回
            doc = json.loads((d / "items.json").read_text())
            it = next(i for i in doc["items"] if i["id"] == "yt:abcDEFghi_1")
            self.assertEqual(it["title"], "Houdini & tips")
            self.assertEqual(it["source"], "Some Chan")
            blob = json.dumps(doc) + out + (d / "fetch_state.json").read_text()
            self.assertNotIn("KEY_SECRET_999", blob)

    def set_publish(self, d, value):
        c = json.loads((d / "sources.x.json").read_text(encoding="utf-8"))
        c["publish_public"] = value
        (d / "sources.x.json").write_text(json.dumps(c))

    def test_x_not_in_public_files_by_default_and_goes_to_local_file(self):
        with FakeServer() as s:
            d = self.setup_dir(s, x_enabled=True)  # publish_public 未指定 = false
            s.routes["/2/tweets/search/recent"] = (200, tweets([777]), {})
            self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            for path in (d / "items.json", d / "site" / "items.json"):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertFalse(any(i["kind"] == "x" for i in doc["items"]), path)
                self.assertNotIn("x:777", path.read_text(encoding="utf-8"))
                self.assertTrue(any(i["source_id"] == "good" for i in doc["items"]))  # Web の項目は出る
            local = json.loads((d / "items.x.local.json").read_text(encoding="utf-8"))
            self.assertEqual([i["id"] for i in local["items"]], ["x:777"])
            # 2 回目: ローカルの保存分が削除追従に使われ、返らなければ消える
            s.routes["/2/tweets"] = (200, {"errors": [{"title": "Not Found Error"}]}, {})
            s.routes["/2/tweets/search/recent"] = (200, {"meta": {"result_count": 0}}, {})
            self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            self.assertEqual(json.loads((d / "items.x.local.json").read_text(encoding="utf-8"))["items"], [])

    def test_x_removed_from_public_even_if_previously_published(self):
        with FakeServer() as s:
            d = self.setup_dir(s)  # X は無効
            (d / "items.json").write_text(json.dumps({"items": [dict(stored(5), published=iso(NOW - timedelta(days=1)))]}))
            self.run_it(d)
            self.assertNotIn("x:5", (d / "items.json").read_text(encoding="utf-8"))
            self.assertNotIn("x:5", (d / "site" / "items.json").read_text(encoding="utf-8"))
            self.assertIn("x:5", (d / "items.x.local.json").read_text(encoding="utf-8"))

    def test_x_in_public_files_when_publish_public_true(self):
        with FakeServer() as s:
            d = self.setup_dir(s, x_enabled=True)
            self.set_publish(d, True)
            s.routes["/2/tweets/search/recent"] = (200, tweets([777]), {})
            self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            for path in (d / "items.json", d / "site" / "items.json"):
                self.assertTrue(any(i["id"] == "x:777" for i in json.loads(path.read_text(encoding="utf-8"))["items"]), path)
            self.assertFalse((d / "items.x.local.json").exists())

    def test_publish_public_must_be_exactly_true(self):
        with FakeServer() as s:
            d = self.setup_dir(s, x_enabled=True)
            self.set_publish(d, "true")  # 文字列などは false 扱い(安全側)
            s.routes["/2/tweets/search/recent"] = (200, tweets([777]), {})
            self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            self.assertNotIn("x:777", (d / "items.json").read_text(encoding="utf-8"))

    def test_x_full_flow_no_token_leak(self):
        with FakeServer() as s:
            d = self.setup_dir(s, x_enabled=True)
            self.set_publish(d, True)
            s.routes["/2/tweets/search/recent"] = (200, tweets([777]), {})
            code, out = self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            doc = json.loads((d / "items.json").read_text())
            self.assertTrue(any(i["id"] == "x:777" for i in doc["items"]))
            usage = (d / "x_usage.json").read_text()
            blob = json.dumps(doc) + out + usage + (d / "fetch_state.json").read_text()
            self.assertNotIn(TOKEN, blob)
            # 2 回目: 保存済みの投稿が照会され、返らなければ消える
            s.routes["/2/tweets"] = (200, {"errors": [{"title": "Not Found Error"}]}, {})
            s.routes["/2/tweets/search/recent"] = (200, {"meta": {"result_count": 0}}, {})
            self.run_it(d, env={"X_BEARER_TOKEN": TOKEN})
            doc = json.loads((d / "items.json").read_text())
            self.assertFalse(any(i["id"] == "x:777" for i in doc["items"]))

    def test_dry_run_no_network_no_write(self):
        with FakeServer() as s:
            d = self.setup_dir(s, x_enabled=True)
            code, out = self.run_it(d, env={"X_BEARER_TOKEN": TOKEN}, dry_run=True)
            self.assertEqual(code, 0)
            self.assertEqual(s.requests, [])
            self.assertFalse((d / "items.json").exists())
            self.assertIn("dry_run", out)
            self.assertNotIn(TOKEN, out)


if __name__ == "__main__":
    unittest.main()
