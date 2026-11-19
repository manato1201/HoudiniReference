"""テキストの正規化: HTML タグ除去・空白整理・抜粋・URL 検査。"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

EXCERPT_MAX = 200
TITLE_MAX = 200

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS = re.compile(r"\s+")
_SKIP_TAGS = {"script", "style", "noscript", "template"}
_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}
_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "si", "feature"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(value: str | None) -> str:
    """HTML タグ・script/style を除去し、実体参照を戻し、空白を 1 つにまとめる。"""
    if not value:
        return ""
    # 二重エスケープ(&lt;p&gt;)のフィードがあるので、最大 2 回かける
    text = value
    for _ in range(2):
        parser = _Stripper()
        try:
            parser.feed(text)
            parser.close()
        except Exception:  # 壊れた HTML でも落とさない
            text = re.sub(r"<[^>]*>", " ", text)
            break
        text = "".join(parser.parts)
        if "<" not in text:
            break
    text = html.unescape(text)
    text = _CTRL.sub("", text)
    return _WS.sub(" ", text).strip()


def truncate(text: str, limit: int = EXCERPT_MAX) -> str:
    """limit 文字以内(省略記号を含む)。"""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rstrip()
    return cut + "…"


def excerpt(value: str | None, limit: int = EXCERPT_MAX) -> str:
    return truncate(strip_html(value), limit)


def clean_title(value: str | None) -> str:
    return truncate(strip_html(value), TITLE_MAX)


def safe_url(value: str | None) -> str | None:
    """http(s) のみ許可。それ以外(javascript: など)は None。"""
    if not value:
        return None
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return value


def canonical_url(url: str) -> str:
    """追跡パラメータとフラグメントを除いた URL(重複判定用)。"""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in _TRACKING)
    ]
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


_JA = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")


def detect_lang(text: str | None) -> str:
    """かな・漢字を含めば "ja"、無ければ "en"(補助。2 言語の表示用で、精度は保証しない)。"""
    return "ja" if text and _JA.search(text) else "en"


_TITLE_KEY_DROP = re.compile(r"[\W_]+", re.UNICODE)


def title_key(title: str | None) -> str:
    """題名の重複判定用キー(大文字小文字・記号・空白の違いを無視)。"""
    return _TITLE_KEY_DROP.sub("", (title or "").casefold())
