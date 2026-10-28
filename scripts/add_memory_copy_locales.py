#!/usr/bin/env python3
"""记忆页文案迁进 locale（第二十二批 D-3 第二批）—— 7 locale：+5 键、−5 键。

用法：python3 scripts/add_memory_copy_locales.py [--check]

★ 为什么要有这个脚本
-------------------
`pages/MemoryBrowser.tsx` 里 5 处中文（升华中… / 整合记忆 / L1 工作 / L2 情景 / L3 语义）
是**纯硬编码** ⇒ 没有 locale key ⇒ 任何门禁都管不到。

★ 同时做一件事：★ **收敛重复的维度名命名空间**
  · `zenskill.profile.dim.*`（5）与 `zenskill.skillGraph.dim.*`（5）**值逐字相同**
    ⇒ ★ 同一句话被登记了两遍 ⇒ **保留 `profile.dim.*` 作唯一来源，删掉 `skillGraph.dim.*`**

★ 键的前缀：★ 用**窄前缀** `zenskill.memoryCopy.` ⇒ ★ 零牵连
  （既有 `zenskill.memory.*` 的 6 个键不受影响 ⇒ 不必把它们也登记进真相源）
  ⇒ 真相源对应新增 `stateCopy.memoryCopy` 段（**locale 是载体，真相源才是源**）

★ 删除是**破坏性**动作 ⇒ 本脚本显式列出被删的键 ⇒ `--check` 时逐条核对
  （★ 若将来要恢复某个键，改这里 + 真相源两处 ⇒ 别只改一处）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

#: 新增键
ADD: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.memoryCopy.consolidating": "升华中…",
        "zenskill.memoryCopy.consolidate": "整合记忆",
        "zenskill.memoryCopy.layerL1": "L1 工作",
        "zenskill.memoryCopy.layerL2": "L2 情景",
        "zenskill.memoryCopy.layerL3": "L3 语义",
        "zenskill.memoryCopy.noSemanticFacts": "暂无语义事实 — 点击右上「整合记忆」从情景记忆升华",
    },
    "en": {
        "zenskill.memoryCopy.consolidating": "Consolidating…",
        "zenskill.memoryCopy.consolidate": "Consolidate memories",
        "zenskill.memoryCopy.layerL1": "L1 Working",
        "zenskill.memoryCopy.layerL2": "L2 Episodic",
        "zenskill.memoryCopy.layerL3": "L3 Semantic",
        "zenskill.memoryCopy.noSemanticFacts": "No semantic facts yet — consolidate episodic memories to distill them",
    },
    "de": {
        "zenskill.memoryCopy.consolidating": "Konsolidierung…",
        "zenskill.memoryCopy.consolidate": "Erinnerungen konsolidieren",
        "zenskill.memoryCopy.layerL1": "L1 Arbeit",
        "zenskill.memoryCopy.layerL2": "L2 Episodisch",
        "zenskill.memoryCopy.layerL3": "L3 Semantisch",
        "zenskill.memoryCopy.noSemanticFacts": "Noch keine semantischen Fakten — episodische Erinnerungen konsolidieren",
    },
    "es": {
        "zenskill.memoryCopy.consolidating": "Consolidando…",
        "zenskill.memoryCopy.consolidate": "Consolidar recuerdos",
        "zenskill.memoryCopy.layerL1": "L1 Trabajo",
        "zenskill.memoryCopy.layerL2": "L2 Episódica",
        "zenskill.memoryCopy.layerL3": "L3 Semántica",
        "zenskill.memoryCopy.noSemanticFacts": "Aún no hay hechos semánticos — consolida los recuerdos episódicos",
    },
    "hu": {
        "zenskill.memoryCopy.consolidating": "Összevonás…",
        "zenskill.memoryCopy.consolidate": "Emlékek összevonása",
        "zenskill.memoryCopy.layerL1": "L1 Munkamemória",
        "zenskill.memoryCopy.layerL2": "L2 Élményszerű",
        "zenskill.memoryCopy.layerL3": "L3 Szemantikus",
        "zenskill.memoryCopy.noSemanticFacts": "Még nincsen szemantikai tények — konszolidáld az élményszerű emlékeket",
    },
    "ja": {
        "zenskill.memoryCopy.consolidating": "統合中…",
        "zenskill.memoryCopy.consolidate": "記憶を統合",
        "zenskill.memoryCopy.layerL1": "L1 作業記憶",
        "zenskill.memoryCopy.layerL2": "L2 情景記憶",
        "zenskill.memoryCopy.layerL3": "L3 意味記憶",
        "zenskill.memoryCopy.noSemanticFacts": "まだ意味記憶がありません — 情景記憶を統合して昇華させましょう",
    },
    "pl": {
        "zenskill.memoryCopy.consolidating": "Konsolidacja…",
        "zenskill.memoryCopy.consolidate": "Skonsoliduj wspomnienia",
        "zenskill.memoryCopy.layerL1": "L1 Robocza",
        "zenskill.memoryCopy.layerL2": "L2 Epizodyczna",
        "zenskill.memoryCopy.layerL3": "L3 Semantyczna",
        "zenskill.memoryCopy.noSemanticFacts": "Nie ma jeszcze faktów semantycznych — skonsoliduj wspomnienia epizodyczne",
    },
}

#: ★ 删除键（维度名收敛：保留 `profile.dim.*`，删掉重复的 `skillGraph.dim.*`）
DROP: tuple[str, ...] = (
    "zenskill.skillGraph.dim.proficiency",
    "zenskill.skillGraph.dim.stability",
    "zenskill.skillGraph.dim.satisfaction",
    "zenskill.skillGraph.dim.responsiveness",
    "zenskill.skillGraph.dim.memory",
)


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    bad = 0
    expected = set(ADD["zh-Hans"])
    for loc, table in ADD.items():
        if set(table) != expected:
            print(f"[FAIL] {loc}: 新增 key 集合与 zh-Hans 不一致")
            bad += 1
        path = LOCALES_DIR / f"{loc}.json"
        if not path.exists():
            print(f"[FAIL] {loc}: locale 文件不存在")
            bad += 1
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = expected - set(data)
        if missing:
            if check:
                print(f"[FAIL] {loc}: 缺 {len(missing)} 个 key")
                bad += 1
            else:
                print(f"[新增] {loc}: 新增 {len(missing)} 个 key（{', '.join(sorted(missing))}）")
        still = [k for k in DROP if k in data]
        if still:
            if check:
                print(f"[FAIL] {loc}: 待删键仍在（{', '.join(still)}）")
                bad += 1
            else:
                print(f"[删除] {loc}: 删除 {len(still)} 个重复键")
        merged = {k: v for k, v in {**data, **table}.items() if k not in DROP}
        if check:
            if path.read_text(encoding="utf-8") != dump(merged):
                print(f"[FAIL] {loc}: 文件内容与预期不一致（--check 判红）")
                bad += 1
            else:
                print(f"[OK] {loc}: {len(table)} 条记忆页文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条记忆页文案（共 {len(merged)}）")

    keysets = {
        loc: set(json.loads((LOCALES_DIR / f"{loc}.json").read_text(encoding="utf-8")))
        for loc in ADD
        if (LOCALES_DIR / f"{loc}.json").exists()
    }
    base = keysets.get("zh-Hans", set())
    for loc, ks in keysets.items():
        if ks != base:
            print(f"[FAIL] {loc}: 与 zh-Hans 的 key 集合不一致（差 {len(ks ^ base)} 项）")
            bad += 1
    if bad:
        print(f"\n[FAIL] {bad} 项不通过")
        return 1
    print("\n✅ 记忆页文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
