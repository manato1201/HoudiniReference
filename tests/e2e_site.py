"""Playwright による画面検証(任意。playwright は本プロジェクトの依存ではない)。
使い方: python -m http.server 8765 --directory site  を起動してから  python tests/e2e_site.py [撮影先]"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765/index.html"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name, detail)


def page_with(ctx, errors):
    p = ctx.new_page()
    p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    p.on("pageerror", lambda e: errors.append(str(e)))
    return p


with sync_playwright() as pw:
    b = pw.chromium.launch()
    errors = []
    ctx = b.new_context(viewport={"width": 1200, "height": 900})
    p = page_with(ctx, errors)
    p.goto(BASE)
    p.wait_for_selector("#list .card")

    # (1) 3 タブ
    counts = {}
    for t in ("news", "tips", "reference"):
        p.click(f"#tab-{t}")
        sel = p.get_attribute(f"#tab-{t}", "aria-selected")
        n = p.locator("#list .card").count()
        counts[t] = n
        check(f"tab {t}", sel == "true" and n > 0 and p.evaluate("location.hash") == f"#{t}", f"{n} cards")
    check("reference link group visible", p.locator("#refs a").count() >= 8 and not p.locator("#refs").is_hidden())
    p.click("#tab-news"); check("news hides refs", p.locator("#refs").is_hidden())
    p.keyboard.press("ArrowRight") if False else None

    # (2) 検索・絞り込み
    p.click("#tab-tips")
    total = p.locator("#list .card").count()
    p.fill("#q", "vellum")
    n = p.locator("#list .card").count()
    texts = [t.lower() for t in p.locator("#list .card").all_inner_texts()]
    check("search narrows", 0 < n < total and all("vellum" in t for t in texts), f"{total}->{n}")
    p.fill("#q", "zzzzqqq")
    check("search empty state", p.locator("#empty").is_visible() and "条件に合う" in p.inner_text("#empty"))
    p.click("#empty button")
    check("reset filters", p.locator("#list .card").count() == total and p.input_value("#q") == "")
    p.click('#kind button[data-kind="youtube"]')
    nyt = p.locator("#list .card").count()
    check("kind filter youtube", 0 < nyt < total and p.locator("#list .badge.youtube").count() == nyt, f"{nyt}")
    p.click('#kind button[data-kind="github"]')
    check("kind filter github has no cards in tips", p.locator("#list .card").count() == 0)
    p.click('#kind button[data-kind=""]')
    p.click("#tab-reference"); p.click('#kind button[data-kind="github"]')
    ngh = p.locator("#list .card").count()
    check("kind filter github (reference)", ngh > 0 and p.locator("#list .badge.github").count() == ngh, f"{ngh}")
    p.click('#kind button[data-kind=""]'); p.click("#tab-tips")
    # 言語の絞り込み・言語の表示
    p.click('#lang button[data-lang="ja"]')
    nja = p.locator("#list .card").count()
    check("lang filter ja", 0 < nja < total and p.locator("#list .lang").all_inner_texts() == ["JA"] * nja, f"{nja}/{total}")
    p.click('#lang button[data-lang="en"]')
    nen = p.locator("#list .card").count()
    check("lang filter en", 0 < nen < total and set(p.locator("#list .lang").all_inner_texts()) == {"EN"}, f"{nen}")
    check("lang filter partitions the tab", nja + nen == total, f"{nja}+{nen}={total}")
    p.click('#lang button[data-lang=""]')
    # 出典の選択肢は種別ごとのグループ
    groups = p.locator("#source optgroup").evaluate_all("els => els.map(e => e.label)")
    check("source options grouped by kind", groups[:2] == ["Web", "YouTube"], f"{groups}")
    p.select_option("#source", "Qiita #Houdini")
    check("source filter Qiita (ja)", p.locator("#list .card").count() > 0 and set(p.locator("#list .lang").all_inner_texts()) == {"JA"})
    p.select_option("#source", "")
    p.click('#kind button[data-kind="x"]')
    check("kind filter X (none stored) -> empty state", p.locator("#list .card").count() == 0 and p.locator("#empty").is_visible())
    p.click('#kind button[data-kind=""]')
    p.select_option("#source", "Entagma")
    n = p.locator("#list .card").count()
    check("source filter", n > 0 and all("Entagma" in t for t in p.locator("#list .src").all_inner_texts()), f"{n}")
    p.select_option("#source", "")
    p.select_option("#period", "7")
    n7 = p.locator("#list .card").count()
    check("period filter 7d", n7 < total, f"{n7}/{total}")
    p.select_option("#period", "0")

    # (3) お気に入り
    p.click("#tab-tips")
    title = p.locator("#list .card h3").first.inner_text()
    p.locator("#list .card .fav").first.click()
    p.reload(); p.wait_for_selector("#list .card")
    p.click("#tab-tips")
    p.click("#favonly")
    favs = p.locator("#list .card h3").all_inner_texts()
    check("favorite persists across reload", favs == [title], f"{favs}")
    p.click("#favonly")
    p.fill("#q", "")
    # お気に入り解除
    p.click("#favonly"); p.locator("#list .card .fav").first.click()
    check("favorite removed -> empty", p.locator("#empty").is_visible() and "お気に入りはまだ" in p.inner_text("#empty"))
    p.click("#favonly")

    # テーマ
    p.click("#theme"); th1 = p.get_attribute("html", "data-theme")
    p.reload(); p.wait_for_selector("#list .card")
    check("theme persists", p.get_attribute("html", "data-theme") == th1, th1)

    # 通常の動き(1 回きり)
    p.click("#theme")
    p.evaluate("localStorage.setItem('hr.theme','light')")
    p.reload(); p.wait_for_selector("#list .card")
    name = p.evaluate("getComputedStyle(document.querySelector('#list .card')).animationName")
    iters = p.evaluate("getComputedStyle(document.querySelector('#list .card')).animationIterationCount")
    check("motion: one-shot rise", name == "rise" and iters == "1", f"{name} x{iters}")

    # 関連サイト(フッター)
    rel = p.locator("#related-list a")
    hrefs = [rel.nth(i).get_attribute("href").rstrip("/") for i in range(rel.count())]
    check("related: 3 links with the right URLs", hrefs == ["https://the-algorithm-illustrated.vercel.app", "https://foundations-encyclopedia.vercel.app", "https://color-encyclopedia.vercel.app"], f"{hrefs}")
    check("related: rel=noopener, same tab", all(rel.nth(i).get_attribute("rel") == "noopener" and rel.nth(i).get_attribute("target") is None for i in range(rel.count())))
    check("related: no takayustudio link", p.locator("a[href*='takayustudio']").count() == 0)
    cur = p.locator("#related-list [aria-current]")
    check("related: self is aria-current, not a link", cur.count() == 1 and "HoudiniReference" in cur.inner_text() and cur.evaluate("n => n.tagName") == "SPAN" and p.locator("#related-list a", has_text="HoudiniReference").count() == 0)
    check("related: storage note", "お気に入り・テーマ・設定はサイトごとに別々に保存され、共有されません。" in p.inner_text("footer .related"))
    check("related: no motion", p.evaluate("getComputedStyle(document.querySelector('.related-list a')).transitionDuration") in ("0s", "0.0s"))

    # 撮影
    for theme in ("light", "dark"):
        for w, h in ((390, 844), (1200, 900), (1900, 1000)):
            ctx2 = b.new_context(viewport={"width": w, "height": h}, color_scheme=theme)
            p2 = page_with(ctx2, errors)
            p2.goto(BASE + "#tips"); p2.wait_for_selector("#list .card"); p2.wait_for_timeout(700)
            overflow = p2.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            check(f"no horizontal scroll {theme} {w}", not overflow)
            p2.locator("footer .related").scroll_into_view_if_needed()
            check(f"related footer visible {theme} {w}", p2.locator("footer .related").is_visible() and p2.evaluate("(() => { const r = document.querySelector('footer .related').getBoundingClientRect(); return r.left >= 0 && r.right <= document.documentElement.clientWidth; })()"))
            p2.locator("footer").screenshot(path=str(OUT / f"shot_{theme}_{w}_footer.png"))
            p2.screenshot(path=str(OUT / f"shot_{theme}_{w}_tips.png"))
            if w in (390, 1200):
                p2.goto(BASE + "#reference"); p2.wait_for_selector("#list .card"); p2.wait_for_timeout(700)
                p2.screenshot(path=str(OUT / f"shot_{theme}_{w}_reference.png"))
            ctx2.close()

    # (5) reduced motion
    ctx3 = b.new_context(reduced_motion="reduce")
    p3 = page_with(ctx3, errors)
    p3.goto(BASE); p3.wait_for_selector("#list .card")
    name = p3.evaluate("getComputedStyle(document.querySelector('#list .card')).animationName")
    check("reduced-motion stops animation", name == "none", name)
    ctx3.close()

    # (4) エンプティステート
    real_errors = list(errors)
    for label, handler, expect in (
        ("empty data", lambda r: r.fulfill(json=json.loads('{"schema_version":1,"generated_at":"2026-11-18T00:00:00Z","sources":[],"items":[]}')), "まだデータがありません"),
        ("load failure", lambda r: r.fulfill(status=404, body="nf"), "読み込めませんでした"),
        ("broken json", lambda r: r.fulfill(status=200, body="{bad", content_type="application/json"), "読み込めませんでした"),
    ):
        ctx4 = b.new_context(); p4 = ctx4.new_page()
        p4.route("**/data/items.json", handler)
        p4.goto(BASE); p4.wait_for_selector("#empty:not([hidden])")
        check(f"empty state: {label}", expect in p4.inner_text("#empty") and p4.locator("#list .card").count() == 0)
        ctx4.close()

    # XSS: データ中の HTML は文字列のまま表示、javascript: はリンクにしない
    evil = {"schema_version": 1, "generated_at": "2026-11-18T00:00:00Z", "sources": [{"id": "e", "name": "<b>E</b>", "ok": False, "error": "<img src=x onerror=window.__x=1>"}],
            "items": [{"id": "e1", "tab": "news", "kind": "rss", "source": "<img src=x onerror=window.__x=1>", "title": "<img src=x onerror=window.__x=1><script>window.__x=1</script>",
                       "url": "javascript:window.__x=1", "published": "2026-11-17T00:00:00Z", "excerpt": "<b>bold</b>", "tags": ["<i>t</i>"]},
                      {"id": "e2", "tab": "news", "kind": "x", "source": "X", "handle": "h", "title": "t", "url": "https://x.com/h/status/1", "published": "2026-11-17T00:00:00Z", "excerpt": "hello", "tags": []}]}
    ctx5 = b.new_context(); p5 = page_with(ctx5, errors)
    p5.route("**/data/items.json", lambda r: r.fulfill(json=evil))
    p5.goto(BASE); p5.wait_for_selector("#list .card")
    check("xss: no injected elements", p5.locator("#list img, #list script, #list b, #list i, #health-list b, #health-list img").count() == 0 and p5.evaluate("window.__x") is None)
    check("xss: javascript: url not linked", p5.locator("#list a[href^='javascript']").count() == 0 and p5.locator("#list .card").first.locator("h3 a").count() == 0)
    check("X item: note + original link + handle", "削除・変更されることがあります" in p5.inner_text("#list") and p5.locator("#list a[rel='noopener noreferrer']").count() >= 1 and "@h" in p5.inner_text("#list"))
    ctx5.close()
    check("links have rel noopener noreferrer", p.locator("#list a:not([rel='noopener noreferrer'])").count() == 0)

    # (C1) サムネ・再生数・人気順・グリッド/リスト・プレビュー枠
    PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")
    def yt(i, vid, views, title, pub):
        it = {"id": f"yt:{vid}", "tab": "tips", "kind": "youtube", "source": "Chan", "source_id": "youtube-x", "title": title,
              "url": f"https://www.youtube.com/watch?v={vid}", "published": pub, "excerpt": "e", "tags": ["YouTube"], "lang": "en"}
        if views is not None:
            it["views"] = views
        return it
    vids = [("AAAAAAAAAAA", 1200, "Low", "2026-11-10T00:00:00Z"), ("BBBBBBBBBBB", 345678, "High", "2026-11-01T00:00:00Z"),
            ("CCCCCCCCCCC", None, "NoViews", "2026-11-18T00:00:00Z"), ("DDDDDDDDDDD", 99999999, "Huge", "2026-10-01T00:00:00Z")]
    c1 = {"schema_version": 1, "generated_at": "2026-11-19T00:00:00Z", "sources": [],
          "items": [yt(n, *v) for n, v in enumerate(vids)] + [
              {"id": "yt:bad", "tab": "tips", "kind": "youtube", "source": "Bad", "title": "BadId", "url": "https://www.youtube.com/watch?v=bad", "published": "2026-11-17T00:00:00Z", "excerpt": "", "tags": []},
              {"id": "yt:\"onerror=1", "tab": "tips", "kind": "youtube", "source": "Evil", "title": "EvilId", "url": "https://www.youtube.com/watch?v=x", "published": "2026-11-16T00:00:00Z", "excerpt": "", "tags": []},
              {"id": "w1", "tab": "tips", "kind": "rss", "source": "Qiita", "title": "WebPost", "url": "https://example.com/w", "published": "2026-11-15T00:00:00Z", "excerpt": "x", "tags": []}]}
    def c1_page(width, fail_images=False, scheme="light"):
        cx = b.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
        pg = page_with(cx, [] if fail_images else errors)  # 画像を意図的に失敗させる回の net::ERR は期待どおりなので数えない
        pg.route("**/data/items.json", lambda r: r.fulfill(json=c1))
        if fail_images:
            pg.route("https://i.ytimg.com/**", lambda r: r.abort())
        else:
            pg.route("https://i.ytimg.com/**", lambda r: r.fulfill(status=200, body=PNG, content_type="image/png"))
        pg.route("https://www.youtube-nocookie.com/**", lambda r: r.fulfill(status=200, body="<html><body>player stub</body></html>", content_type="text/html"))
        return cx, pg
    cx, pg = c1_page(1200)
    pg.goto(BASE + "#tips"); pg.wait_for_selector("#list .card")
    check("c1: no iframe before pressing", pg.locator("iframe").count() == 0)
    srcs = pg.locator("#list .thumb img").evaluate_all("els => els.map(e => e.getAttribute('src'))")
    check("c1: thumb URLs are built from yt id (only valid ids)", sorted(srcs) == sorted(f"https://i.ytimg.com/vi/{v[0]}/mqdefault.jpg" for v in vids), f"{srcs}")
    check("c1: thumb img lazy + empty alt", pg.locator("#list .thumb img[loading='lazy'][alt='']").count() == len(vids))
    check("c1: invalid ids have no img and no preview button", pg.locator("#list .card", has_text="BadId").locator("img, .thumb-btn, .pv-btn").count() == 0 and pg.locator("#list .card", has_text="EvilId").locator("img, .thumb-btn, .pv-btn").count() == 0)
    heights = pg.evaluate("Array.from(document.querySelectorAll('#list .thumb')).map(t => Math.round(t.getBoundingClientRect().height))")
    check("c1: all thumb frames same height (yt, placeholder)", len(set(heights)) == 1 and heights[0] > 50, f"{set(heights)}")
    check("c1: placeholder initial shown for non-YouTube", pg.locator("#list .card", has_text="WebPost").locator(".thumb .ph").inner_text() == "Q")
    vt = pg.locator("#list .views").all_inner_texts()
    check("c1: views formatted", sorted(vt) == sorted(["1200 回視聴", "34.6万 回視聴", "1億 回視聴"]), f"{vt}")
    order_new = pg.locator("#list .card h3").all_inner_texts()
    check("c1: default order = newest first", order_new[0] == "NoViews", f"{order_new}")
    pg.select_option("#sort", "popular")
    order_pop = pg.locator("#list .card h3").all_inner_texts()
    check("c1: popular order = views desc, no-views last", order_pop[:4] == ["Huge", "High", "Low", "NoViews"], f"{order_pop}")
    pg.select_option("#sort", "new")
    pg.click('#view button[data-view="list"]')
    check("c1: list view", "view-list" in pg.get_attribute("#list", "class") and pg.get_attribute('#view button[data-view="list"]', "aria-pressed") == "true")
    pg.reload(); pg.wait_for_selector("#list .card")
    check("c1: view persists", "view-list" in pg.get_attribute("#list", "class"))
    pg.click('#view button[data-view="grid"]')
    # プレビュー
    pg.select_option("#sort", "popular")
    pg.locator("#list .card", has_text="High").locator(".thumb-btn").click()
    pg.wait_for_selector("#preview[open]")
    ifr = pg.locator("#preview iframe")
    isrc = ifr.get_attribute("src")
    check("c1: iframe created on press with nocookie embed, no autoplay", ifr.count() == 1 and isrc == "https://www.youtube-nocookie.com/embed/BBBBBBBBBBB" and "autoplay" not in isrc, f"{isrc}")
    check("c1: iframe attrs (referrerpolicy, minimal allow)", ifr.get_attribute("referrerpolicy") == "strict-origin-when-cross-origin" and "autoplay" not in (ifr.get_attribute("allow") or ""))
    check("c1: preview shows original link + title", pg.get_attribute("#pv-open", "href") == "https://www.youtube.com/watch?v=BBBBBBBBBBB" and pg.inner_text("#pv-title") == "High")
    check("c1: prev enabled/next enabled (2nd of 3 previewable in popular order)", pg.inner_text("#pv-pos") == "2 / 4" and not pg.is_disabled("#pv-prev") and not pg.is_disabled("#pv-next"), pg.inner_text("#pv-pos"))
    pg.click("#pv-next")
    check("c1: next switches video & replaces iframe", pg.locator("#preview iframe").count() == 1 and pg.get_attribute("#preview iframe", "src").endswith("AAAAAAAAAAA") and pg.inner_text("#pv-title") == "Low")
    pg.click("#pv-next")
    check("c1: last item disables next", pg.is_disabled("#pv-next") and pg.inner_text("#pv-pos") == "4 / 4")
    pg.click("#pv-fav")
    check("c1: favorite from preview", pg.get_attribute("#pv-fav", "aria-pressed") == "true")
    pg.keyboard.press("Escape")
    pg.wait_for_function("!document.getElementById('preview').open")
    pg.wait_for_function("document.querySelectorAll('iframe').length === 0", timeout=2000)
    check("c1: Esc closes and destroys iframe", pg.locator("iframe").count() == 0)
    pg.locator("#list .card", has_text="Low").locator(".pv-btn").click()
    pg.wait_for_selector("#preview[open]"); pg.click("#pv-close"); pg.wait_for_function("!document.getElementById('preview').open")
    check("c1: close button destroys iframe", pg.locator("iframe").count() == 0 and not pg.evaluate("document.getElementById('preview').open"))
    # 先頭で前へが無効
    pg.locator("#list .card").first.locator(".thumb-btn").click(); pg.wait_for_selector("#preview[open]")
    check("c1: first item disables prev", pg.is_disabled("#pv-prev") and pg.inner_text("#pv-pos").startswith("1 /"))
    pg.keyboard.press("Escape")
    cx.close()
    # 読み込み失敗でもサムネ枠の高さは変わらず、プレースホルダーが残る
    cx, pg = c1_page(1200, fail_images=True)
    pg.goto(BASE + "#tips"); pg.wait_for_selector("#list .card"); pg.wait_for_timeout(500)
    h2 = pg.evaluate("Array.from(document.querySelectorAll('#list .thumb')).map(t => Math.round(t.getBoundingClientRect().height))")
    check("c1: image load failure -> img removed, placeholder + same height", pg.locator("#list .thumb img").count() == 0 and len(set(h2)) == 1 and h2[0] == heights[0] and pg.locator("#list .thumb .ph").count() == len(c1["items"]), f"{set(h2)} vs {heights[0]}")
    cx.close()
    # 390px・ダークでも横スクロールなし(一覧・プレビュー)
    for theme in ("light", "dark"):
        cx, pg = c1_page(390, scheme=theme)
        pg.goto(BASE + "#tips"); pg.wait_for_selector("#list .card"); pg.wait_for_timeout(500)
        check(f"c1: no horizontal scroll 390 {theme}", not pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
        pg.screenshot(path=str(OUT / f"c1_{theme}_390_grid.png"))
        pg.locator("#list .thumb-btn").first.click(); pg.wait_for_selector("#preview[open]"); pg.wait_for_timeout(300)
        check(f"c1: preview fits 390 {theme}", pg.evaluate("(() => { const r = document.getElementById('preview').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })()") and not pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
        pg.screenshot(path=str(OUT / f"c1_{theme}_390_preview.png"))
        cx.close()
    cx, pg = c1_page(1900)
    pg.goto(BASE + "#tips"); pg.wait_for_selector("#list .card"); pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT / "c1_light_1900_grid.png"))
    pg.click('#view button[data-view="list"]'); pg.screenshot(path=str(OUT / "c1_light_1900_list.png"))
    cx.close()

    # (C4) ノードタブ
    nodes_doc = json.loads((Path(__file__).resolve().parent.parent / "site" / "data" / "nodes.json").read_text(encoding="utf-8"))
    nn = nodes_doc["nodes"]
    by_ctx = {}
    for n_ in nn:
        by_ctx[n_["context"]] = by_ctx.get(n_["context"], 0) + 1
    cxn = b.new_context(viewport={"width": 1200, "height": 900})
    pn = page_with(cxn, errors)
    pn.goto(BASE + "#nodes"); pn.wait_for_selector("#nodes-panel .ncard")
    check("c4: nodes tab selected, hash, count", pn.get_attribute("#tab-nodes", "aria-selected") == "true" and pn.evaluate("location.hash") == "#nodes" and pn.inner_text('[data-count="nodes"]') == str(len(nn)), pn.inner_text('[data-count="nodes"]'))
    check("c4: list/filters hidden on nodes tab, panel visible", pn.locator("#list").is_hidden() and pn.locator("#filters").is_hidden() and pn.locator("#nodes-panel").is_visible())
    check("c4: all node cards shown", pn.locator("#nodes-panel .ncard").count() == len(nn) >= 30, f"{pn.locator('#nodes-panel .ncard').count()}")
    pn.locator('.nf-item', has_text="SOP").first.click()
    check("c4: context filter SOP count", pn.locator("#nodes-panel .ncard").count() == by_ctx["SOP"], f"{pn.locator('#nodes-panel .ncard').count()} vs {by_ctx['SOP']}")
    pn.locator('.nf-item', has_text="SOP").first.click()  # 解除
    pn.locator('.nf-item', has_text="VOP").first.click()
    check("c4: context filter VOP count", pn.locator("#nodes-panel .ncard").count() == by_ctx["VOP"])
    pn.locator('.nf-item', has_text="VOP").first.click()
    pn.fill("#nq", "scatter")
    n_s = pn.locator("#nodes-panel .ncard").count()
    check("c4: search narrows", 0 < n_s < len(nn) and "Scatter" in pn.locator("#nodes-panel .ncard-name").all_inner_texts(), f"{n_s}")
    pn.fill("#nq", "zzzzqqq")
    check("c4: search empty state", pn.locator("#nodes-panel .empty").is_visible() and pn.locator("#nodes-panel .ncard").count() == 0)
    pn.click("#nodes-panel .empty button")
    check("c4: reset restores all", pn.locator("#nodes-panel .ncard").count() == len(nn) and pn.input_value("#nq") == "")
    cat0 = nn[0]["category"]
    pn.locator(".n-group", has_text="カテゴリ").locator(".nf-item", has_text=cat0).first.click()
    check("c4: category filter", pn.locator("#nodes-panel .ncard").count() == sum(1 for x in nn if x["category"] == cat0))
    pn.locator(".n-group", has_text="カテゴリ").locator(".nf-item", has_text=cat0).first.click()
    # 詳細(6 項目・SVG の接続図・前後)
    pn.locator("#nodes-panel .ncard", has_text="Scatter").first.click()
    pn.wait_for_selector("#nodes-panel .ndetail")
    heads = pn.locator("#nodes-panel .nsec-h").all_inner_texts()
    check("c4: detail has the 6 sections", len(heads) == 6 and all(h.endswith(t) for h, t in zip(heads, ["何をするか", "どう使うか", "実例のポイント", "使いどころ", "他のノードとの組み合わせ例", "使う前と後の違い"])), f"{heads}")
    sc = next(x for x in nn if x["id"] == "scatter")
    svgs = pn.locator("#nodes-panel svg.chain")
    check("c4: chain SVG per combo, boxes = chain length", svgs.count() == len(sc["combos"]) and all(svgs.nth(i).locator("rect").count() == len(sc["combos"][i]["chain"]) for i in range(svgs.count())))
    check("c4: chain labels via textContent", svgs.first.locator("text").evaluate_all("els => els.map(e => e.textContent)") == sc["combos"][0]["chain"])
    check("c4: hash shows node id", pn.evaluate("location.hash") == "#nodes/scatter")
    doc = pn.locator("#nodes-panel .ndoc a")
    check("c4: official doc link (https, noopener)", doc.get_attribute("href").startswith("https://www.sidefx.com/docs/") and doc.get_attribute("rel") == "noopener noreferrer")
    check("c4: before/after images with alt", pn.locator("#nodes-panel .nba-img").count() == 2 and pn.locator("#nodes-panel .nba-img[alt='']").count() == 0)
    pn.wait_for_timeout(300)
    check("c4: images actually loaded", pn.evaluate("Array.from(document.querySelectorAll('.nba-img')).every(i => i.complete && i.naturalWidth > 0)"))
    i0 = [x["id"] for x in nn].index("scatter")
    pn.click("text=次のノード →")
    check("c4: next node", pn.evaluate("location.hash") == "#nodes/" + nn[i0 + 1]["id"] and pn.inner_text("#ndetail-title") == nn[i0 + 1]["name"])
    pn.click("text=← 一覧へ")
    check("c4: back to list", pn.locator("#nodes-panel .ncard").count() == len(nn) and pn.evaluate("location.hash") == "#nodes")
    pn.goto(BASE + "#nodes/grid"); pn.wait_for_selector("#nodes-panel .ndetail")
    check("c4: deep link opens detail", pn.inner_text("#ndetail-title") == "Grid")
    pn.goto(BASE + "#nodes/does-not-exist"); pn.wait_for_selector("#nodes-panel .ncard")
    check("c4: unknown id falls back to list", pn.locator("#nodes-panel .ncard").count() == len(nn))
    first_no_img = next(x for x in nn if "image" not in x["before_after"])
    pn.goto(BASE + "#nodes/" + first_no_img["id"]); pn.wait_for_selector("#nodes-panel .ndetail")
    check("c4: node without image still shows text before/after", pn.locator("#nodes-panel .nba-img").count() == 0 and first_no_img["before_after"]["after"] in pn.inner_text("#nodes-panel .nba"))
    pn.goto(BASE + "#news"); pn.wait_for_selector("#list .card")
    check("c4: other tabs unaffected (list visible, nodes hidden)", pn.locator("#list").is_visible() and pn.locator("#nodes-panel").is_hidden() and pn.locator("#filters").is_visible())
    cxn.close()
    # 390px・ライト/ダークで横スクロールなし(一覧・詳細)
    for theme in ("light", "dark"):
        for w in (390, 1200, 1900):
            cxm = b.new_context(viewport={"width": w, "height": 900}, color_scheme=theme)
            pm = page_with(cxm, errors)
            pm.goto(BASE + "#nodes"); pm.wait_for_selector("#nodes-panel .ncard"); pm.wait_for_timeout(300)
            check(f"c4: no horizontal scroll list {theme} {w}", not pm.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
            pm.screenshot(path=str(OUT / f"c4_{theme}_{w}_list.png"))
            pm.goto(BASE + "#nodes/polyextrude"); pm.wait_for_selector("#nodes-panel .ndetail"); pm.wait_for_timeout(400)
            check(f"c4: no horizontal scroll detail {theme} {w}", not pm.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
            pm.screenshot(path=str(OUT / f"c4_{theme}_{w}_detail.png"), full_page=True)
            cxm.close()
    # XSS・不正な URL
    evil_nodes = {"schema_version": 1, "nodes": [{"id": "e1", "name": "<img src=x onerror=window.__n=1>", "type": "<b>t</b>", "context": "SOP", "category": "<i>c</i>", "what": "<script>window.__n=1</script>", "how": "h",
                  "example_points": ["<b>x</b>", "y"], "use_cases": ["<img src=x onerror=window.__n=1>", "z"], "combos": [{"title": "<b>t</b>", "chain": ["<img src=x onerror=window.__n=1>", "B"], "note": "<i>n</i>"}],
                  "before_after": {"before": "<b>b</b>", "after": "a", "image": {"before": "https://evil.example/x.svg", "after": "img/nodes/../../secret.svg", "alt": "<b>alt</b>"}},
                  "params": [{"name": "<b>p</b>", "note": "<i>n</i>"}], "doc_url": "javascript:window.__n=1", "verified": False}]}
    cxe = b.new_context(); pe = page_with(cxe, errors)
    pe.route("**/data/nodes.json", lambda r: r.fulfill(json=evil_nodes))
    pe.goto(BASE + "#nodes/e1"); pe.wait_for_selector("#nodes-panel .ndetail")
    check("c4 xss: no injected elements", pe.locator("#nodes-panel img, #nodes-panel script, #nodes-panel b, #nodes-panel i").count() == 0 and pe.evaluate("window.__n") is None)
    check("c4 xss: javascript: doc_url not linked; external/.. image paths rejected", pe.locator("#nodes-panel a[href^='javascript']").count() == 0 and pe.locator("#nodes-panel .ndoc a").count() == 0 and pe.locator("#nodes-panel .nba-img").count() == 0)
    check("c4 xss: unverified badge shown", "未確認" in pe.inner_text("#nodes-panel .nverified"))
    cxe.close()
    cxf = b.new_context(); pf = cxf.new_page()
    pf.route("**/data/nodes.json", lambda r: r.fulfill(status=404, body="nf"))
    pf.goto(BASE + "#nodes"); pf.wait_for_selector("#nodes-panel .empty")
    check("c4: nodes.json load failure -> message, other tabs still work", "読み込めませんでした" in pf.inner_text("#nodes-panel") and pf.locator("#tab-tips").is_enabled())
    cxf.close()

    b.close()

check("console errors / page errors 0", not errors, f"{errors}")
bad = [r for r in results if not r[1]]
print("\nERRORS:", errors)
print("RESULT:", "ALL PASS" if not bad else f"{len(bad)} FAIL")
sys.exit(1 if bad else 0)
