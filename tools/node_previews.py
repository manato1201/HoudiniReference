"""ノードの「前後」プレビュー(SVG)を、ローカルの Houdini(hython)で実際に cook したジオメトリから書き出す開発用スクリプト。
公開サイトの実行には使わない(出力の site/img/nodes/*.svg だけを置く)。

使い方:  hython tools/node_previews.py [出力先=site/img/nodes] [id ...]
画像は点・面を 2D に投影した簡易描画で、Houdini のビューポートの画像ではない(公式の画像・文章は使っていない)。
"""
import hou, math, os, sys, hashlib, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isidentifier() else os.path.join(ROOT, "site", "img", "nodes")
ONLY = [a for a in sys.argv[1:] if a.isidentifier()]
W, H, PAD = 320, 240, 16

geo = hou.node("/obj").createNode("geo", "previews")


def mk(_t, *inputs, **kw):
    n = geo.createNode(_t)
    for k, v in kw.items():
        p = n.parmTuple(k) if isinstance(v, (tuple, list)) else n.parm(k)
        if p is None:
            raise RuntimeError(f"{_t} に {k} がない")
        p.set(v)
    for i, src in enumerate(inputs):
        n.setInput(i, src)
    return n


def wrangle(src, code, cls="point"):
    n = geo.createNode("attribwrangle")
    n.setInput(0, src)
    n.parm("class").set({"detail": 0, "primitive": 1, "point": 2, "vertex": 3}[cls])
    n.parm("snippet").set(code)
    return n


# ---------- 描画 ----------
def snap(node):
    node.cook(force=True)
    if node.errors():
        raise RuntimeError(f"{node.path()}: {node.errors()}")
    g = node.geometry()
    pts = [tuple(p.position()) for p in g.points()]
    ptcd = [tuple(p.attribValue("Cd")) for p in g.points()] if g.findPointAttrib("Cd") else None
    primcd_attr = g.findPrimAttrib("Cd")
    name_attr = g.findPrimAttrib("name")
    cls_attr = g.findPrimAttrib("class")
    prims = []
    for pr in g.prims():
        if pr.type() != hou.primType.Polygon:
            continue
        idx = [v.point().number() for v in pr.vertices()]
        cd = tuple(pr.attribValue("Cd")) if primcd_attr else None
        key = pr.attribValue("name") if name_attr else (pr.attribValue("class") if cls_attr else None)
        prims.append((idx, pr.isClosed(), cd, key))
    return {"pts": pts, "ptcd": ptcd, "prims": prims}


def project(p, view):
    x, y, z = p
    if view == "top":
        return x, z, 0.0
    a, b = math.radians(35), math.radians(28)
    sx = x * math.cos(a) - z * math.sin(a)
    sz = x * math.sin(a) + z * math.cos(a)
    sy = y * math.cos(b) + sz * math.sin(b)  # 斜め上から見下ろす(奥ほど画面の上)
    depth = sz * math.cos(b) - y * math.sin(b)  # 大きいほど奥
    return sx, -sy, depth


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v * 255)))) for v in c)


def hue(key):
    h = int(hashlib.md5(str(key).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    import colorsys
    return colorsys.hsv_to_rgb(h, 0.55, 0.85)


def bounds(geos, view):
    xs, ys = [], []
    for g in geos:
        for p in g["pts"]:
            sx, sy, _ = project(p, view)
            xs.append(sx); ys.append(sy)
    return min(xs), max(xs), min(ys), max(ys)


def render(geos, view, tf, opts):
    mnx, mxx, mny, mxy = tf
    s = min((W - 2 * PAD) / max(mxx - mnx, 1e-6), (H - 2 * PAD) / max(mxy - mny, 1e-6))
    ox = (W - s * (mxx - mnx)) / 2 - s * mnx
    oy = (H - s * (mxy - mny)) / 2 - s * mny
    def T(p):
        sx, sy, d = project(p, view)
        return ox + s * sx, oy + s * sy, d
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
           f'<rect width="{W}" height="{H}" rx="10" fill="#23262d"/>']
    items = []
    solid = opts.get("solid", view == "iso")
    for g in geos:
        P = [T(p) for p in g["pts"]]
        for idx, closed, cd, key in g["prims"]:
            pts2 = [P[i] for i in idx]
            depth = sum(p[2] for p in pts2) / len(pts2)
            items.append(("prim", depth, g, idx, closed, cd, key, pts2))
    items.sort(key=lambda it: -it[1])  # 奥から手前
    for _, depth, g, idx, closed, cd, key, pts2 in items:
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts2)
        if closed and len(idx) >= 3:
            if cd is not None:
                fill = hexc(cd)
            elif key is not None and opts.get("color_key"):
                fill = hexc(hue(key))
            else:
                fill = "#3a4150" if solid else "none"
            if solid and cd is None and not (key is not None and opts.get("color_key")):
                # 面の向きでわずかに明暗(見やすさのための簡易シェーディング)
                p3 = [g["pts"][i] for i in idx[:3]]
                ux = [p3[1][k] - p3[0][k] for k in range(3)]; vx = [p3[2][k] - p3[0][k] for k in range(3)]
                n = [ux[1]*vx[2]-ux[2]*vx[1], ux[2]*vx[0]-ux[0]*vx[2], ux[0]*vx[1]-ux[1]*vx[0]]
                l = math.sqrt(sum(c*c for c in n)) or 1
                lum = abs((n[0]*0.3 + n[1]*0.8 + n[2]*0.5) / l / 1.0)
                v = int(0x32 + min(1.0, lum) * 0x36)
                fill = "#%02x%02x%02x" % (v, v + 6, v + 18)
            out.append(f'<polygon points="{d}" fill="{fill}" stroke="#8d97a8" stroke-width="0.8" stroke-linejoin="round"/>')
        else:
            out.append(f'<polyline points="{d}" fill="none" stroke="#ffb84d" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>')
    show_pts = opts.get("points", all(not g["prims"] for g in geos))
    if opts.get("path"):
        for g in geos:
            P = [T(p) for p in g["pts"]]
            out.append('<polyline points="%s" fill="none" stroke="#6ea8ff" stroke-width="1.2" stroke-dasharray="3 2"/>' % " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in P))
    if show_pts:
        for g in geos:
            for i, p in enumerate(g["pts"]):
                x, y, _ = T(p)
                c = hexc(g["ptcd"][i]) if g["ptcd"] else "#ffcc66"
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{opts.get("r", 2.4)}" fill="{c}"/>')
                if opts.get("labels"):
                    out.append(f'<text x="{x+4:.1f}" y="{y-4:.1f}" font-size="9" fill="#cfd6e4" font-family="monospace">{i}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------- 例 ----------
def ex_grid():
    return dict(before=[mk("grid", size=(4, 4), rows=3, cols=3)], after=[mk("grid", size=(4, 4), rows=9, cols=9)], view="top", opts=dict(r=2.2))

def ex_scatter():
    g = mk("grid", size=(4, 4), rows=2, cols=2)
    s = mk("scatter::2.0", g, forcetotal=1, npts=140)
    return dict(before=[g], after=[s], view="top", opts=dict(points=False if False else True, r=2.2))

def ex_copytopoints():
    box = mk("box", size=(0.5, 0.5, 0.5))
    g = mk("grid", size=(4, 4), rows=2, cols=2)
    sc = mk("scatter::2.0", g, forcetotal=1, npts=14, seed=3)
    c = mk("copytopoints::2.0", box, sc)
    return dict(before=[box, sc], after=[c], view="iso", opts=dict(points=True, r=2.2))

def ex_attribwrangle():
    g = mk("grid", size=(5, 5), rows=18, cols=18)
    w = wrangle(g, "@P.y = sin(@P.x * 2.0) * 0.6;")
    return dict(before=[g], after=[w], view="iso", opts=dict(solid=False))

def ex_attribnoise():
    g = mk("grid", size=(4, 4), rows=14, cols=14)
    cd = wrangle(g, "@Cd = {0.45, 0.45, 0.5};")
    nz = mk("attribnoise::2.0", cd, attribs="Cd", attribtype=1, amplitudev=0.5, amplitude=0.5)
    return dict(before=[cd], after=[nz], view="top", opts=dict(points=True, r=4.2, solid=False))

def ex_blast():
    g = mk("grid", size=(4, 4), rows=7, cols=7)
    b = mk("blast", g, group="0-11", grouptype=3)
    return dict(before=[g], after=[b], view="top", opts=dict(points=False, solid=True))

def ex_merge():
    box = mk("box", size=(1.2, 1.2, 1.2), t=(-0.8, 0, 0))
    sp = mk("sphere", type=1, rad=(0.7, 0.7, 0.7), t=(1.0, 0, 0), rows=10, cols=16)
    m = mk("merge", box, sp)
    return dict(before=[box], after=[m], view="iso", opts={})

def ex_xform():
    box = mk("box", size=(1.2, 1.2, 1.2))
    x = mk("xform", box, t=(1.4, 0.3, 0), r=(0, 40, 0), s=(1.3, 0.6, 1.0))
    return dict(before=[box], after=[x], view="iso", opts={})

def ex_polyextrude():
    g = mk("grid", size=(3, 3), rows=4, cols=4)
    e = mk("polyextrude::2.0", g, group="4", dist=0.8, inset=0.15)
    return dict(before=[g], after=[e], view="iso", opts={})

def ex_resample():
    c = mk("circle", type=1, orient=2, divs=6, rad=(1.5, 1.5))
    r = mk("resample", c, length=0.4)
    return dict(before=[c], after=[r], view="top", opts=dict(points=True, r=3.0))

def ex_carve():
    c = mk("circle", type=1, orient=2, divs=24, rad=(1.5, 1.5), arc=0)
    cv = mk("carve", c, firstu=1, domainu1=0.0, secondu=1, domainu2=0.5)
    return dict(before=[c], after=[cv], view="top", opts=dict(points=False))

def ex_rbdmaterialfracture():
    b = mk("box", size=(2, 2, 2))
    f = mk("rbdmaterialfracture::4.0", b)
    return dict(before=[b], after=[f], view="iso", opts=dict(color_key=True))

def ex_attribcreate():
    g = mk("grid", size=(4, 4), rows=9, cols=9)
    a = mk("attribcreate::2.0", g, name1="Cd", class1=2, type1=2, size1=3, value1v=(1.0, 0.45, 0.1, 0.0))
    return dict(before=[g], after=[a], view="top", opts=dict(points=True, r=3.4, solid=False))

def ex_attribpromote():
    g = mk("grid", size=(4, 4), rows=5, cols=5)
    w = wrangle(g, "@Cd = set(rand(@primnum), rand(@primnum + 7.3), rand(@primnum + 1.9));", cls="primitive")
    p = mk("attribpromote", w, inname="Cd", inclass=1, outclass=2)
    return dict(before=[w], after=[p], view="top", opts=dict(points=True, r=7.0, solid=False))

def ex_delete():
    g = mk("grid", size=(4, 4), rows=2, cols=2)
    s = mk("scatter::2.0", g, forcetotal=1, npts=120, seed=5)
    d = mk("delete", s, entity="point", affectnumber=0, userandom=1, percent=50, negate=0)
    return dict(before=[s], after=[d], view="top", opts=dict(r=2.4))

def ex_groupcreate():
    g = mk("grid", size=(4, 4), rows=9, cols=9)
    cd = wrangle(g, "@Cd = {0.3, 0.33, 0.42};", cls="primitive")
    gc = mk("groupcreate", cd, groupname="g", groupbounding=1, boundtype=0, size=(2.0, 2.0, 2.0))
    col = wrangle(gc, 'if (inprimgroup(0, "g", @primnum)) @Cd = {1, 0.55, 0.1};', cls="primitive")
    return dict(before=[cd], after=[col], view="top", opts=dict(points=False, solid=False))

def ex_sort():
    g = mk("grid", size=(4, 4), rows=2, cols=2)
    s = mk("scatter::2.0", g, forcetotal=1, npts=12, seed=2)
    so = mk("sort", s, ptsort="byx")
    return dict(before=[s], after=[so], view="top", opts=dict(points=True, path=True, labels=True, r=3.0))

def ex_subdivide():
    b = mk("box", size=(1.6, 1.6, 1.6))
    s = mk("subdivide", b, algorithm="osdcc", iterations=2)
    return dict(before=[b], after=[s], view="iso", opts={})

def ex_mountain():
    g = mk("grid", size=(6, 6), rows=26, cols=26)
    m = mk("mountain::2.0", g, height=1.4, elementsize=3.0)
    return dict(before=[g], after=[m], view="iso", opts=dict(solid=False))

def ex_polybevel():
    b = mk("box", size=(1.6, 1.6, 1.6))
    bv = mk("polybevel::3.0", b, offset=0.22, divisions=2, group="")
    return dict(before=[b], after=[bv], view="iso", opts={})

def ex_sweep():
    ln = mk("line", points=30)
    w = wrangle(ln, "@P = set(fit(@ptnum, 0, @numpt-1, -2, 2), sin(@ptnum * 0.45) * 0.5, 0);")
    sw = mk("sweep::2.0", w, surfaceshape="tube", radius=0.15, cols=10)
    return dict(before=[w], after=[sw], view="iso", opts=dict(points=False))

def ex_boolean():
    b = mk("box", size=(1.6, 1.6, 1.6))
    sp = mk("sphere", type=1, rad=(1.0, 1.0, 1.0), t=(-0.8, 0.8, -0.8), rows=14, cols=20)
    bo = mk("boolean::2.0", b, sp, booleanop="subtract", subtractchoices="aminusb")
    return dict(before=[b, sp], after=[bo], view="iso", opts={})

def ex_connectivity():
    a = mk("sphere", type=1, rad=(0.6, 0.6, 0.6), t=(-1.4, 0, 0), rows=8, cols=12)
    b = mk("box", size=(1, 1, 1), t=(0, 0, 0))
    c = mk("sphere", type=1, rad=(0.5, 0.5, 0.5), t=(1.4, 0.3, 0), rows=8, cols=12)
    m = mk("merge", a, b, c)
    cn = mk("connectivity", m, connecttype=1, attribname="class")
    return dict(before=[m], after=[cn], view="iso", opts=dict(color_key=True))

def ex_vdbfrompolygons():
    sp = mk("sphere", type=1, rad=(1.0, 1.0, 1.0), rows=12, cols=20)
    v = mk("vdbfrompolygons", sp, voxelsize=0.3)
    cv = mk("convertvdb", v, conversion="poly")
    return dict(before=[sp], after=[cv], view="iso", opts={})

EXAMPLES = {k[3:]: v for k, v in list(globals().items()) if k.startswith("ex_")}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    ok, ng = [], []
    for name, fn in EXAMPLES.items():
        if ONLY and name not in ONLY:
            continue
        try:
            ex = fn()
            b = [snap(n) for n in ex["before"]]
            a = [snap(n) for n in ex["after"]]
            view = ex["view"]
            tf = bounds(b + a, view)
            for tag, gs in (("before", b), ("after", a)):
                svg = render(gs, view, tf, ex["opts"])
                with open(os.path.join(OUT, f"{name}-{tag}.svg"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(svg + "\n")
            ok.append(name)
        except Exception as e:
            ng.append((name, str(e)[:200]))
    print("OK", ok)
    print("NG", ng)
