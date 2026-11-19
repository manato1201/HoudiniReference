/* HoudiniReference — 静的サイト。data/items.json を読む。データ中の文字列は必ず textContent で入れる(innerHTML は使わない)。 */
(function () {
  "use strict";

  var TABS = ["news", "tips", "reference", "nodes"];
  var X_NOTE = "X の投稿は削除・変更されることがあります。元の投稿で確認してください。";
  var KIND_LABEL = { rss: "Web", youtube: "YouTube", github: "GitHub", x: "X" };
  var LANG_LABEL = { ja: "JA", en: "EN" };
  /* 関連サイト(フッター)。URL はここ 1 か所だけ。自サイトの url はデプロイ後に埋める(空なら名前だけ出す)。
     自サイトは self: true または url の origin が現在地と一致する時に「いま見ているサイト」として出し、リンクにしない。 */
  var RELATED_SITES = [
    { name: "HoudiniReference", url: "https://houdini-reference.vercel.app", self: true },
    { name: "The-Algorithm-Illustrated", url: "https://the-algorithm-illustrated.vercel.app" },
    { name: "FoundationsEncyclopedia", url: "https://foundations-encyclopedia.vercel.app" },
    { name: "ColorEncyclopedia", url: "https://color-encyclopedia.vercel.app" }
  ];
  var FAV_KEY = "hr.fav", THEME_KEY = "hr.theme", VIEW_KEY = "hr.view";
  var YT_ID = /^yt:([A-Za-z0-9_-]{11})$/;   /* 動画 ID はこの形のものだけ(サムネ・埋め込みの URL に入れてよい) */

  var state = { items: [], sources: [], refs: null, generated: null, loaded: false, failed: false, nodes: [], nodesFailed: false, nodesMounted: false, nodeId: "",
                tab: "news", q: "", kind: "", lang: "", source: "", period: 0, favOnly: false, favs: {},
                sort: "new", view: "grid" };
  var preview = { list: [], idx: -1, opener: null };
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

  /* URL ハッシュ: #news / #tips / #reference / #nodes / #nodes/<ノード id> */
  function hashParts() {
    var parts = location.hash.slice(1).split("/");
    return { tab: parts[0], id: /^[a-z0-9_-]+$/.test(parts[1] || "") ? parts[1] : "" };
  }

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
    var nodes = fetchJson("data/nodes.json").then(function (d) {
      if (!d || !Array.isArray(d.nodes)) throw new Error("bad shape");
      state.nodes = d.nodes;
    }).catch(function () { state.nodesFailed = true; });
    var refs = fetchJson("data/reference.json").then(function (d) { state.refs = d; }).catch(function () { state.refs = null; });
    return Promise.all([items.catch(function () { state.failed = true; }), refs, nodes]).then(function () { state.loaded = true; });
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
  /* YouTube の動画 ID(`yt:<id>` の形で、ID が 11 文字の安全な文字だけのとき)。それ以外は null */
  function videoId(i) {
    var m = i && typeof i.id === "string" ? YT_ID.exec(i.id) : null;
    return m ? m[1] : null;
  }
  /* サムネ URL は保存せず、動画 ID から組み立てる(YouTube 以外は null → プレースホルダー) */
  function thumbUrl(i) {
    var id = i && i.kind === "youtube" ? videoId(i) : null;
    return id ? "https://i.ytimg.com/vi/" + id + "/mqdefault.jpg" : null;
  }
  function embedUrl(i) {
    var id = i && i.kind === "youtube" ? videoId(i) : null;
    return id ? "https://www.youtube-nocookie.com/embed/" + id : null;
  }
  function viewsOf(i) { return typeof i.views === "number" && isFinite(i.views) && i.views >= 0 ? i.views : null; }
  function fmtViews(n) {
    var r, man = n / 1e4;
    if (man >= 9999.5) { r = (n / 1e8).toFixed(1).replace(/\.0$/, "") + "億"; }
    else if (n >= 1e4) { r = man.toFixed(man >= 100 ? 0 : 1).replace(/\.0$/, "") + "万"; }
    else { r = String(n); }
    return r + " 回視聴";
  }
  function sortRows(rows) {
    var byDate = function (a, b) { return String(b.published).localeCompare(String(a.published)); };
    if (state.sort !== "popular") return rows.sort(byDate);
    return rows.sort(function (a, b) {   // 再生数の多い順。再生数の無い項目は後ろ(その中は新しい順)
      var va = viewsOf(a), vb = viewsOf(b);
      if (va === null && vb === null) return byDate(a, b);
      if (va === null) return 1;
      if (vb === null) return -1;
      return vb - va || byDate(a, b);
    });
  }
  function filtered() {
    var terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    var minTime = state.period ? Date.now() - state.period * 86400000 : 0;
    return sortRows(allForTab().filter(function (i) {
      if (state.favOnly && !state.favs[i.id]) return false;
      if (state.kind && i.kind !== state.kind) return false;
      if (state.lang && i.lang !== state.lang) return false;
      if (state.source && i.source !== state.source) return false;
      if (minTime && new Date(i.published).getTime() < minTime) return false;
      var h = haystack(i);
      return terms.every(function (t) { return h.indexOf(t) >= 0; });
    }));
  }

  /* ---- 描画 ---- */
  /* サムネ枠。16:9 の固定枠(読み込み前・失敗・YouTube 以外でも高さが変わらない)。
     下にプレースホルダー(出典の頭文字)を常に置き、画像が読めたときだけ上に重ねる。画像は保存せず参照表示のみ。 */
  function thumb(i, onOpen) {
    var wrap = el(onOpen ? "button" : "div", "thumb" + (onOpen ? " thumb-btn" : ""));
    if (onOpen) {
      wrap.type = "button";
      wrap.setAttribute("aria-label", "プレビューで再生: " + i.title);
      wrap.addEventListener("click", function () { openPreview(i, wrap); });
    } else { wrap.setAttribute("aria-hidden", "true"); }
    var ph = el("span", "ph", (String(i.source || "?").trim().charAt(0) || "?").toUpperCase());
    ph.setAttribute("aria-hidden", "true");
    wrap.appendChild(ph);
    var url = thumbUrl(i);
    if (url) {
      var img = el("img");
      img.alt = ""; img.loading = "lazy"; img.decoding = "async"; img.referrerPolicy = "no-referrer";
      img.addEventListener("error", function () { if (img.parentNode) img.parentNode.removeChild(img); });
      img.src = url;
      wrap.appendChild(img);
      wrap.appendChild(el("span", "play", "▶"));
    }
    return wrap;
  }

  function card(i) {
    var li = el("li", "card");
    var canPreview = !!embedUrl(i);
    li.appendChild(thumb(i, canPreview ? true : null));
    var body = el("div", "card-body");
    var meta = el("div", "meta");
    meta.appendChild(el("span", "badge " + (KIND_LABEL[i.kind] ? i.kind : "rss"), KIND_LABEL[i.kind] || "Web"));
    meta.appendChild(el("span", "src", i.source || ""));
    if (LANG_LABEL[i.lang]) { var lg = el("span", "lang mono", LANG_LABEL[i.lang]); lg.setAttribute("lang", i.lang); lg.title = i.lang === "ja" ? "日本語" : "English"; meta.appendChild(lg); }
    if (i.kind === "x" && i.handle) meta.appendChild(el("span", "mono", "@" + i.handle));
    var d = fmtDate(i.published);
    if (d) { var t = el("time", "mono", d); t.setAttribute("datetime", i.published); meta.appendChild(t); }
    var v = viewsOf(i);
    if (v !== null) { var vs = el("span", "views mono", fmtViews(v)); vs.title = v.toLocaleString("en-US") + " 回視聴"; meta.appendChild(vs); }
    body.appendChild(meta);

    var href = safeHref(i.url);
    var h = el("h3");
    if (href) {
      var a = el("a", null, i.title);
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      h.appendChild(a);
    } else { h.textContent = i.title; }
    if (i.kind !== "x") body.appendChild(h);   // X は本文(抜粋)が題名の代わり

    if (i.excerpt) body.appendChild(el("p", "ex", i.excerpt));
    if (i.kind === "x") {
      if (href) { var p = el("p", "ex"), a2 = el("a", null, "元の投稿を開く"); a2.href = href; a2.target = "_blank"; a2.rel = "noopener noreferrer"; p.appendChild(a2); body.appendChild(p); }
      body.appendChild(el("p", "xnote", X_NOTE));
    }

    var row = el("div", "foot-row");
    var tags = el("div", "tags");
    (i.tags || []).forEach(function (tg) { tags.appendChild(el("span", "tag", String(tg))); });
    row.appendChild(tags);
    var acts = el("div", "acts");
    if (canPreview) {
      var pv = el("button", "btn pv-btn", "▶ プレビュー");
      pv.type = "button";
      pv.setAttribute("aria-label", "プレビューで再生: " + i.title);
      pv.addEventListener("click", function () { openPreview(i, pv); });
      acts.appendChild(pv);
    }
    var fav = el("button", "fav", state.favs[i.id] ? "★" : "☆");
    fav.type = "button";
    fav.setAttribute("aria-pressed", state.favs[i.id] ? "true" : "false");
    fav.setAttribute("aria-label", "お気に入り: " + i.title);
    fav.addEventListener("click", function () { toggleFav(i); });
    acts.appendChild(fav);
    row.appendChild(acts);
    body.appendChild(row);
    li.appendChild(body);
    return li;
  }

  /* ---- プレビュー枠(<dialog>)。押したときだけ youtube-nocookie の iframe を作り、閉じたら破棄する。自動再生しない ---- */
  function destroyEmbed() { clear($("pv-stage")); }
  function showPreview() {
    var i = preview.list[preview.idx];
    if (!i) return;
    var src = embedUrl(i);
    var stage = $("pv-stage");
    destroyEmbed();
    if (!src) return;
    var f = el("iframe");
    f.src = src;   /* autoplay などのパラメータは付けない */
    f.title = i.title;
    f.setAttribute("allow", "picture-in-picture; fullscreen");
    f.setAttribute("allowfullscreen", "");
    f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation allow-popups allow-popups-to-escape-sandbox");
    stage.appendChild(f);

    $("pv-title").textContent = i.title;
    var meta = $("pv-meta");
    clear(meta);
    meta.appendChild(el("span", "badge youtube", "YouTube"));
    meta.appendChild(el("span", "src", i.source || ""));
    var d = fmtDate(i.published);
    if (d) meta.appendChild(el("time", "mono", d));
    var v = viewsOf(i);
    if (v !== null) meta.appendChild(el("span", "views mono", fmtViews(v)));
    var href = safeHref(i.url), open = $("pv-open");
    if (href) { open.href = href; open.hidden = false; } else { open.removeAttribute("href"); open.hidden = true; }
    updatePreviewFav();
    $("pv-prev").disabled = preview.idx <= 0;
    $("pv-next").disabled = preview.idx >= preview.list.length - 1;
    $("pv-pos").textContent = (preview.idx + 1) + " / " + preview.list.length;
  }
  function updatePreviewFav() {
    var i = preview.list[preview.idx], on = !!(i && state.favs[i.id]), b = $("pv-fav");
    b.setAttribute("aria-pressed", on ? "true" : "false");
    b.textContent = (on ? "★" : "☆") + " お気に入り";
  }
  function openPreview(item, opener) {
    var dlg = $("preview");
    if (typeof dlg.showModal !== "function") {   /* dialog 非対応: 元の動画ページを開くだけ */
      var h = safeHref(item.url); if (h) window.open(h, "_blank", "noopener,noreferrer");
      return;
    }
    preview.list = filtered().filter(function (r) { return !!embedUrl(r); });
    preview.idx = preview.list.map(function (r) { return r.id; }).indexOf(item.id);
    if (preview.idx < 0) { preview.list = [item]; preview.idx = 0; }
    preview.opener = opener || null;
    showPreview();
    if (!dlg.open) dlg.showModal();
  }
  function stepPreview(d) {
    var n = preview.idx + d;
    if (n < 0 || n >= preview.list.length) return;
    preview.idx = n;
    showPreview();
  }
  function bindPreview() {
    var dlg = $("preview");
    function closePreview() { destroyEmbed(); dlg.close(); }
    $("pv-close").addEventListener("click", closePreview);
    $("pv-prev").addEventListener("click", function () { stepPreview(-1); });
    $("pv-next").addEventListener("click", function () { stepPreview(1); });
    $("pv-fav").addEventListener("click", function () {
      var i = preview.list[preview.idx]; if (i) { toggleFav(i); updatePreviewFav(); }
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) closePreview(); });   /* 枠の外(バックドロップ)で閉じる */
    dlg.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft" && !e.altKey && e.target.tagName !== "IFRAME") { stepPreview(-1); }
      else if (e.key === "ArrowRight" && !e.altKey && e.target.tagName !== "IFRAME") { stepPreview(1); }
    });
    dlg.addEventListener("cancel", destroyEmbed);   /* Esc: 閉じる直前に iframe を破棄 */
    dlg.addEventListener("close", function () {   /* Esc・閉じるボタン・バックドロップのどれでも: iframe を破棄 */
      destroyEmbed();
      var o = preview.opener; preview.opener = null;
      if (o && document.body.contains(o)) o.focus(); else { var l = $("list"); if (l) l.focus(); }
    });
  }

  function toggleFav(i) {
    if (state.favs[i.id]) { delete state.favs[i.id]; }
    else { state.favs[i.id] = { id: i.id, tab: i.tab, kind: i.kind, source: i.source, handle: i.handle || "", title: i.title, url: i.url, published: i.published, excerpt: i.excerpt || "", tags: i.tags || [], lang: i.lang || "" }; }
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
        return !state.kind && !state.lang && !state.source && !state.favOnly && terms.every(function (t) { return h.indexOf(t) >= 0; });
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

  function renderNodes() {
    var panel = $("nodes-panel");
    if (!state.loaded) return;
    if (state.nodesFailed || !window.HRNodes) {
      clear(panel);
      panel.appendChild(el("div", "empty")).appendChild(el("strong", null, "ノードのデータを読み込めませんでした"));
      state.nodesMounted = false;
      return;
    }
    if (state.nodesMounted) return;
    state.nodesMounted = true;
    window.HRNodes.mount(panel, state.nodes, {
      id: state.nodeId,
      onChange: function (id) {
        state.nodeId = id || "";
        try { history.replaceState(null, "", "#nodes" + (id ? "/" + id : "")); } catch (e) { /* 無視 */ }
      }
    });
  }

  function render(intro) {
    // タブ
    TABS.forEach(function (t) {
      var b = $("tab-" + t);
      b.setAttribute("aria-selected", t === state.tab ? "true" : "false");
      b.tabIndex = t === state.tab ? 0 : -1;
      var n = t === "nodes" ? state.nodes.length : state.items.filter(function (i) { return i.tab === t; }).length;
      var ok = t === "nodes" ? !state.nodesFailed : !state.failed;
      document.querySelector('[data-count="' + t + '"]').textContent = state.loaded && ok ? String(n) : "";
    });
    var isNodes = state.tab === "nodes";
    ["filters", "refs", "status", "list", "empty"].forEach(function (id) { if (isNodes) $(id).hidden = true; });
    $("filters").hidden = isNodes;
    $("nodes-panel").hidden = !isNodes;
    if (isNodes) { renderNodes(); return; }
    $("status").hidden = false; $("list").hidden = false;
    $("list").setAttribute("aria-labelledby", "tab-" + state.tab);

    // 出典の選択肢(現在のタブにあるもの)。種別ごとにグループ化(情報源が増えても探しやすいように)
    var sel = $("source"), cur = state.source, names = {}, kindOf = {};
    state.items.forEach(function (i) { if (i.tab === state.tab) { names[i.source] = true; kindOf[i.source] = i.kind; } });
    if (cur && !names[cur]) { cur = ""; state.source = ""; }
    clear(sel);
    var o0 = el("option", null, "すべて"); o0.value = ""; sel.appendChild(o0);
    ["rss", "youtube", "github", "x"].forEach(function (k) {
      var group = Object.keys(names).filter(function (n) { return kindOf[n] === k; }).sort();
      if (!group.length) return;
      var og = el("optgroup"); og.label = KIND_LABEL[k] || k;
      group.forEach(function (n) { var o = el("option", null, n); o.value = n; og.appendChild(o); });
      sel.appendChild(og);
    });
    sel.value = cur;

    // 種別・言語・お気に入りボタン
    Array.prototype.forEach.call($("kind").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-kind") === state.kind ? "true" : "false");
    });
    Array.prototype.forEach.call($("lang").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-lang") === state.lang ? "true" : "false");
    });
    Array.prototype.forEach.call($("view").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-view") === state.view ? "true" : "false");
    });
    $("sort").value = state.sort;
    var fb = $("favonly");
    fb.setAttribute("aria-pressed", state.favOnly ? "true" : "false");
    fb.textContent = (state.favOnly ? "★" : "☆") + " お気に入りのみ";

    renderRefs();
    $("refs").className = "refs" + (intro ? " intro" : "");

    var list = $("list");
    clear(list);
    list.className = "list view-" + state.view + (intro ? " intro" : "");
    if (state.failed) { emptyState("failed"); $("status").textContent = ""; return; }
    if (!state.items.length) { emptyState("nodata"); $("status").textContent = ""; return; }

    var rows = filtered();
    // リファレンスタブは「リリースノートの新着」の見出しを付ける
    var frag = document.createDocumentFragment();
    rows.forEach(function (i) { frag.appendChild(card(i)); });
    list.appendChild(frag);
    var total = allForTab().length;
    $("status").textContent = rows.length + " 件" + (rows.length !== total ? "(全 " + total + " 件中)" : "") +
      (state.tab === "reference" ? " — リリースノートの新着" : "") +
      (state.sort === "popular" ? " — 再生数の多い順(再生数のない項目は後ろ)" : "");
    emptyState(rows.length ? null : "none");
  }

  function resetFilters() {
    state.q = ""; state.kind = ""; state.lang = ""; state.source = ""; state.period = 0; state.favOnly = false; state.sort = "new";
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
    var want = "#" + t + (t === "nodes" && state.nodeId ? "/" + state.nodeId : "");
    if (location.hash !== want) { try { history.replaceState(null, "", want); } catch (e) { /* 無視 */ } }
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
    Array.prototype.forEach.call($("lang").querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { state.lang = b.getAttribute("data-lang") || ""; render(false); });
    });
    $("sort").addEventListener("change", function (e) { state.sort = e.target.value === "popular" ? "popular" : "new"; render(false); });
    Array.prototype.forEach.call($("view").querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { state.view = b.getAttribute("data-view") === "list" ? "list" : "grid"; lsSet(VIEW_KEY, state.view); render(false); });
    });
    bindPreview();
    $("favonly").addEventListener("click", function () { state.favOnly = !state.favOnly; render(false); });
    $("theme").addEventListener("click", function () {
      var t = currentTheme() === "dark" ? "light" : "dark";
      applyTheme(t); lsSet(THEME_KEY, t);
    });
    window.addEventListener("hashchange", function () {
      var h = hashParts();
      if (h.tab === "nodes") {
        state.nodeId = h.id;
        if (state.nodesMounted && window.HRNodes) window.HRNodes.select(h.id);
      }
      setTab(h.tab, false);
    });
  }

  function init() {
    var saved = lsGet(THEME_KEY);
    applyTheme(saved === "dark" || saved === "light" ? saved : currentTheme());
    loadFavs();
    state.view = lsGet(VIEW_KEY) === "list" ? "list" : "grid";
    bind();
    renderRelated();
    var h = hashParts();
    state.tab = TABS.indexOf(h.tab) >= 0 ? h.tab : "news";
    state.nodeId = state.tab === "nodes" ? h.id : "";
    load().then(function () {
      renderHeader(); renderHealth();
      render(true);
    });
  }

  init();
})();
