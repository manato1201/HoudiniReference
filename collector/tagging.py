"""キーワードによる簡易タグ付け(補助。精度は保証しない)。"""
from __future__ import annotations

import re

# タグ名 -> 正規表現(大文字小文字を区別しない)
TAG_RULES: dict[str, str] = {
    "VEX": r"\bvex\b|\bwrangle",
    "Solaris": r"\bsolaris\b|\blops\b|\busd\b",
    "Karma": r"\bkarma\b",
    "APEX": r"\bapex\b",
    "KineFX": r"\bkinefx\b|\brigging\b",
    "Vellum": r"\bvellum\b",
    "Pyro": r"\bpyro\b|\bsmoke\b|\bfire\b",
    "FLIP": r"\bflip\b|\bfluid",
    "RBD": r"\brbd\b|\bbullet\b|\bdestruction",
    "Copernicus": r"\bcopernicus\b|\bcops?\b",
    "Terrain": r"\bheightfield|\bterrain",
    "HDA": r"\bhda\b|digital asset",
    "PDG/TOPs": r"\bpdg\b|\btops\b",
    "Python": r"\bpython\b|\bhou\.",
    "Houdini Engine": r"houdini engine|\bhengine\b",
    "Unreal": r"\bunreal\b|\bue5\b",
    "Unity": r"\bunity\b",
    "Labs": r"\blabs\b",
    "Rendering": r"\bmantra\b|\brenderman\b|\bredshift\b|\barnold\b|\bocto\w*|\brender",
}
_COMPILED = {tag: re.compile(rx, re.IGNORECASE) for tag, rx in TAG_RULES.items()}
_VERSION = re.compile(r"\b(?:h(?:oudini)?\s?)?(1[89]|2\d)\.(0|5)(?:\.\d+)?\b", re.IGNORECASE)
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
