"""data/nodes.json の検査(ネットワーク・Houdini 不要)。ノードを足すときは JSON に 1 件足すだけで、ここで形が検査される。"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from collector.run import sync_site_data

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "nodes.json"
SITE = ROOT / "site"
REQUIRED = ("id", "name", "context", "category", "what", "how", "example_points", "use_cases", "combos", "before_after", "doc_url", "verified")
CONTEXTS = {"SOP", "VOP", "LOP", "DOP", "COP", "OBJ", "ROP", "TOP"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def nonempty(s):
    return isinstance(s, str) and s.strip() != ""


class NodesJsonTests(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.nodes = self.doc["nodes"]

    def test_has_at_least_30_nodes(self):
        self.assertGreaterEqual(len(self.nodes), 30)

    def test_required_keys_and_nonempty_strings(self):
        for n in self.nodes:
            for k in REQUIRED:
                self.assertIn(k, n, f"{n.get('id')}: {k} がない")
            for k in ("id", "name", "context", "category", "what", "how", "doc_url"):
                self.assertTrue(nonempty(n[k]), f"{n['id']}: {k} が空")
            self.assertIsInstance(n["verified"], bool, n["id"])

    def test_ids_unique_and_safe(self):
        ids = [n["id"] for n in self.nodes]
        self.assertEqual(len(ids), len(set(ids)), "id の重複")
        for i in ids:
            self.assertRegex(i, ID_RE)

    def test_context_known(self):
        for n in self.nodes:
            self.assertIn(n["context"], CONTEXTS, n["id"])

    def test_doc_url_is_official_docs(self):
        for n in self.nodes:
            self.assertTrue(n["doc_url"].startswith("https://www.sidefx.com/docs/"), f"{n['id']}: {n['doc_url']}")
            self.assertNotRegex(n["doc_url"], r"/docs/(houdini|hqueue|hengine|hdk|unreal|maya)\d", f"{n['id']}: 版つきパスは使わない(robots が禁止)")

    def test_list_fields(self):
        for n in self.nodes:
            for k, minimum in (("example_points", 2), ("use_cases", 2)):
                self.assertIsInstance(n[k], list, n["id"])
                self.assertGreaterEqual(len(n[k]), minimum, f"{n['id']}: {k}")
                for s in n[k]:
                    self.assertTrue(nonempty(s), f"{n['id']}: {k} に空の文字列")

    def test_combos(self):
        for n in self.nodes:
            self.assertIsInstance(n["combos"], list)
            self.assertGreaterEqual(len(n["combos"]), 1, f"{n['id']}: 組み合わせ例がない")
            for c in n["combos"]:
                self.assertTrue(nonempty(c.get("title")), n["id"])
                self.assertTrue(nonempty(c.get("note")), n["id"])
                chain = c.get("chain")
                self.assertIsInstance(chain, list, n["id"])
                self.assertGreaterEqual(len(chain), 2, f"{n['id']}: chain は 2 つ以上")
                for name in chain:
                    self.assertTrue(nonempty(name) and len(name) <= 40, f"{n['id']}: chain の名前 {name!r}")

    def test_before_after(self):
        for n in self.nodes:
            ba = n["before_after"]
            self.assertTrue(nonempty(ba.get("before")) and nonempty(ba.get("after")), f"{n['id']}: 前後の文章")
            img = ba.get("image")
            if img is not None:  # 任意。あるなら site/img/nodes/ にある実ファイル
                for side in ("before", "after"):
                    p = img.get(side)
                    self.assertTrue(nonempty(p) and p.startswith("img/nodes/") and ".." not in p, f"{n['id']}: {p}")
                    self.assertTrue((SITE / p).is_file(), f"{n['id']}: {p} がない")
                self.assertTrue(nonempty(img.get("alt")), f"{n['id']}: 画像の説明(alt)")

    def test_verified_nodes_have_type_and_params(self):
        for n in self.nodes:
            if n["verified"]:
                self.assertTrue(nonempty(n.get("type")), f"{n['id']}: verified なのに type がない")
                self.assertGreaterEqual(len(n.get("params", [])), 1, f"{n['id']}: verified なのに params がない")
            for p in n.get("params", []):
                self.assertTrue(nonempty(p.get("name")) and nonempty(p.get("note")), n["id"])

    def test_no_official_doc_text_markers(self):
        # 文章は自作。HTML は入れない(textContent だけで描画する)
        for n in self.nodes:
            blob = json.dumps(n, ensure_ascii=False)
            self.assertNotRegex(blob, r"<[a-zA-Z/]", f"{n['id']}: HTML タグらしき文字列")

    def test_site_copy_is_in_sync(self):
        copy = SITE / "data" / "nodes.json"
        self.assertTrue(copy.is_file(), "site/data/nodes.json がない(python -m collector か sync で作る)")
        self.assertEqual(json.loads(copy.read_text(encoding="utf-8")), self.doc)


class SyncTests(unittest.TestCase):
    def test_sync_copies_published_files(self):
        with tempfile.TemporaryDirectory() as d:
            data, site = Path(d) / "data", Path(d) / "site" / "data"
            data.mkdir()
            for name in ("items.json", "reference.json", "nodes.json"):
                (data / name).write_text(json.dumps({"n": name}), encoding="utf-8")
            (data / "fetch_state.json").write_text("{}", encoding="utf-8")
            sync_site_data(data, site)
            self.assertEqual(sorted(p.name for p in site.iterdir()), ["items.json", "nodes.json", "reference.json"])
            self.assertEqual(json.loads((site / "nodes.json").read_text(encoding="utf-8")), {"n": "nodes.json"})

    def test_sync_skips_missing(self):
        with tempfile.TemporaryDirectory() as d:
            data, site = Path(d) / "data", Path(d) / "site" / "data"
            data.mkdir()
            (data / "items.json").write_text("{}", encoding="utf-8")
            sync_site_data(data, site)
            self.assertEqual([p.name for p in site.iterdir()], ["items.json"])


if __name__ == "__main__":
    unittest.main()
