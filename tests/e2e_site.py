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

    b.close()

check("console errors / page errors 0", not errors, f"{errors}")
bad = [r for r in results if not r[1]]
print("\nERRORS:", errors)
print("RESULT:", "ALL PASS" if not bad else f"{len(bad)} FAIL")
sys.exit(1 if bad else 0)
