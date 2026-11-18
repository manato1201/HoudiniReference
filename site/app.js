/* HoudiniReference — 静的サイト。data/items.json を読む。データ中の文字列は必ず textContent で入れる(innerHTML は使わない)。 */
(function () {
  "use strict";

  var TABS = ["news", "tips", "reference"];
  var X_NOTE = "X の投稿は削除・変更されることがあります。元の投稿で確認してください。";
  var KIND_LABEL = { rss: "Web", youtube: "YouTube", x: "X" };
  /* 関連サイト(フッター)。URL はここ 1 か所だけ。自サイトの url はデプロイ後に埋める(空なら名前だけ出す)。
     自サイトは self: true または url の origin が現在地と一致する時に「いま見ているサイト」として出し、リンクにしない。 */
  var RELATED_SITES = [
    { name: "HoudiniReference", url: "https://houdini-reference.vercel.app", self: true },
    { name: "The-Algorithm-Illustrated", url: "https://the-algorithm-illustrated.vercel.app" },
    { name: "FoundationsEncyclopedia", url: "https://foundations-encyclopedia.vercel.app" },
    { name: "ColorEncyclopedia", url: "https://color-encyclopedia.vercel.app" }
  ];
  var FAV_KEY = "hr.fav", THEME_KEY = "hr.theme";

  var state = { items: [], sources: [], refs: null, generated: null, loaded: false, failed: false,
                tab: "news", q: "", kind: "", source: "", period: 0, favOnly: false, favs: {} };
  var $ = function (id) { return document.getElementById(id); };

  /* ---- localStorage(読み書きは try/catch。無くても動く) ---- */
  function lsGet(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { window.localStorage.setItem(k, v); return true; } catch (e) { return false; } }
  function loadFavs() {
    var raw = lsGet(FAV_KEY), obj = {};
    try { obj = raw ? JSON.parse(raw) : {}; } catch (e) { obj = {}; }
    state.favs = (obj && typeof obj === "object" && !Array.isArray(obj)) ? obj : {};
  }
  function saveFavs() { lsSet(FAV_KEY, JSON.stringify(state.favs)); }

  /* ---- テーマ ---- */
  function currentTheme() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    $("theme").textContent = t === "dark" ? "ライトにする" : "ダークにする";
  }

  /* ---- ユーティリティ ---- */
  function safeHref(u) {
    try { var p = new URL(u, location.href); return (p.protocol === "https:" || p.protocol === "http:") ? p.href : null; }
    catch (e) { return null; }
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function fmtDate(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function fmtDateTime(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "不明";
    return fmtDate(iso) + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  /* ---- データ読み込み ---- */
  function fetchJson(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function load() {
    var items = fetchJson("data/items.json").then(function (d) {
      if (!d || !Array.isArray(d.items)) throw new Error("bad shape");
      state.items = d.items.filter(function (i) { return i && typeof i.id === "string" && typeof i.title === "string" && TABS.indexOf(i.tab) >= 0; });
      state.sources = Array.isArray(d.sources) ? d.sources : [];
      state.generated = d.generated_at || null;
    });
    var refs = fetchJson("data/reference.json").then(function (d) { state.refs = d; }).catch(function () { state.refs = null; });
    return Promise.all([items.catch(function () { state.failed = true; }), refs]).then(function () { state.loaded = true; });
  }

  /* ---- 絞り込み ---- */
  function haystack(i) { return (i.title + " " + (i.excerpt || "") + " " + (i.source || "") + " " + (i.handle || "") + " " + (i.tags || []).join(" ")).toLowerCase(); }
  function allForTab() {
    var byId = {}, list = [];
    state.items.forEach(function (i) { byId[i.id] = true; if (i.tab === state.tab) list.push(i); });
    if (state.favOnly) {   // データから消えた項目も、保存したスナップショットで残す
      Object.keys(state.favs).forEach(function (id) {
        var s = state.favs[id];
        if (!byId[id] && s && s.tab === state.tab && typeof s.title === "string") list.push(s);
      });
    }
    return list;
  }
  function filtered() {
    var terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    var minTime = state.period ? Date.now() - state.period * 86400000 : 0;
    return allForTab().filter(function (i) {
      if (state.favOnly && !state.favs[i.id]) return false;
      if (state.kind && i.kind !== state.kind) return false;
      if (state.source && i.source !== state.source) return false;
      if (minTime && new Date(i.published).getTime() < minTime) return false;
      var h = haystack(i);
      return terms.every(function (t) { return h.indexOf(t) >= 0; });
    }).sort(function (a, b) { return String(b.published).localeCompare(String(a.published)); });
  }

  /* ---- 描画 ---- */
  function card(i) {
    var li = el("li", "card");
    var meta = el("div", "meta");
    meta.appendChild(el("span", "badge " + (KIND_LABEL[i.kind] ? i.kind : "rss"), KIND_LABEL[i.kind] || "Web"));
    meta.appendChild(el("span", "src", i.source || ""));
    if (i.kind === "x" && i.handle) meta.appendChild(el("span", "mono", "@" + i.handle));
    var d = fmtDate(i.published);
    if (d) { var t = el("time", "mono", d); t.setAttribute("datetime", i.published); meta.appendChild(t); }
    li.appendChild(meta);

    var href = safeHref(i.url);
    var h = el("h3");
    if (href) {
      var a = el("a", null, i.title);
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      h.appendChild(a);
    } else { h.textContent = i.title; }
    if (i.kind !== "x") li.appendChild(h);   // X は本文(抜粋)が題名の代わり

    if (i.excerpt) li.appendChild(el("p", "ex", i.excerpt));
    if (i.kind === "x") {
      if (href) { var p = el("p", "ex"), a2 = el("a", null, "元の投稿を開く"); a2.href = href; a2.target = "_blank"; a2.rel = "noopener noreferrer"; p.appendChild(a2); li.appendChild(p); }
      li.appendChild(el("p", "xnote", X_NOTE));
    }

    var row = el("div", "foot-row");
    var tags = el("div", "tags");
    (i.tags || []).forEach(function (tg) { tags.appendChild(el("span", "tag", String(tg))); });
    row.appendChild(tags);
    var fav = el("button", "fav", state.favs[i.id] ? "★" : "☆");
    fav.type = "button";
    fav.setAttribute("aria-pressed", state.favs[i.id] ? "true" : "false");
    fav.setAttribute("aria-label", "お気に入り: " + i.title);
    fav.addEventListener("click", function () { toggleFav(i); });
    row.appendChild(fav);
    li.appendChild(row);
    return li;
  }

  function toggleFav(i) {
    if (state.favs[i.id]) { delete state.favs[i.id]; }
    else { state.favs[i.id] = { id: i.id, tab: i.tab, kind: i.kind, source: i.source, handle: i.handle || "", title: i.title, url: i.url, published: i.published, excerpt: i.excerpt || "", tags: i.tags || [] }; }
    saveFavs();
    render(false);
  }

  function renderRefs() {
    var box = $("refs");
    clear(box);
    var show = state.tab === "reference" && state.refs && Array.isArray(state.refs.groups);
    box.hidden = !show;
    if (!show) return;
    var terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    var any = false;
    state.refs.groups.forEach(function (g) {
      var links = (g.links || []).filter(function (l) {
        var h = ((l.title || "") + " " + (l.note || "") + " " + (g.title || "")).toLowerCase();
        return !state.kind && !state.source && !state.favOnly && terms.every(function (t) { return h.indexOf(t) >= 0; });
      });
      if (!links.length) return;
      any = true;
      var sec = el("div");
      sec.appendChild(el("h2", null, g.title || ""));
      var ul = el("ul");
      links.forEach(function (l) {
        var href = safeHref(l.url);
        if (!href) return;
        var li = el("li"), a = el("a");
        a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
        a.appendChild(el("span", "t", l.title || href));
        a.appendChild(el("span", "n", l.note || ""));
        li.appendChild(a); ul.appendChild(li);
      });
      sec.appendChild(ul); box.appendChild(sec);
    });
    if (!any) box.hidden = true;
  }

  function emptyState(kind) {
    var box = $("empty");
    clear(box);
    box.hidden = !kind;
    if (!kind) return;
    var strong = el("strong");
    if (kind === "failed") {
      strong.textContent = "データを読み込めませんでした";
      box.appendChild(strong);
      box.appendChild(el("span", null, "data/items.json が見つからない、または壊れています。収集を実行してください: "));
      box.appendChild(el("code", null, "python -m collector"));
    } else if (kind === "nodata") {
      strong.textContent = "まだデータがありません";
      box.appendChild(strong);
      box.appendChild(el("span", null, "収集を実行すると、ここに並びます: "));
      box.appendChild(el("code", null, "python -m collector"));
    } else {
      strong.textContent = state.favOnly ? "お気に入りはまだありません" : "条件に合う項目がありません";
      box.appendChild(strong);
      box.appendChild(el("span", null, state.favOnly ? "各項目の ☆ で追加できます。" : "検索語や絞り込みを変えてみてください。"));
      var b = el("button", "btn", "絞り込みを解除");
      b.type = "button";
      b.addEventListener("click", resetFilters);
      box.appendChild(el("div")).appendChild(b);
    }
  }

  function render(intro) {
    // タブ
    TABS.forEach(function (t) {
      var b = $("tab-" + t);
      b.setAttribute("aria-selected", t === state.tab ? "true" : "false");
      b.tabIndex = t === state.tab ? 0 : -1;
      var n = state.items.filter(function (i) { return i.tab === t; }).length;
      document.querySelector('[data-count="' + t + '"]').textContent = state.loaded && !state.failed ? String(n) : "";
    });
    $("list").setAttribute("aria-labelledby", "tab-" + state.tab);

    // 出典の選択肢(現在のタブにあるもの)
    var sel = $("source"), cur = state.source, names = {};
    state.items.forEach(function (i) { if (i.tab === state.tab) names[i.source] = true; });
    if (cur && !names[cur]) { cur = ""; state.source = ""; }
    clear(sel);
    var o0 = el("option", null, "すべて"); o0.value = ""; sel.appendChild(o0);
    Object.keys(names).sort().forEach(function (n) { var o = el("option", null, n); o.value = n; sel.appendChild(o); });
    sel.value = cur;

    // 種別・お気に入りボタン
    Array.prototype.forEach.call($("kind").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-kind") === state.kind ? "true" : "false");
    });
    var fb = $("favonly");
    fb.setAttribute("aria-pressed", state.favOnly ? "true" : "false");
    fb.textContent = (state.favOnly ? "★" : "☆") + " お気に入りのみ";

    renderRefs();
    $("refs").className = "refs" + (intro ? " intro" : "");

    var list = $("list");
    clear(list);
    list.className = "list" + (intro ? " intro" : "");
    if (state.failed) { emptyState("failed"); $("status").textContent = ""; return; }
    if (!state.items.length) { emptyState("nodata"); $("status").textContent = ""; return; }

    var rows = filtered();
    // リファレンスタブは「リリースノートの新着」の見出しを付ける
    var frag = document.createDocumentFragment();
    rows.forEach(function (i) { frag.appendChild(card(i)); });
    list.appendChild(frag);
    var total = allForTab().length;
    $("status").textContent = rows.length + " 件" + (rows.length !== total ? "(全 " + total + " 件中)" : "") +
      (state.tab === "reference" ? " — リリースノートの新着" : "");
    emptyState(rows.length ? null : "none");
  }

  function resetFilters() {
    state.q = ""; state.kind = ""; state.source = ""; state.period = 0; state.favOnly = false;
    $("q").value = ""; $("period").value = "0";
    render(false);
  }

  function isCurrentSite(site) {
    if (site.self) return true;
    try { return !!site.url && new URL(site.url).origin === location.origin; } catch (e) { return false; }
  }
  function renderRelated() {
    var ul = $("related-list");
    clear(ul);
    RELATED_SITES.forEach(function (site) {
      var li = el("li");
      var href = safeHref(site.url);
      if (isCurrentSite(site)) {
        var cur = el("span", "rel-item rel-current", site.name);
        cur.setAttribute("aria-current", "true");
        li.appendChild(cur);
        li.appendChild(el("span", "rel-note", "いま見ているサイト"));
      } else if (href) {
        var a = el("a", "rel-item rel-link", site.name);
        a.href = href; a.rel = "noopener";
        li.appendChild(a);
      } else {
        li.appendChild(el("span", "rel-item", site.name));
      }
      ul.appendChild(li);
    });
  }

  function renderHealth() {
    var ul = $("health-list");
    clear(ul);
    if (!state.sources.length) { ul.appendChild(el("li", null, "情報がありません")); return; }
    state.sources.forEach(function (s) {
      var li = el("li");
      var label = s.ok === true ? "取得 OK" : s.ok === false ? "失敗: " + (s.error || "") : "スキップ: " + (s.skipped || "");
      li.appendChild(el("span", s.ok === false ? "ng" : "ok", s.name + " — " + label));
      if (s.last_ok) li.appendChild(el("span", null, "(最後に成功 " + fmtDateTime(s.last_ok) + ")"));
      ul.appendChild(li);
    });
  }

  function renderHeader() {
    $("updated").textContent = "最終更新 " + (state.generated ? fmtDateTime(state.generated) : "—");
    var n = $("stale");
    var age = state.generated ? (Date.now() - new Date(state.generated).getTime()) / 86400000 : null;
    var failed = state.sources.filter(function (s) { return s.ok === false; });
    var msgs = [];
    if (age !== null && age > 3) msgs.push("データが " + Math.floor(age) + " 日前のものです。収集が止まっている可能性があります。");
    if (failed.length) msgs.push("取得に失敗した情報源: " + failed.map(function (s) { return s.name; }).join("、") + "(古いデータを残しています)");
    n.hidden = msgs.length === 0;
    n.textContent = msgs.join(" ");
  }

  /* ---- 操作 ---- */
  function setTab(t, focus) {
    if (TABS.indexOf(t) < 0) t = "news";
    state.tab = t; state.source = "";
    if (location.hash !== "#" + t) { try { history.replaceState(null, "", "#" + t); } catch (e) { /* 無視 */ } }
    render(false);
    if (focus) $("tab-" + t).focus();
  }

  function bind() {
    TABS.forEach(function (t, idx) {
      var b = $("tab-" + t);
      b.addEventListener("click", function () { setTab(t, false); });
      b.addEventListener("keydown", function (e) {
        var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (d) { e.preventDefault(); setTab(TABS[(idx + d + TABS.length) % TABS.length], true); }
      });
    });
    $("q").addEventListener("input", function (e) { state.q = e.target.value; render(false); });
    $("source").addEventListener("change", function (e) { state.source = e.target.value; render(false); });
    $("period").addEventListener("change", function (e) { state.period = parseInt(e.target.value, 10) || 0; render(false); });
    Array.prototype.forEach.call($("kind").querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { state.kind = b.getAttribute("data-kind") || ""; render(false); });
    });
    $("favonly").addEventListener("click", function () { state.favOnly = !state.favOnly; render(false); });
    $("theme").addEventListener("click", function () {
      var t = currentTheme() === "dark" ? "light" : "dark";
      applyTheme(t); lsSet(THEME_KEY, t);
    });
    window.addEventListener("hashchange", function () { setTab(location.hash.slice(1), false); });
  }

  function init() {
    var saved = lsGet(THEME_KEY);
    applyTheme(saved === "dark" || saved === "light" ? saved : currentTheme());
    loadFavs();
    bind();
    renderRelated();
    var h = location.hash.slice(1);
    state.tab = TABS.indexOf(h) >= 0 ? h : "news";
    load().then(function () {
      renderHeader(); renderHealth();
      render(true);
    });
  }

  init();
})();
