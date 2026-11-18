import unittest

from collector.httpclient import FetchError, Fetcher, HOST_DELAYS

from .fakeserver import FakeServer


class FetcherTests(unittest.TestCase):
    def test_https_only(self):
        with self.assertRaises(FetchError):
            Fetcher().get("http://example.com/")
        with self.assertRaises(FetchError):
            Fetcher().get("file:///etc/passwd")

    def test_sidefx_crawl_delay_is_5s(self):
        self.assertEqual(HOST_DELAYS["www.sidefx.com"], 5.0)
        sleeps, t = [], [100.0]
        f = Fetcher(sleep=sleeps.append, clock=lambda: t[0])
        f._wait("www.sidefx.com")
        t[0] += 1.0
        f._wait("www.sidefx.com")
        self.assertAlmostEqual(sleeps[0], 4.0)
        f._wait("www.youtube.com")  # 別ホストは待たない
        self.assertEqual(len(sleeps), 1)

    def test_size_limit_and_generic_ua(self):
        with FakeServer() as s:
            s.routes["/big"] = (200, b"x" * 5000, {})
            f = Fetcher(allow_local_http=True, host_delays={}, default_delay=0, max_bytes=1000)
            with self.assertRaises(FetchError):
                f.get(s.base + "/big")
            f.max_bytes = 10000
            f.get(s.base + "/big")
            ua = s.requests[-1]["headers"]["User-Agent"]
            self.assertNotIn("@", ua)
            self.assertIn("ReferenceFeedReader", ua)

    def test_error_has_no_query(self):
        with FakeServer() as s:
            s.routes["/e"] = (500, "x", {})
            f = Fetcher(allow_local_http=True, host_delays={}, default_delay=0)
            with self.assertRaises(FetchError) as cm:
                f.get(s.base + "/e?key=SECRET")
            self.assertNotIn("SECRET", str(cm.exception))

    def test_conditional_get(self):
        with FakeServer() as s:
            s.routes["/f"] = (200, "body", {"ETag": '"abc"', "Last-Modified": "Tue, 17 Nov 2026 00:00:00 GMT"})
            f = Fetcher({}, allow_local_http=True, host_delays={}, default_delay=0)
            self.assertFalse(f.get(s.base + "/f").not_modified)
            self.assertTrue(f.get(s.base + "/f").not_modified)
            self.assertEqual(s.requests[-1]["headers"]["If-None-Match"], '"abc"')


if __name__ == "__main__":
    unittest.main()
