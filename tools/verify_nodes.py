"""data/nodes.json の「確認済み(verified: true)」のノードを、ローカルの Houdini(hython)で実際に照合する開発用スクリプト。
公開サイトの実行には使わない。型名(type)が実在するか、params の名前がそのノードのパラメータとして実在するかを調べる。

使い方:  hython tools/verify_nodes.py [id ...]   (id を省略すると全件)
type に " / " で複数の型を書いたノード(例: block_begin / block_end)は、どれかの型に params があれば良しとする。
"""
import hou, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATEGORY = {"SOP": "Sop", "VOP": "Vop", "LOP": "Lop", "DOP": "Dop", "COP": "Cop", "TOP": "Top", "CHOP": "Chop", "ROP": "Driver", "OBJ": "Object"}
ONLY = set(sys.argv[1:])


def all_names(ptg):
    names = set()
    def walk(tmpls):
        for t in tmpls:
            names.add(t.name())
            if t.type() in (hou.parmTemplateType.Folder, hou.parmTemplateType.FolderSet):
                walk(t.parmTemplates())
    walk(ptg.entries())
    return names


def main():
    doc = json.load(open(os.path.join(ROOT, "data", "nodes.json"), encoding="utf-8"))
    cats = hou.nodeTypeCategories()
    bad, ok = [], 0
    for n in doc["nodes"]:
        if ONLY and n["id"] not in ONLY:
            continue
        if not n.get("verified"):
            print("SKIP (verified: false)", n["id"])
            continue
        cat = cats[CATEGORY[n["context"]]]
        types = [t.strip() for t in n["type"].split(" / ")]
        names, missing_types = set(), []
        for t in types:
            nt = cat.nodeTypes().get(t)
            if nt is None:
                missing_types.append(t)
            else:
                names |= all_names(nt.parmTemplateGroup())
        problems = [f"型 {t} がない" for t in missing_types]
        for p in n.get("params", []):
            if p["name"].startswith("("):   # 「(パラメータなし)」のような注記は照合しない
                continue
            if p["name"] not in names and p["name"] + "#" not in names:
                problems.append(f"param {p['name']} がない")
        if problems:
            bad.append((n["id"], problems))
        else:
            ok += 1
    print("OK", ok)
    for i, pr in bad:
        print("NG", i, pr)
    print("RESULT", "ALL OK" if not bad else f"{len(bad)} NG")


main()
