/* HoudiniReference — 「ノード」タブの描画。data/nodes.json(自作の説明)を読む。
   データ中の文字列は必ず textContent で入れる(innerHTML は使わない)。接続例は chain(ノード名の配列)から SVG を自動で描く。 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var CONTEXT_ORDER = ["SOP", "VOP", "LOP", "DOP", "COP", "OBJ", "ROP", "TOP"];
  var SECTIONS = [
    ["①", "何をするか"], ["②", "どう使うか"], ["③", "実例のポイント"],
    ["④", "使いどころ"], ["⑤", "他のノードとの組み合わせ例"], ["⑥", "使う前と後の違い"]
  ];

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
  var S = { nodes: [], ctx: "", cat: "", q: "", id: "", root: null, onChange: null };

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
    Object.keys(catCounts).sort().forEach(function (c) {
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

  function section(num, title) {
    var s = el("section", "nsec");
    var h = el("h3", "nsec-h");
    h.appendChild(el("span", "nsec-num", num));
    h.appendChild(document.createTextNode(" " + title));
    s.appendChild(h);
    return s;
  }
  function bullets(items) {
    var ul = el("ul", "nlist");
    items.forEach(function (t) { ul.appendChild(el("li", null, t)); });
    return ul;
  }

  function renderDetail(main, n, rows) {
    var top = el("div", "ndetail-top");
    var back = el("button", "btn", "← 一覧へ");
    back.type = "button";
    back.addEventListener("click", function () { S.id = ""; renderPanel(); sync(); });
    top.appendChild(back);
    var idx = rows.map(function (r) { return r.id; }).indexOf(n.id);
    var nav = el("div", "ndetail-nav");
    var prev = el("button", "btn", "← 前のノード"), next = el("button", "btn", "次のノード →");
    prev.type = next.type = "button";
    prev.disabled = idx <= 0; next.disabled = idx < 0 || idx >= rows.length - 1;
    prev.addEventListener("click", function () { S.id = rows[idx - 1].id; renderPanel(true); sync(); });
    next.addEventListener("click", function () { S.id = rows[idx + 1].id; renderPanel(true); sync(); });
    nav.appendChild(prev); nav.appendChild(next);
    nav.appendChild(el("span", "mono ndetail-pos", idx >= 0 ? (idx + 1) + " / " + rows.length : ""));
    top.appendChild(nav);
    main.appendChild(top);

    var art = el("article", "ndetail");
    art.setAttribute("aria-labelledby", "ndetail-title");
    var head = el("header", "ndetail-head");
    var h2 = el("h2", null, n.name);
    h2.id = "ndetail-title";
    head.appendChild(h2);
    var meta = el("div", "ndetail-meta");
    meta.appendChild(el("span", "badge nctx", n.context));
    meta.appendChild(el("span", "tag", n.category));
    if (n.type) meta.appendChild(el("span", "mono ntype", n.type));
    meta.appendChild(el("span", "nverified " + (n.verified ? "ok" : "unv"), n.verified ? "Houdini 22 で名前・パラメータを確認済み" : "未確認(名前・パラメータは Houdini で確認していません)"));
    head.appendChild(meta);
    art.appendChild(head);

    var s1 = section(SECTIONS[0][0], SECTIONS[0][1]); s1.appendChild(el("p", null, n.what)); art.appendChild(s1);

    var s2 = section(SECTIONS[1][0], SECTIONS[1][1]); s2.appendChild(el("p", null, n.how));
    var params = Array.isArray(n.params) ? n.params.filter(function (p) { return p && typeof p.name === "string"; }) : [];
    if (params.length) {
      s2.appendChild(el("h4", "nsub", "主なパラメータ"));
      var dl = el("dl", "nparams");
      params.forEach(function (p) { dl.appendChild(el("dt", "mono", p.name)); dl.appendChild(el("dd", null, str(p.note))); });
      s2.appendChild(dl);
    }
    art.appendChild(s2);

    var s3 = section(SECTIONS[2][0], SECTIONS[2][1]); s3.appendChild(bullets(strList(n.example_points))); art.appendChild(s3);
    var s4 = section(SECTIONS[3][0], SECTIONS[3][1]); s4.appendChild(bullets(strList(n.use_cases))); art.appendChild(s4);

    var s5 = section(SECTIONS[4][0], SECTIONS[4][1]);
    var combos = Array.isArray(n.combos) ? n.combos : [];
    var wrap = el("div", "ncombos");
    combos.forEach(function (c) {
      if (!c || !Array.isArray(c.chain)) return;
      var f = el("figure", "ncombo");
      f.appendChild(renderChain(c.chain));
      var cap = el("figcaption");
      cap.appendChild(el("strong", null, str(c.title)));
      cap.appendChild(el("span", null, str(c.note)));
      f.appendChild(cap);
      wrap.appendChild(f);
    });
    s5.appendChild(wrap); art.appendChild(s5);

    var s6 = section(SECTIONS[5][0], SECTIONS[5][1]);
    var ba = n.before_after || {};
    var pair = el("div", "nba");
    [["before", "使う前"], ["after", "使った後"]].forEach(function (k) {
      var box = el("div", "nba-box " + k[0]);
      box.appendChild(el("h4", "nsub", k[1]));
      var image = ba.image && safeImg(ba.image[k[0]]);
      if (image) {
        var img = el("img", "nba-img");
        img.alt = k[0] === "after" ? str(ba.image.alt) : "使う前のジオメトリの図";
        img.loading = "lazy"; img.decoding = "async"; img.width = 320; img.height = 240;
        img.addEventListener("error", function () { if (img.parentNode) img.parentNode.removeChild(img); });
        img.src = image;
        box.appendChild(img);
      }
      box.appendChild(el("p", null, str(ba[k[0]])));
      pair.appendChild(box);
    });
    s6.appendChild(pair);
    if (ba.image) s6.appendChild(el("p", "nnote", "図は、このノードを実際に Houdini 22 で cook したジオメトリの点・面を、簡易に描いたものです(公式の画像ではありません)。"));
    art.appendChild(s6);

    var href = safeDocUrl(n.doc_url);
    if (href) {
      var p = el("p", "ndoc");
      var a = el("a", "btn", "公式ドキュメントを開く(sidefx.com)");
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      p.appendChild(a);
      p.appendChild(el("span", "nnote", "説明は自作の文章で、公式の文章ではありません。詳しい仕様は公式を参照してください。"));
      art.appendChild(p);
    }
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
  function mount(panel, nodes, opts) {
    S.root = panel;
    S.nodes = (Array.isArray(nodes) ? nodes : []).filter(function (n) {
      return n && typeof n.id === "string" && typeof n.name === "string" && typeof n.context === "string" && typeof n.what === "string";
    });
    S.onChange = opts && opts.onChange;
    S.id = (opts && opts.id) || "";
    renderPanel(false);
  }
  function select(id) {   // ハッシュの変化から。存在しない id は一覧に戻す
    if (!S.root) return;
    S.id = S.nodes.some(function (n) { return n.id === id; }) ? id : "";
    renderPanel(false);
  }

  window.HRNodes = { mount: mount, select: select, renderChain: renderChain };
})();
