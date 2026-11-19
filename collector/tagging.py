"""キーワードによる簡易タグ付け(補助。精度は保証しない)。英語と日本語の語彙の両方を見る。"""
from __future__ import annotations

import re

# タグ名 -> 正規表現(大文字小文字を区別しない)。`\b` は _ascii_boundaries で ASCII の英数字との境界に直される。
TAG_RULES: dict[str, str] = {
    "VEX": r"\bvex\b|\bwrangle|ベックス",
    "Solaris": r"\bsolaris\b|\blops\b|\busd\b|ソラリス",
    "Karma": r"\bkarma\b|カルマ",
    "APEX": r"\bapex\b",
    "KineFX": r"\bkinefx\b|\brigging\b|リギング|リグ",
    "Vellum": r"\bvellum\b|ベラム|ヴェラム|クロスシミュ",
    "Pyro": r"\bpyro\b|\bsmoke\b|\bfire\b|パイロ|煙|炎",
    "FLIP": r"\bflip\b|\bfluid|流体",
    "RBD": r"\brbd\b|\bbullet\b|\bdestruction|破壊|リジッドボディ",
    "Copernicus": r"\bcopernic\w*|\bcops?\b|コペルニクス",
    "Terrain": r"\bheightfield|\bterrain|ハイトフィールド|地形",
    "HDA": r"\bhda\b|digital asset|デジタルアセット",
    "PDG/TOPs": r"\bpdg\b|\btops\b",
    "Python": r"\bpython\b|\bhou\.|パイソン",
    "Houdini Engine": r"houdini engine|\bhengine\b|ヒューディニエンジン",
    "Unreal": r"\bunreal\b|\bue[45]\b|アンリアル",
    "Unity": r"\bunity\b|ユニティ",
    "Labs": r"\blabs\b",
    "Simulation": r"\bsimulat|\bsim\b|シミュレーション",
    "Procedural": r"\bprocedural|プロシージャル|プロシージャ",
    "Rendering": r"\bmantra\b|\brenderman\b|\bredshift\b|\barnold\b|\bocto\w*|\brender|レンダ",
}


def _ascii_boundaries(rx: str) -> str:
    r"""`\b` は日本語の直前直後(「VEXの」「22.0の」など)で働かないので、ASCII の英数字との境界に置き換える。"""
    out: list[str] = []
    i = 0
    while i < len(rx):
        if rx.startswith("\\b", i):
            leading = not out or out[-1] in "|("
            out.append("(?<![A-Za-z0-9_])" if leading else "(?![A-Za-z0-9_])")
            i += 2
        else:
            out.append(rx[i])
            i += 1
    return "".join(out)


_COMPILED = {tag: re.compile(_ascii_boundaries(rx), re.IGNORECASE) for tag, rx in TAG_RULES.items()}
_VERSION = re.compile(_ascii_boundaries(r"\b(?:h(?:oudini)?\s?)?(1[89]|2\d)\.(0|5)(?:\.\d+)?\b"), re.IGNORECASE)
MAX_TAGS = 6


def auto_tags(text: str, base: list[str] | None = None) -> list[str]:
    tags: list[str] = list(base or [])
    for tag, rx in _COMPILED.items():
        if rx.search(text) and tag not in tags:
            tags.append(tag)
    m = _VERSION.search(text)
    if m:
        v = f"H{m.group(1)}.{m.group(2)}"
        if v not in tags:
            tags.append(v)
    return tags[:MAX_TAGS]
