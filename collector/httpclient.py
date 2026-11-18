"""礼儀正しい HTTP 取得: ホストごとの間隔・汎用 UA・サイズ上限・ETag/Last-Modified・秘密の除去。"""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_UA = "Mozilla/5.0 (compatible; ReferenceFeedReader/0.1)"
# sidefx.com の robots.txt は Crawl-delay: 5 を指定している。
HOST_DELAYS = {"www.sidefx.com": 5.0, "sidefx.com": 5.0}
DEFAULT_DELAY = 1.0


class FetchError(Exception):
    """メッセージは秘密(トークン・キー)と URL のクエリを含まない。"""


@dataclass
class Result:
    status: int
    body: bytes
    not_modified: bool = False


def redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[redacted]")
    return text


def _safe_where(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


class Fetcher:
    def __init__(
        self,
        state: dict | None = None,
        *,
        user_agent: str = DEFAULT_UA,
        timeout: float = 20.0,
        max_bytes: int = 2_000_000,
        host_delays: dict[str, float] | None = None,
        default_delay: float = DEFAULT_DELAY,
        secrets: list[str] | None = None,
        allow_local_http: bool = False,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.state = state if state is not None else {}
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.host_delays = HOST_DELAYS if host_delays is None else host_delays
        self.default_delay = default_delay
        self.secrets = secrets or []
        self.allow_local_http = allow_local_http
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        delay = self.host_delays.get(host, self.default_delay)
        last = self._last.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()

    def _check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme == "https":
            return
        if self.allow_local_http and parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost"):
            return
        raise FetchError("only https URLs are allowed")

    def get(self, url: str, *, headers: dict[str, str] | None = None, cache: bool = True) -> Result:
        self._check_url(url)
        host = urlsplit(url).netloc
        req_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        entry = self.state.get(url, {}) if cache else {}
        if entry.get("etag"):
            req_headers["If-None-Match"] = entry["etag"]
        if entry.get("last_modified"):
            req_headers["If-Modified-Since"] = entry["last_modified"]
        req_headers.update(headers or {})
        self._wait(host)
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise FetchError("response too large")
                if cache:
                    self.state[url] = {
                        "etag": resp.headers.get("ETag", ""),
                        "last_modified": resp.headers.get("Last-Modified", ""),
                    }
                return Result(resp.status, body)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return Result(304, b"", not_modified=True)
            body = b""
            try:
                body = exc.read(4096)
            except Exception:
                pass
            err = FetchError(f"HTTP {exc.code} from {_safe_where(url)}")
            err.status = exc.code  # type: ignore[attr-defined]
            err.body = body  # type: ignore[attr-defined]
            raise err from None
        except FetchError:
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            reason = redact(str(getattr(exc, "reason", exc)), self.secrets)[:120]
            raise FetchError(f"network error from {_safe_where(url)}: {reason}") from None
