"""項目(items.json の 1 件)の組み立てと、フィード/YouTube API の正規化。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .feeds import is_video_id, parse_date, parse_feed
from .httpclient import FetchError, Fetcher
from .tagging import auto_tags
from .textutil import canonical_url, clean_title, detect_lang, excerpt, safe_url, title_key

TABS = ("news", "tips", "reference")
KINDS = ("rss", "youtube", "x", "github")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def make_item(*, item_id, tab, kind, source_id, source, title, url, published, exc, tags, now, handle=None, lang=None) -> dict:
    item = {
        "id": item_id,
        "tab": tab if tab in TABS else "tips",
        "kind": kind,
        "source_id": source_id,
        "source": source,
        "title": title,
        "url": url,
        "published": published,
        "excerpt": exc,
        "tags": tags,
        "lang": lang if lang in ("ja", "en") else detect_lang(f"{title} {exc}"),
        "first_seen": iso(now),
    }
    if handle:
        item["handle"] = handle
    return item


def normalize_entry(raw: dict, src: dict, now: datetime) -> dict | None:
    """フィードの 1 エントリ → 項目。必須(題名・安全な URL)が無ければ None。"""
    title = clean_title(raw.get("title"))
    kind = src.get("kind", "rss")
    video_id = raw.get("video_id", "")
    if kind == "youtube":
        if not is_video_id(video_id):
            return None
        url = f"https://www.youtube.com/watch?v={video_id}"
        item_id = f"yt:{video_id}"
    else:
        url = safe_url(raw.get("url"))
        if not url:
            return None
        item_id = url_id(url)
    if not title:
        return None
    exc = excerpt(raw.get("summary"))
    published = raw.get("published") or iso(now)
    tags = auto_tags(f"{title} {exc}", src.get("tags"))
    version = _changelog_version(title)
    if version and version not in tags:
        tags = (tags + [version])[:6]
    return make_item(
        item_id=item_id, tab=src.get("tab", "tips"), kind=kind, source_id=src["id"], source=src["name"],
        title=title, url=url, published=published, exc=exc, tags=tags, now=now, lang=src.get("lang"),
    )


def _changelog_version(title: str) -> str | None:
    head = title.split(":", 1)[0].strip()
    parts = head.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return f"H{parts[0]}.{parts[1]}"
    return None


def fetch_feed_source(fetcher: Fetcher, src: dict, now: datetime) -> tuple[list[dict], bool]:
    """(新しい項目のリスト, not_modified)。失敗は例外(FetchError / FeedError)。"""
    res = fetcher.get(src["url"])
    if res.not_modified:
        return [], True
    entries = parse_feed(res.body)
    limit = int(src.get("limit", 30))
    items: list[dict] = []
    seen_titles: set[str] = set()
    for raw in entries[:limit]:
        it = normalize_entry(raw, src, now)
        if not it:
            continue
        if src.get("dedupe_title"):  # 投稿単位のフィード(フォーラム)は同じ題名が並ぶ。新しい方だけ残す
            key = title_key(it["title"])
            if key in seen_titles:
                continue
            seen_titles.add(key)
        items.append(it)
    return items, False


def youtube_api_search(
    fetcher: Fetcher, key: str, cfg: dict, now: datetime
) -> tuple[list[dict], int]:
    """YouTube Data API v3 search.list(1 回 100 ユニット)。(項目, 使った回数) を返す。"""
    queries = list(cfg.get("queries", []))
    max_req = int(cfg.get("max_requests_per_run", 5))
    days = int(cfg.get("days", 7))
    max_results = max(1, min(int(cfg.get("max_results", 10)), 50))
    base = cfg.get("api_base", "https://www.googleapis.com/youtube/v3")
    after = iso(now - timedelta(days=days))
    out: list[dict] = []
    used = 0
    src = {"id": "youtube-api", "name": "YouTube", "kind": "youtube", "tab": cfg.get("tab", "tips"), "tags": ["YouTube"]}
    for q in queries[:max_req]:
        params = urlencode(
            {"part": "snippet", "type": "video", "q": q, "order": "date", "maxResults": max_results,
             "publishedAfter": after, "key": key}
        )
        used += 1
        res = fetcher.get(f"{base}/search?{params}", cache=False)
        try:
            data = json.loads(res.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise FetchError("invalid JSON from YouTube API") from None
        if not isinstance(data, dict):
            raise FetchError("unexpected response from YouTube API")
        for row in data.get("items", []) if isinstance(data.get("items"), list) else []:
            try:
                vid = row["id"]["videoId"]
                sn = row["snippet"]
                raw = {
                    "title": sn.get("title", ""), "summary": sn.get("description", ""),
                    "video_id": vid, "published": sn.get("publishedAt"),
                }
                raw["published"] = parse_date(raw["published"])
                s = dict(src, name=clean_title(sn.get("channelTitle")) or "YouTube")
            except (KeyError, TypeError, AttributeError):
                continue
            it = normalize_entry(raw, s, now)
            if it:
                out.append(it)
    return out, used
