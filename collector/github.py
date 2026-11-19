"""GitHub のリリース情報(公式 REST API・認証なし)。題名・URL・日付・タグだけを取り、本文(body)は読まない・保存しない。

`github.com/<repo>/releases.atom` は github.com の robots.txt が `Disallow: /*.atom$` なので使わない。
認証なしの上限は 60 回/時(IP ごと)。ETag の条件付き GET(304 は上限に数えられない)で減らす。
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .feeds import parse_date
from .httpclient import FetchError, Fetcher
from .items import make_item, url_id
from .tagging import auto_tags
from .textutil import clean_title, safe_url

API_BASE = "https://api.github.com"
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*$")  # "../x" や "." 始まりを通さない


def github_sources(cfg: dict) -> list[dict]:
    """sources.github.json の repos → 収集器の情報源(kind="github")。リポジトリ名の形が不正なものは捨てる。"""
    out = []
    for r in cfg.get("repos", []) if isinstance(cfg.get("repos"), list) else []:
        if not isinstance(r, dict) or not r.get("enabled", True):
            continue
        repo = r.get("repo", "")
        if not isinstance(repo, str) or not _REPO.match(repo):
            continue
        label = r.get("label") or repo.split("/", 1)[1]
        out.append({
            "id": "github-" + repo.lower().replace("/", "-").replace(".", "-"),
            "name": label, "label": label, "kind": "github", "repo": repo,
            "url": f"{cfg.get('api_base', API_BASE)}/repos/{repo}/releases?per_page={min(int(r.get('limit', 10)), 30)}",
            "tab": r.get("tab", "reference"), "tags": ["GitHub", "Release notes", *r.get("tags", [])],
            "limit": int(r.get("limit", 10)), "keep": int(r.get("keep", 30)), "lang": "en",
        })
    return out


def fetch_github_releases(fetcher: Fetcher, src: dict, now: datetime) -> tuple[list[dict], bool]:
    """(新しい項目のリスト, not_modified)。失敗は FetchError。"""
    try:
        res = fetcher.get(src["url"], headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    except FetchError as exc:
        if getattr(exc, "status", None) in (403, 429):  # 認証なしの上限(60 回/時)に達した時など
            raise FetchError(f"{exc} (rate limited?)") from None
        raise
    if res.not_modified:
        return [], True
    try:
        data = json.loads(res.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise FetchError("invalid JSON from GitHub API") from None
    if not isinstance(data, list):
        raise FetchError("unexpected response from GitHub API")
    prefix = f"https://github.com/{src['repo']}/"
    items: list[dict] = []
    for row in data[: src["limit"]]:
        if not isinstance(row, dict) or row.get("draft"):
            continue
        url = safe_url(row.get("html_url"))
        if not url or not url.startswith(prefix):  # 想定外のホストのリンクは使わない
            continue
        tag = row.get("tag_name") if isinstance(row.get("tag_name"), str) else ""
        name = row.get("name") if isinstance(row.get("name"), str) and row.get("name") else tag
        if not name:
            continue
        label = src["label"]
        title = clean_title(name if label.lower() in name.lower() else f"{label}: {name}")
        published = parse_date(row.get("published_at") or row.get("created_at")) or now.strftime("%Y-%m-%dT%H:%M:%SZ")
        tags = auto_tags(f"{title} {tag}", src.get("tags"))
        if row.get("prerelease") and "Pre-release" not in tags:
            tags = (tags + ["Pre-release"])[:6]
        items.append(make_item(
            item_id=url_id(url), tab=src["tab"], kind="github", source_id=src["id"], source=src["name"],
            title=title, url=url, published=published, exc="", tags=tags, now=now, lang="en",
        ))
    return items, False
