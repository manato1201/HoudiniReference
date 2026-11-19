"""収集の流れ: 取得 → 正規化 → 重複除去 → タグ付け → items.json。1 つの情報源が落ちても他は続ける。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .feeds import FeedError
from .github import fetch_github_releases, github_sources
from .httpclient import FetchError, Fetcher, redact
from .items import fetch_feed_source, iso, youtube_api_search
from .textutil import detect_lang, title_key
from .xapi import TOKEN_ENV, XCollector

SCHEMA_VERSION = 1
YT_KEY_ENV = "YOUTUBE_API_KEY"
DEFAULT_KEEP = 200
RETENTION_DAYS_BY_SOURCE = {"youtube-api": 30, "x": 30}  # API 由来のデータは短く持つ
X_LOCAL_FILE = "items.x.local.json"  # publish_public が false の時の X 項目の置き場(.gitignore 済み・公開しない)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


SITE_FILES = ("items.json", "reference.json", "nodes.json")  # サイトが読む公開データ(data/ → site/data/ へコピー)


def sync_site_data(data_dir: Path, site_data_dir: Path) -> None:
    site_data_dir.mkdir(parents=True, exist_ok=True)
    for name in SITE_FILES:
        if (data_dir / name).exists():
            shutil.copyfile(data_dir / name, site_data_dir / name)


def load_x_items(data_dir: Path, public_items: list[dict]) -> list[dict]:
    """保存済みの X 項目。ローカル専用ファイルと(過去に公開物へ入っていた分も)両方から集めて id で重複除去。"""
    local = load_json(data_dir / X_LOCAL_FILE, {})
    rows = local.get("items", []) if isinstance(local.get("items"), list) else []
    by_id = {}
    for i in list(public_items) + rows:
        if isinstance(i, dict) and i.get("kind") == "x" and isinstance(i.get("id"), str):
            by_id[i["id"]] = i
    return list(by_id.values())


def feed_sources(data_dir: Path) -> list[dict]:
    """sources.json の RSS/Atom + sources.youtube.json の公式フィード(チャンネル)+ sources.github.json(リリース API)。"""
    out = []
    for s in load_json(data_dir / "sources.json", {}).get("sources", []):
        if s.get("enabled", True) and s.get("id") and s.get("url"):
            out.append({**s, "kind": "rss"})
    for ch in load_json(data_dir / "sources.youtube.json", {}).get("channels", []):
        cid = ch.get("id", "")
        if ch.get("enabled", True) and cid.startswith("UC") and len(cid) == 24:
            out.append({
                "id": f"youtube-{ch.get('slug') or cid[-6:].lower()}", "name": ch.get("name", "YouTube"), "kind": "youtube",
                "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", "tab": ch.get("tab", "tips"),
                "tags": ["YouTube", *ch.get("tags", [])], "limit": ch.get("limit", 15), "keep": ch.get("keep", 100),
                "lang": ch.get("lang"),
            })
    out += github_sources(load_json(data_dir / "sources.github.json", {}))
    return out


def interleave_by_host(sources: list[dict]) -> list[dict]:
    """取得の順番だけを、ホストを交互にする(待ち時間の重ね合わせ)。sidefx.com は 5 秒あけるので、その間に他のホストを取る。"""
    queues: dict[str, list[dict]] = {}
    for s in sources:
        queues.setdefault(urlsplit(s["url"]).netloc, []).append(s)
    out: list[dict] = []
    while any(queues.values()):
        for q in queues.values():
            if q:
                out.append(q.pop(0))
    return out


def dedupe_titles(items: list[dict], order: dict[str, int]) -> list[dict]:
    """Web(rss)の項目で、題名が同じ(記号・大文字小文字の違いは無視)ものを 1 件にする。
    同じ話題が複数の情報源(フォーラムのトピックと分類別、Qiita と Zenn の転載など)から来ても重複しない。
    残すのは、情報源の並び順が先のもの → 同じ情報源なら新しいもの。YouTube・GitHub・X は題名では判定しない。"""
    groups: dict[str, list[dict]] = {}
    for it in items:
        key = title_key(it.get("title"))
        if it.get("kind") == "rss" and len(key) >= 6:  # 短すぎる題名は別物の可能性が高いので対象外
            groups.setdefault(key, []).append(it)
    drop: set[int] = set()
    for group in groups.values():
        if len(group) > 1:
            group.sort(key=lambda i: i.get("published", ""), reverse=True)
            group.sort(key=lambda i: order.get(i.get("source_id"), 10_000))  # 安定ソート: 情報源の順が優先
            drop.update(id(i) for i in group[1:])
    return [i for i in items if id(i) not in drop]


def merge(existing: list[dict], new: list[dict]) -> list[dict]:
    by_id = {i["id"]: i for i in existing if isinstance(i, dict) and "id" in i}
    for it in new:
        old = by_id.get(it["id"])
        if old:
            if it["source_id"] == "youtube-api":
                continue  # 公式フィード由来の項目を優先
            it = {**it, "first_seen": old.get("first_seen", it["first_seen"])}
            if "views" not in it and isinstance(old.get("views"), int):
                it["views"] = old["views"]  # 今回のフィードに再生数が無くても、前回の値を残す
        by_id[it["id"]] = it
    return list(by_id.values())


def apply_retention(items: list[dict], now: datetime, keep_by_source: dict[str, int]) -> list[dict]:
    kept = []
    for it in items:
        days = RETENTION_DAYS_BY_SOURCE.get(it.get("source_id"))
        if days and it.get("published", "") < iso(now - timedelta(days=days)):
            continue
        kept.append(it)
    kept.sort(key=lambda i: (i.get("published", ""), i["id"]), reverse=True)
    counts: dict[str, int] = {}
    out = []
    for it in kept:
        sid = it.get("source_id", "")
        counts[sid] = counts.get(sid, 0) + 1
        if counts[sid] <= keep_by_source.get(sid, DEFAULT_KEEP):
            out.append(it)
    return out


def run(
    data_dir: Path,
    site_data_dir: Path | None = None,
    *,
    env: dict | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
    only: str | None = None,
    no_x: bool = False,
    no_youtube_api: bool = False,
    allow_local_http: bool = False,
    host_delays: dict | None = None,
    default_delay: float | None = None,
    out=sys.stdout,
) -> int:
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    token, yt_key = env.get(TOKEN_ENV) or None, env.get(YT_KEY_ENV) or None

    old = load_json(data_dir / "items.json", {})
    old_items = old.get("items", []) if isinstance(old.get("items"), list) else []
    old_status = {s.get("id"): s for s in old.get("sources", []) if isinstance(s, dict)}
    x_cfg = load_json(data_dir / "sources.x.json", {})
    yt_cfg = load_json(data_dir / "sources.youtube.json", {})
    usage = load_json(data_dir / "x_usage.json", {})
    stored_x = load_x_items(data_dir, old_items)
    publish_x = x_cfg.get("publish_public") is True  # 既定 false: 公開物(items.json)に X の抜粋を出さない
    sources = [s for s in feed_sources(data_dir) if not only or s["id"] == only]

    if dry_run:  # 取得せず、見込みだけ出す
        plan = {"dry_run": True, "feeds": [s["id"] for s in sources]}
        plan["x"] = XCollector(x_cfg, token or "dry", Fetcher(), usage, now).run(stored_x, dry_run=True).status if not no_x else "skipped"
        api = yt_cfg.get("api_search", {})
        plan["youtube_api"] = {"enabled": bool(api.get("enabled")) and bool(yt_key), "max_requests": api.get("max_requests_per_run", 5), "units": 100 * int(api.get("max_requests_per_run", 5))}
        out.write(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
        return 0

    fetch_state = load_json(data_dir / "fetch_state.json", {})
    fetcher = Fetcher(fetch_state, secrets=[t for t in (token, yt_key) if t], allow_local_http=allow_local_http, host_delays=host_delays,
                      **({} if default_delay is None else {"default_delay": default_delay}))
    new_items: list[dict] = []
    statuses: list[dict] = []
    keep_by_source = {s["id"]: int(s.get("keep", DEFAULT_KEEP)) for s in sources}
    attempted = ok_count = 0

    def record(st: dict) -> None:
        prev = old_status.get(st["id"], {})
        if st.get("ok"):
            st["last_ok"] = iso(now)
        elif prev.get("last_ok"):
            st["last_ok"] = prev["last_ok"]
        statuses.append(st)

    config_order = {s["id"]: n for n, s in enumerate(sources)}
    for src in interleave_by_host(sources):
        st = {"id": src["id"], "name": src["name"], "kind": src["kind"], "tab": src.get("tab", "tips")}
        attempted += 1
        try:
            fetch = fetch_github_releases if src["kind"] == "github" else fetch_feed_source
            items, not_mod = fetch(fetcher, src, now)
            st.update(ok=True, fetched=len(items), not_modified=not_mod)
            new_items += items
            ok_count += 1
        except (FetchError, FeedError) as exc:
            st.update(ok=False, error=redact(str(exc), [t for t in (token, yt_key) if t])[:200])
        except Exception as exc:  # 想定外でも他の情報源は続ける
            st.update(ok=False, error=f"unexpected {type(exc).__name__}")
        record(st)
    statuses.sort(key=lambda st: config_order.get(st["id"], 0))  # 画面の表示は設定ファイルの並び順

    # YouTube Data API(任意)
    api = yt_cfg.get("api_search", {})
    if api.get("enabled") and not no_youtube_api and not only:
        st = {"id": "youtube-api", "name": "YouTube 検索 (API)", "kind": "youtube", "tab": api.get("tab", "tips")}
        if not yt_key:
            st.update(ok=None, skipped=f"no {YT_KEY_ENV}")
        else:
            attempted += 1
            try:
                items, used = youtube_api_search(fetcher, yt_key, api, now)
                st.update(ok=True, fetched=len(items), requests=used, units_estimate=used * 100)
                new_items += items
                ok_count += 1
            except (FetchError, FeedError) as exc:
                st.update(ok=False, error=redact(str(exc), [yt_key])[:200])
        record(st)

    # X(既定は無効)
    removed: set[str] = set()
    updated: dict[str, str] = {}
    if not no_x and not only:
        xr = XCollector(x_cfg, token, fetcher, usage, now).run(stored_x)
        st = xr.status
        if st.get("ok") is not None:
            attempted += 1
            ok_count += 1 if st["ok"] else 0
            write_json(data_dir / "x_usage.json", usage)
        new_items += xr.new_items
        removed, updated = xr.removed_ids, xr.updated
        record(st)

    # X は保存済みの分(ローカル専用ファイル由来を含む)を足してから、保持期限・削除を適用する
    base = [i for i in old_items if i.get("kind") != "x"] + stored_x
    items = [i for i in base if i.get("id") not in removed]
    for i in items:
        if i["id"] in updated:
            i["excerpt"] = updated[i["id"]]
    items = dedupe_titles(merge(items, new_items), config_order)
    for i in items:  # 過去に保存した項目にも言語を付ける
        if i.get("lang") not in ("ja", "en"):
            i["lang"] = detect_lang(f"{i.get('title', '')} {i.get('excerpt', '')}")
    items = apply_retention(items, now, keep_by_source)

    x_items = [i for i in items if i.get("kind") == "x"]
    if publish_x:
        public_items = items
    else:
        public_items = [i for i in items if i.get("kind") != "x"]
        if x_items or (data_dir / X_LOCAL_FILE).exists():
            write_json(data_dir / X_LOCAL_FILE, {"schema_version": SCHEMA_VERSION, "generated_at": iso(now),
                                                 "note": "ローカル専用。公開しない(.gitignore 済み)", "items": x_items})
    if publish_x:
        (data_dir / X_LOCAL_FILE).unlink(missing_ok=True)  # 公開物に統合済み。古い二重管理を残さない

    doc = {"schema_version": SCHEMA_VERSION, "generated_at": iso(now), "sources": statuses, "items": public_items}
    write_json(data_dir / "items.json", doc)
    write_json(data_dir / "fetch_state.json", fetch_state)
    if site_data_dir:
        sync_site_data(data_dir, site_data_dir)
    out.write(json.dumps({"items": len(public_items), "x_items_local_only": 0 if publish_x else len(x_items), "sources": [{k: s.get(k) for k in ("id", "ok", "fetched", "skipped", "error")} for s in statuses]}, ensure_ascii=False, indent=1) + "\n")
    return 1 if attempted and ok_count == 0 else 0
