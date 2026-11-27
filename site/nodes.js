/* HoudiniReference — 「ノード」タブの描画。data/nodes.json(自作の説明)を読む。
   データ中の文字列は必ず textContent で入れる(innerHTML は使わない)。接続例は chain(ノード名の配列)から SVG を自動で描く。 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var CONTEXT_ORDER = ["SOP", "VOP", "LOP", "DOP", "COP", "CHOP", "OBJ", "ROP", "TOP"];
  /* カテゴリの並び(80 件・19 カテゴリでも探しやすいよう、作る→変える→属性→シミュレーション→入出力…の流れ)。ここに無いカテゴリは末尾に五十音順 */
  var CATEGORY_ORDER = ["生成", "配置・コピー", "変形", "モデリング", "曲線", "選択・削除", "統合", "VEX・アトリビュート", "ボリューム(VDB)", "シミュレーション",
                        "リギング(KineFX)", "APEX", "入出力・管理", "USD 連携", "マテリアル", "レンダリング", "画像処理", "TOP・自動化", "チャンネル"];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function str(v) { return typeof v === "string" ? v : ""; }
  function strList(v) { return Array.isArray(v) ? v.filter(function (s) { return typeof s === "string" && s; }) : []; }

  /* 公式ドキュメントへのリンクは https だけ。画像は site/img/nodes/ 配下の相対パスだけ(外部・.. は使わない)。 */
  function safeDocUrl(u) {
    try { var p = new URL(u); return p.protocol === "https:" ? p.href : null; } catch (e) { return null; }
  }
  function safeImg(p) {
    return typeof p === "string" && /^img\/nodes\/[A-Za-z0-9_-]+\.(svg|png)$/.test(p) ? p : null;
  }

  /* ---- 接続例の SVG(ライブラリなし・createElementNS と textContent だけ)。ノード名を矩形で結ぶ。縦に流す(Houdini のネットワークと同じ上→下) ---- */
  function textWidth(s) {   // 文字幅の概算(全角は広め)
    var w = 0;
    for (var i = 0; i < s.length; i++) w += s.charCodeAt(i) > 255 ? 14 : 7.6;
    return w;
  }
  function svgEl(name, attrs) {
    var n = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, String(attrs[k])); });
    return n;
  }
  function renderChain(chain) {
    var names = strList(chain);
    var BOX_H = 34, GAP = 22, PADX = 16, MARGIN = 6;
    var maxW = 0;
    names.forEach(function (n) { maxW = Math.max(maxW, textWidth(n)); });
    var boxW = Math.max(96, Math.ceil(maxW + PADX * 2));
    var W = boxW + MARGIN * 2;
    var H = names.length * BOX_H + Math.max(0, names.length - 1) * GAP + MARGIN * 2;
    var svg = svgEl("svg", { "class": "chain", viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", focusable: "false" });
    svg.setAttribute("aria-label", "接続の例: " + names.join(" → "));
    svg.appendChild(svgEl("title")).textContent = names.join(" → ");
    names.forEach(function (name, i) {
      var y = MARGIN + i * (BOX_H + GAP);
      var g = svgEl("g");
      g.appendChild(svgEl("rect", { x: MARGIN, y: y, width: boxW, height: BOX_H, rx: 7, "class": "chain-box" }));
      var t = svgEl("text", { x: MARGIN + boxW / 2, y: y + BOX_H / 2, "text-anchor": "middle", "dominant-baseline": "central", "class": "chain-label" });
      t.textContent = name;
      g.appendChild(t);
      svg.appendChild(g);
      if (i < names.length - 1) {   // 次のノードへの矢印
        var x = MARGIN + boxW / 2, y1 = y + BOX_H, y2 = y1 + GAP;
        svg.appendChild(svgEl("line", { x1: x, y1: y1, x2: x, y2: y2 - 5, "class": "chain-line" }));
        svg.appendChild(svgEl("path", { d: "M" + (x - 5) + " " + (y2 - 7) + " L" + x + " " + y2 + " L" + (x + 5) + " " + (y2 - 7), fill: "none", "class": "chain-line" }));
      }
    });
    return svg;
  }

  /* ---- 画面 ---- */
  var S = { nodes: [], ctx: "", cat: "", q: "", id: "", root: null, onChange: null, rows: [], fav: null };

  function filtered() {
    var terms = S.q.toLowerCase().split(/\s+/).filter(Boolean);
    return S.nodes.filter(function (n) {
      if (S.ctx && n.context !== S.ctx) return false;
      if (S.cat && n.category !== S.cat) return false;
      if (!terms.length) return true;
      var h = [n.name, n.type, n.context, n.category, n.what, n.how].concat(strList(n.use_cases)).join(" ").toLowerCase();
      return terms.every(function (t) { return h.indexOf(t) >= 0; });
    });
  }
  function count(list, key) {
    var m = {};
    list.forEach(function (n) { m[n[key]] = (m[n[key]] || 0) + 1; });
    return m;
  }
  function sync() {
    if (S.onChange) S.onChange(S.id);
  }

  function filterButton(label, n, active, onClick) {
    var b = el("button", "nf-item");
    b.type = "button";
    b.setAttribute("aria-pressed", active ? "true" : "false");
    b.appendChild(el("span", "nf-name", label));
    b.appendChild(el("span", "nf-count mono", String(n)));
    b.addEventListener("click", onClick);
    return b;
  }

  function sidebar() {
    var side = el("aside", "n-side");
    side.setAttribute("aria-label", "ノードの絞り込み");
    var search = el("label", "field");
    search.appendChild(el("span", "lbl", "ノードを検索"));
    var inp = el("input");
    inp.type = "search"; inp.id = "nq"; inp.value = S.q; inp.autocomplete = "off"; inp.placeholder = "名前・説明(スペースで AND)";
    inp.addEventListener("input", function () { S.q = inp.value; S.id = ""; var pos = inp.selectionStart; renderPanel(); var again = document.getElementById("nq"); if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (e) { /* 無視 */ } } sync(); });
    search.appendChild(inp);
    side.appendChild(search);

    var ctxCounts = count(S.nodes.filter(function (n) { return !S.cat || n.category === S.cat; }), "context");
    var g1 = el("div", "n-group");
    g1.appendChild(el("h2", "n-h", "コンテキスト"));
    var l1 = el("div", "nf-list");
    l1.appendChild(filterButton("すべて", Object.keys(ctxCounts).reduce(function (a, k) { return a + ctxCounts[k]; }, 0), !S.ctx, function () { S.ctx = ""; S.id = ""; renderPanel(); sync(); }));
    CONTEXT_ORDER.concat(Object.keys(ctxCounts).filter(function (k) { return CONTEXT_ORDER.indexOf(k) < 0; })).forEach(function (c) {
      if (!ctxCounts[c]) return;
      l1.appendChild(filterButton(c, ctxCounts[c], S.ctx === c, function () { S.ctx = S.ctx === c ? "" : c; S.id = ""; renderPanel(); sync(); }));
    });
    g1.appendChild(l1); side.appendChild(g1);

    var catCounts = count(S.nodes.filter(function (n) { return !S.ctx || n.context === S.ctx; }), "category");
    var g2 = el("div", "n-group");
    g2.appendChild(el("h2", "n-h", "カテゴリ"));
    var l2 = el("div", "nf-list");
    l2.appendChild(filterButton("すべて", Object.keys(catCounts).reduce(function (a, k) { return a + catCounts[k]; }, 0), !S.cat, function () { S.cat = ""; S.id = ""; renderPanel(); sync(); }));
    var catKeys = Object.keys(catCounts);
    catKeys.sort(function (a, b) {
      var ia = CATEGORY_ORDER.indexOf(a), ib = CATEGORY_ORDER.indexOf(b);
      if (ia < 0 && ib < 0) return a < b ? -1 : a > b ? 1 : 0;
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
    });
    catKeys.forEach(function (c) {
      l2.appendChild(filterButton(c, catCounts[c], S.cat === c, function () { S.cat = S.cat === c ? "" : c; S.id = ""; renderPanel(); sync(); }));
    });
    g2.appendChild(l2); side.appendChild(g2);
    return side;
  }

  function nodeCard(n) {
    var li = el("li", "ncard");
    var b = el("button", "ncard-btn");
    b.type = "button";
    var head = el("div", "ncard-head");
    head.appendChild(el("h3", "ncard-name", n.name));
    if (S.fav && S.fav.has(n.id)) { var star = el("span", "ncard-fav", "★"); star.setAttribute("aria-label", "お気に入り"); head.appendChild(star); }
    head.appendChild(el("span", "badge nctx", n.context));
    b.appendChild(head);
    b.appendChild(el("p", "ncard-what", n.what));
    var foot = el("div", "ncard-foot");
    foot.appendChild(el("span", "tag", n.category));
    foot.appendChild(el("span", "mono ntype", n.type || n.id));
    b.appendChild(foot);
    b.setAttribute("aria-label", n.name + "(" + n.context + "): 詳細を開く");
    b.addEventListener("click", function () { S.id = n.id; renderPanel(true); sync(); });
    li.appendChild(b);
    return li;
  }

  function renderList(main) {
    var rows = filtered();
    var status = el("p", "status", rows.length + " 件" + (rows.length !== S.nodes.length ? "(全 " + S.nodes.length + " 件中)" : ""));
    status.setAttribute("role", "status");
    main.appendChild(status);
    if (!rows.length) {
      var box = el("div", "empty");
      box.appendChild(el("strong", null, "条件に合うノードがありません"));
      box.appendChild(el("span", null, "検索語や絞り込みを変えてみてください。"));
      var b = el("button", "btn", "絞り込みを解除");
      b.type = "button";
      b.addEventListener("click", function () { S.q = ""; S.ctx = ""; S.cat = ""; renderPanel(); sync(); });
      box.appendChild(el("div")).appendChild(b);
      main.appendChild(box);
      return;
    }
    var ul = el("ul", "ngrid");
    rows.forEach(function (n) { ul.appendChild(nodeCard(n)); });
    main.appendChild(ul);
  }

  /* ---- 詳細: 5 サイト共通の並び(ITEM・SPEC・NOTES・TIPS・METHODS・RELATED)。左(狭い画面では ITEM の下)は前後の違い(主役)。
     データに無い欄は出さない(空のカードや「準備中」を並べない)。 ---- */
  function bullets(items) {
    var ul = el("ul", "nlist");
    items.forEach(function (t) { ul.appendChild(el("li", null, t)); });
    return ul;
  }
  var panelNo = 0;
  function panel(cls, key, title) {
    var p = el("section", "np " + cls);
    p.setAttribute("data-panel", key.toLowerCase());
    p.style.setProperty("--i", String(panelNo++));   // 出てくる順(動きの遅れ)
    var h = el("p", "np-label mono");
    h.appendChild(el("span", "np-key", key));
    h.appendChild(el("span", null, "· " + title));
    p.appendChild(h);
    return p;
  }
  function byName() {
    var m = {};
    S.nodes.forEach(function (x) { m[x.name.toLowerCase()] = x; });
    return m;
  }
  function openNode(id) { S.id = id; renderPanel(true); sync(); }
  function step(d) {
    var rows = S.rows, idx = rows.map(function (r) { return r.id; }).indexOf(S.id);
    if (rows.length < 2 || idx < 0) return;
    openNode(rows[(idx + d + rows.length) % rows.length].id);
  }

  function itemPanel(n, rows) {
    var p = panel("np-item", "ITEM", "NODE-" + String(S.nodes.indexOf(n) + 1).padStart(3, "0"));
    var nav = el("div", "nd-nav");
    var back = el("button", "btn", "← 一覧へ");
    back.type = "button";
    back.addEventListener("click", function () { S.id = ""; renderPanel(); sync(); });
    var idx = rows.map(function (r) { return r.id; }).indexOf(n.id);
    var prev = el("button", "btn nd-prev", "← 前のノード"), next = el("button", "btn nd-next", "次のノード →");
    prev.type = next.type = "button";
    if (rows.length > 1) {
      prev.title = "前のノード: " + rows[(idx - 1 + rows.length) % rows.length].name + "(Shift+N)";
      next.title = "次のノード: " + rows[(idx + 1) % rows.length].name + "(N)";
    }
    prev.setAttribute("aria-keyshortcuts", "Shift+N");
    next.setAttribute("aria-keyshortcuts", "N");
    prev.disabled = next.disabled = rows.length < 2;
    prev.addEventListener("click", function () { step(-1); });
    next.addEventListener("click", function () { step(1); });
    var pos = el("span", "mono ndetail-pos", idx >= 0 ? (idx + 1) + " / " + rows.length : "");
    nav.appendChild(back); nav.appendChild(prev); nav.appendChild(pos); nav.appendChild(next);
    nav.appendChild(el("span", "grow"));
    if (S.fav) {
      var on = S.fav.has(n.id);
      var fav = el("button", "fav", on ? "★" : "☆");
      fav.type = "button";
      fav.setAttribute("aria-pressed", on ? "true" : "false");
      fav.setAttribute("aria-label", "お気に入り: " + n.name);
      fav.addEventListener("click", function () {
        var now = S.fav.toggle(n);
        fav.textContent = now ? "★" : "☆";
        fav.setAttribute("aria-pressed", now ? "true" : "false");
      });
      nav.appendChild(fav);
    }
    p.appendChild(nav);
    p.appendChild(el("p", "nd-eyebrow mono", n.context + " · " + n.category));
    var h2 = el("h2", "nd-title", n.name);
    h2.id = "ndetail-title";
    p.appendChild(h2);
    p.appendChild(el("p", "nd-what", n.what));
    return p;
  }

  /* 前後の違い(主役)。図があれば左の列、無ければ ITEM の下に文章だけ。文章も無ければ出さない */
  function stagePanel(n) {
    var ba = n.before_after && typeof n.before_after === "object" ? n.before_after : {};
    var image = ba.image && typeof ba.image === "object" ? ba.image : null;
    var any = false;
    var p = panel("np-stage", "BEFORE / AFTER", "使う前と後");
    p.setAttribute("data-panel", "stage");
    var pair = el("div", "nba");
    [["before", "使う前"], ["after", "使った後"]].forEach(function (k) {
      var src = image && safeImg(image[k[0]]), text = str(ba[k[0]]);
      if (!src && !text) return;
      any = true;
      var box = el("div", "nba-box " + k[0]);
      box.appendChild(el("h4", "nsub", k[1]));
      if (src) {
        var img = el("img", "nba-img");
        img.alt = k[0] === "after" ? str(image.alt) || "使った後のジオメトリの図" : "使う前のジオメトリの図";
        img.loading = "lazy"; img.decoding = "async"; img.width = 320; img.height = 240;
        img.addEventListener("error", function () { if (img.parentNode) img.parentNode.removeChild(img); });
        img.src = src;
        box.appendChild(img);
      }
      if (text) box.appendChild(el("p", null, text));
      pair.appendChild(box);
    });
    if (!any) return null;
    p.appendChild(pair);
    if (p.querySelector(".nba-img")) {
      p.classList.add("has-img");
      p.appendChild(el("p", "nnote", "図は、このノードを実際に Houdini 22 で cook したジオメトリの点・面を、簡易に描いたものです(公式の画像ではありません)。"));
    }
    return p;
  }

  function specPanel(n) {
    var p = panel("np-spec", "SPEC", "仕様");
    var dl = el("dl", "nd-meta");
    function row(k, v) {
      var d = el("div");
      d.appendChild(el("dt", "mono", k));
      var dd = el("dd");
      if (typeof v === "string") dd.textContent = v; else dd.appendChild(v);
      d.appendChild(dd);
      dl.appendChild(d);
    }
    row("コンテキスト", el("span", "badge nctx", n.context));
    row("カテゴリ", el("span", "tag", n.category));
    if (str(n.type)) row("型名", el("span", "mono ntype", n.type));
    row("確認", el("span", "nverified " + (n.verified ? "ok" : "unv"), n.verified ? "Houdini 22 で名前・パラメータを確認済み" : "未確認(名前・パラメータは Houdini で確認していません)"));
    var uses = strList(n.use_cases);
    if (uses.length) row("使いどころ", bullets(uses));
    p.appendChild(dl);
    var params = paramsOf(n);
    if (params.length) {
      var chips = el("ul", "nchips mono");
      chips.setAttribute("aria-label", "主なパラメータ");
      params.forEach(function (x) {
        var li = el("li", null, x.name);
        if (str(x.note)) li.title = x.note;
        chips.appendChild(li);
      });
      p.appendChild(chips);
    }
    return p;
  }
  function paramsOf(n) {
    return Array.isArray(n.params) ? n.params.filter(function (x) { return x && typeof x.name === "string" && x.name; }) : [];
  }

  function notesPanel(n) {
    var look = strList(n.example_points);
    if (!look.length) return null;   // 「使うときの注意」はデータが無いので出さない(段階 B で足す)
    var p = panel("np-notes", "NOTES", "見る所と注意");
    var cards = el("div", "nd-cards");
    var c1 = el("section", "nd-card nd-card--look");
    c1.appendChild(el("h3", "mono", "見るポイント"));
    c1.appendChild(bullets(look));
    cards.appendChild(c1);
    p.appendChild(cards);
    return p;
  }

  function tipsPanel(n) {
    var combos = (Array.isArray(n.combos) ? n.combos : []).filter(function (c) { return c && Array.isArray(c.chain) && strList(c.chain).length; });
    if (!combos.length) return null;
    var p = panel("np-tips", "TIPS", "組み合わせの要点");
    var ol = el("ol", "ntips");
    combos.forEach(function (c, i) {
      var li = el("li", "ntip");
      li.appendChild(el("span", "ntip-n mono", String(i + 1).padStart(2, "0")));
      var body = el("div", "ntip-body");
      if (str(c.title)) body.appendChild(el("strong", null, c.title));
      if (str(c.note)) body.appendChild(el("span", null, c.note));
      li.appendChild(body);
      var f = el("figure", "ncombo");
      f.appendChild(renderChain(c.chain));
      li.appendChild(f);
      ol.appendChild(li);
    });
    p.appendChild(ol);
    return p;
  }

  function methodsPanel(n) {
    var how = str(n.how), params = paramsOf(n), href = safeDocUrl(n.doc_url);
    if (!how && !params.length && !href) return null;
    var p = panel("np-methods", "METHODS", "使い方");
    if (how) p.appendChild(el("p", "nd-how", how));
    if (params.length) {
      p.appendChild(el("h4", "nsub", "主なパラメータ"));
      var dl = el("dl", "nparams");
      params.forEach(function (x) { dl.appendChild(el("dt", "mono", x.name)); dl.appendChild(el("dd", null, str(x.note))); });
      p.appendChild(dl);
    }
    if (href) {
      var d = el("p", "ndoc");
      var a = el("a", "btn", "公式ドキュメントを開く(sidefx.com)");
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      d.appendChild(a);
      d.appendChild(el("span", "nnote", "説明は自作の文章で、公式の文章ではありません。詳しい仕様は公式を参照してください。"));
      p.appendChild(d);
    }
    return p;
  }

  /* 組み合わせに出てくる他のノード(出てきた順・重複なし)。ノード一覧にある名前はリンク */
  function relatedPanel(n) {
    var map = byName(), seen = {}, names = [];
    (Array.isArray(n.combos) ? n.combos : []).forEach(function (c) {
      strList(c && c.chain).forEach(function (x) {
        var k = x.toLowerCase();
        if (k === n.name.toLowerCase() || seen[k]) return;
        seen[k] = true; names.push(x);
      });
    });
    if (!names.length) return null;
    var p = panel("np-rel", "RELATED", "組み合わせに出てくるノード");
    var ul = el("ul", "nrel");
    names.forEach(function (x) {
      var li = el("li");
      var hit = map[x.toLowerCase()];
      if (hit && hit.id !== n.id) {
        var a = el("a", "nrel-link");
        a.setAttribute("href", "#nodes/" + encodeURIComponent(hit.id));
        a.appendChild(el("span", "badge nctx", hit.context));
        a.appendChild(el("span", null, hit.name));
        a.addEventListener("click", function (e) {
          if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
          e.preventDefault(); openNode(hit.id);
        });
        li.appendChild(a);
      } else {
        li.appendChild(el("span", "nrel-item", x));
      }
      ul.appendChild(li);
    });
    p.appendChild(ul);
    return p;
  }

  function renderDetail(main, n, rows) {
    panelNo = 0;
    S.rows = rows;
    var art = el("article", "ndetail");
    art.setAttribute("aria-labelledby", "ndetail-title");
    var item = itemPanel(n, rows);
    var stage = stagePanel(n);
    var info = el("div", "nd-info");
    [specPanel(n), notesPanel(n), tipsPanel(n), methodsPanel(n), relatedPanel(n)].forEach(function (x) { if (x) info.appendChild(x); });
    art.appendChild(item);
    if (stage) {
      art.appendChild(stage);
      if (stage.classList.contains("has-img")) art.classList.add("has-stage");
    }
    art.appendChild(info);
    main.appendChild(art);
  }

  function renderPanel(focusTitle) {
    var root = S.root;
    clear(root);
    root.appendChild(sidebar());
    var main = el("div", "n-main");
    var rows = filtered();
    var cur = null;
    for (var i = 0; i < S.nodes.length; i++) if (S.nodes[i].id === S.id) cur = S.nodes[i];
    if (cur && rows.every(function (r) { return r.id !== cur.id; })) rows = S.nodes.slice();   // 絞り込みの外のノードを直接開いたとき
    if (cur) renderDetail(main, cur, rows); else renderList(main);
    root.appendChild(main);
    if (focusTitle) { var t = document.getElementById("ndetail-title"); if (t) { t.tabIndex = -1; t.focus(); } }
  }

  /* 公開 API。nodes.json の "nodes" 配列を受け取り、panel に描く。onChange(id) は選択の変化を app.js に知らせる(URL ハッシュ用) */
  function mount(root, nodes, opts) {
    S.root = root;
    S.nodes = (Array.isArray(nodes) ? nodes : []).filter(function (n) {
      return n && typeof n.id === "string" && typeof n.name === "string" && typeof n.context === "string" && typeof n.what === "string";
    });
    S.onChange = opts && opts.onChange;
    S.fav = opts && opts.fav && typeof opts.fav.has === "function" && typeof opts.fav.toggle === "function" ? opts.fav : null;
    S.id = (opts && opts.id) || "";
    renderPanel(false);
    if (!keysBound) { keysBound = true; document.addEventListener("keydown", onKey); }
  }
  /* 詳細を開いているとき: n = 次のノード、N(Shift+n)= 前のノード。入力中・修飾キーつき・タブが隠れているときは何もしない */
  var keysBound = false;
  function onKey(e) {
    if (!S.root || S.root.hidden || !S.id || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    if (document.querySelector("dialog[open]")) return;
    if (e.key === "n" || e.key === "N") { e.preventDefault(); step(e.key === "N" ? -1 : 1); }
  }
  function select(id) {   // ハッシュの変化から。存在しない id は一覧に戻す
    if (!S.root) return;
    S.id = S.nodes.some(function (n) { return n.id === id; }) ? id : "";
    renderPanel(false);
  }

  window.HRNodes = { mount: mount, select: select, renderChain: renderChain };
})();
