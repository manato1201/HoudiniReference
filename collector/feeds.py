"""RSS 2.0 / Atom / YouTube フィードのパーサ(標準ライブラリのみ)。

入力は信頼しない: サイズ上限・DOCTYPE/ENTITY の拒否(実体展開攻撃の対策)・壊れた XML は FeedError。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MAX_FEED_BYTES = 2_000_000
MAX_ENTRIES = 500


class FeedError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_date(value: str | None) -> str | None:
    """RFC 822 / ISO 8601 を UTC の ISO 文字列 (YYYY-MM-DDTHH:MM:SSZ) にする。失敗は None。"""
    if not value:
        return None
    value = value.strip()
    dt = None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _children(el: ET.Element, name: str):
    return [c for c in el if _local(c.tag) == name]


def _first(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for link in _children(entry, "link"):
        href = (link.get("href") or "").strip()
        rel = link.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
    return fallback


def _summary(entry: ET.Element) -> str:
    for name in ("summary", "description", "content", "encoded"):
        el = _first(entry, name)
        if el is not None and _text(el):
            return _text(el)
    # YouTube: <media:group><media:description>
    group = _first(entry, "group")
    if group is not None:
        desc = _first(group, "description")
        if desc is not None:
            return _text(desc)
    return ""


def parse_feed(data: bytes | str) -> list[dict]:
    """エントリの生の辞書 (title, url, published, summary, video_id, categories) を返す。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not data or not data.strip():
        raise FeedError("empty feed")
    if len(data) > MAX_FEED_BYTES:
        raise FeedError("feed too large")
    lowered = data.lower()
    if b"<!entity" in lowered or b"<!doctype" in lowered:
        raise FeedError("DOCTYPE/ENTITY not allowed")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FeedError(f"invalid xml: {exc}") from None

    kind = _local(root.tag)
    if kind == "feed":
        nodes = _children(root, "entry")
    elif kind == "rss":
        channel = _first(root, "channel")
        nodes = _children(channel, "item") if channel is not None else []
    elif kind == "RDF":
        nodes = _children(root, "item")
    else:
        raise FeedError(f"unknown feed root: {kind[:30]}")

    entries: list[dict] = []
    for node in nodes[:MAX_ENTRIES]:
        title = _text(_first(node, "title"))
        if kind == "feed":
            url = _atom_link(node)
            published = parse_date(_text(_first(node, "published")) or _text(_first(node, "updated")))
        else:
            url = _text(_first(node, "link"))
            if not url:
                guid = _text(_first(node, "guid"))
                url = guid if guid.startswith("http") else ""
            published = parse_date(_text(_first(node, "pubDate")) or _text(_first(node, "date")))
        video_el = _first(node, "videoId")
        entries.append(
            {
                "title": title,
                "url": url,
                "published": published,
                "summary": _summary(node),
                "video_id": _text(video_el) if video_el is not None else "",
                "categories": [c.get("term") or _text(c) for c in _children(node, "category")],
            }
        )
    return entries


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def is_video_id(value: str) -> bool:
    return bool(_VIDEO_ID.match(value or ""))
