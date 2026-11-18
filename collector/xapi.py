"""X(旧 Twitter)公式 API v2 だけを使う収集。既定は無効。

- トークンは環境変数 X_BEARER_TOKEN からのみ受け取る。ログ・保存・例外文に出さない。
- 費用の安全装置: 1 回の上限(max_posts_per_run)・月の上限(monthly_post_budget)+ data/x_usage.json・ドライラン。
- 保存は 投稿 ID・URL・ハンドル・日付・本文の先頭 200 字・タグ だけ。保持は retention_days(既定 30)。
- 削除への追従: 保存している投稿の ID を 100 件ずつ照会し、返らないものを取り除く(予算に数える)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .feeds import parse_date
from .httpclient import FetchError, Fetcher, redact
from .items import iso, make_item
from .tagging import auto_tags
from .textutil import excerpt

TOKEN_ENV = "X_BEARER_TOKEN"
LOOKUP_CHUNK = 100
SEARCH_MIN, SEARCH_MAX = 10, 100  # recent search の max_results の範囲
DEFAULTS = {
    "enabled": False,
    "publish_public": False,  # false: X の抜粋を公開物(items.json)に出さない。true にするのは自己責任(規約を確認)
    "api_base": "https://api.x.com/2",
    "max_posts_per_run": 50,
    "monthly_post_budget": 1500,
    "retention_days": 30,
    "assumed_usd_per_post": 0.005,  # 第三者の記事の値。未確認。開発者コンソールで確認すること
    "accounts": [],
    "queries": [],
}
FIELDS = {"tweet.fields": "created_at,lang", "expansions": "author_id", "user.fields": "username"}


@dataclass
class XResult:
    status: dict
    new_items: list[dict] = field(default_factory=list)
    removed_ids: set[str] = field(default_factory=set)
    updated: dict[str, str] = field(default_factory=dict)  # item id -> new excerpt


def month_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def load_config(raw: dict | None) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(raw or {})
    for k in ("max_posts_per_run", "monthly_post_budget", "retention_days"):
        cfg[k] = max(0, int(cfg[k]))
    return cfg


def _newer(a: str, b: str) -> bool:
    return (len(a), a) > (len(b), b)  # ID は数字文字列。桁数→辞書順で比較


class XCollector:
    def __init__(self, cfg: dict, token: str | None, fetcher: Fetcher, usage: dict, now: datetime):
        self.cfg = load_config(cfg)
        self.token = token
        self.fetcher = fetcher
        self.usage = usage
        self.now = now
        self.month = month_key(now)

    # --- 予算 ---
    def used_this_month(self) -> int:
        return int(self.usage.get("months", {}).get(self.month, {}).get("posts_read", 0))

    def _count(self, posts: int) -> None:
        m = self.usage.setdefault("months", {}).setdefault(self.month, {"posts_read": 0, "requests": 0})
        m["posts_read"] = int(m.get("posts_read", 0)) + posts
        m["requests"] = int(m.get("requests", 0)) + 1

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _get_json(self, path: str, params: dict) -> dict:
        url = f"{self.cfg['api_base']}{path}?{urlencode(params)}"
        res = self.fetcher.get(url, headers=self._headers(), cache=False)
        try:
            data = json.loads(res.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise FetchError("invalid JSON from X API") from None
        if not isinstance(data, dict):
            raise FetchError("unexpected response shape from X API")
        return data

    # --- 実行 ---
    def queries(self) -> list[dict]:
        qs = []
        for acc in self.cfg["accounts"]:
            handle = str(acc.get("handle", "")).lstrip("@")
            if handle.replace("_", "").isalnum() and len(handle) <= 15:
                qs.append({"q": f"from:{handle} -is:retweet", "tab": acc.get("tab", "news"), "tags": acc.get("tags", []), "key": f"from:{handle}"})
        for q in self.cfg["queries"]:
            if q.get("q"):
                qs.append({"q": q["q"], "tab": q.get("tab", "tips"), "tags": q.get("tags", []), "key": q["q"]})
        return qs

    def run(self, stored_x: list[dict], dry_run: bool = False) -> XResult:
        st = {"id": "x", "name": "X", "kind": "x"}
        if not self.cfg["enabled"]:
            return XResult({**st, "ok": None, "skipped": "disabled"})
        if not self.token:
            return XResult({**st, "ok": None, "skipped": f"no {TOKEN_ENV}"})  # エラーにしない
        run_left = self.cfg["max_posts_per_run"]
        month_left = self.cfg["monthly_post_budget"] - self.used_this_month()
        if month_left <= 0:
            return XResult({**st, "ok": None, "skipped": "monthly budget exceeded", "used_month": self.used_this_month()})
        left = min(run_left, month_left)

        # 保持期間を過ぎたものは照会せずに消す
        cutoff = iso(self.now - timedelta(days=self.cfg["retention_days"]))
        res = XResult(st)
        live = []
        for it in stored_x:
            if it.get("published", "") < cutoff:
                res.removed_ids.add(it["id"])
            else:
                live.append(it)
        live.sort(key=lambda i: i.get("published", ""), reverse=True)

        if dry_run:
            lookup_n = min(len(live), left)
            search_n = max(0, left - lookup_n) if left - lookup_n >= SEARCH_MIN else 0
            est = lookup_n + (search_n if self.queries() else 0)
            res.status.update({
                "ok": None, "dry_run": True, "would_lookup": lookup_n, "would_search_up_to": search_n if self.queries() else 0,
                "est_posts": est, "est_usd_assumed": round(est * self.cfg["assumed_usd_per_post"], 4),
                "note": "単価は未確認(開発者コンソールで確認)", "month_used": self.used_this_month(), "month_budget": self.cfg["monthly_post_budget"],
            })
            return res

        errors: list[str] = []
        notes: list[str] = []
        looked = searched = 0
        # 1) 削除への追従
        pending = live[: max(0, left)]
        i = 0
        while i < len(pending) and left > 0:
            chunk = pending[i : i + min(LOOKUP_CHUNK, left)]
            ids = [c["id"].split(":", 1)[-1] for c in chunk]
            try:
                data = self._get_json("/tweets", {"ids": ",".join(ids), **FIELDS})
            except FetchError as exc:
                errors.append(self._safe(str(exc)))
                break
            self._count(len(ids))
            left -= len(ids)
            looked += len(ids)
            rows = data.get("data", [])
            if "data" in data and not isinstance(rows, list):
                errors.append("unexpected lookup shape")
                break
            alive = {str(r.get("id")): r for r in rows if isinstance(r, dict)}
            for c in chunk:
                pid = c["id"].split(":", 1)[-1]
                if pid in alive:
                    text = alive[pid].get("text")
                    if isinstance(text, str):
                        res.updated[c["id"]] = excerpt(text)
                else:
                    res.removed_ids.add(c["id"])
            i += len(chunk)

        # 2) 新着の検索
        since = self.usage.setdefault("since_ids", {})
        for q in self.queries():
            if left < SEARCH_MIN:
                notes.append("budget exhausted before all queries")
                break
            params = {"query": q["q"], "max_results": min(SEARCH_MAX, left), **FIELDS}
            if since.get(q["key"]):
                params["since_id"] = since[q["key"]]
            try:
                data = self._get_json("/tweets/search/recent", params)
            except FetchError as exc:
                errors.append(self._safe(str(exc)))
                continue
            rows = data.get("data", [])
            if not isinstance(rows, list):
                errors.append("unexpected search shape")
                continue
            rows = [r for r in rows if isinstance(r, dict)][:left]
            users = {}
            inc = data.get("includes", {})
            for u in inc.get("users", []) if isinstance(inc, dict) and isinstance(inc.get("users"), list) else []:
                if isinstance(u, dict) and u.get("id") and u.get("username"):
                    users[str(u["id"])] = str(u["username"])
            self._count(len(rows))
            left -= len(rows)
            searched += len(rows)
            newest = since.get(q["key"], "0")
            for r in rows:
                pid = str(r.get("id", ""))
                handle = users.get(str(r.get("author_id")), "")
                if not pid.isdigit() or not handle or not handle.replace("_", "").isalnum():
                    continue
                text = r.get("text") if isinstance(r.get("text"), str) else ""
                ex = excerpt(text)
                published = _parse_x_date(r.get("created_at")) or iso(self.now)
                res.new_items.append(make_item(
                    item_id=f"x:{pid}", tab=q["tab"], kind="x", source_id="x", source="X",
                    title=ex[:80] or f"@{handle} の投稿", url=f"https://x.com/{handle}/status/{pid}",
                    published=published, exc=ex, tags=auto_tags(ex, q["tags"]), now=self.now, handle=handle,
                ))
                if _newer(pid, newest):
                    newest = pid
            if newest != "0":
                since[q["key"]] = newest

        res.status.update({
            "ok": not errors, "looked_up": looked, "searched": searched, "removed": len(res.removed_ids),
            "used_month": self.used_this_month(), "month_budget": self.cfg["monthly_post_budget"],
            **({"error": "; ".join(errors)[:300]} if errors else {}),
            **({"note": "; ".join(notes)} if notes else {}),
        })
        return res

    def _safe(self, text: str) -> str:
        return redact(text, [self.token or ""])[:200]


def _parse_x_date(value) -> str | None:
    return parse_date(value) if isinstance(value, str) else None
