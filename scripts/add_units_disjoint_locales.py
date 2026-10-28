#!/usr/bin/env python3
"""补量纲纪律的跨单位说明文案（第二十二批 D 段）—— 给 7 个 locale 写回 1 个新 key。

用法：python3 add_units_disjoint_locales.py [--check]

★ 为什么要有这个脚本
-------------------
GTD 工作台的分账条上有一句**用户可见的量纲纪律说明**：
「两种单位不可相加：能量是燃料，注意力是闸门」。

★ 此前这句是**代码里硬写的中文**（`pages/GtdWorkspace.tsx`）⇒ ★ 它是
`specs/design/copy_terminology.json` 的 `units` 段 role 里那句内部契约
（「四者互不相加、不换算」）**之外的一份副本** ⇒ ★ 真相源改口径 ⇒ 这份不会跟着改
⇒ ★ **分叉**。⇒ 本脚本把这句**登记进 locale**（并由真相源派生），
让代码改为 `t()` 取用 ⇒ ★ locale 是**载体**，真相源才是**源**。

★ 为什么只加 1 个 key（★ 别顺手多造近义词）
--------------------------------------------
这句是**唯一**无法复用现有键的：
  · 能量标签 / 点单位 / 注意力标签 / 分钟单位 / 「至多」/ 深度占用上限提示
    ⇒ **全部复用** `zenskill.readout.*` 与 `zenskill.unit.*`（★ 零新增）
  · 「还剩」这个词 ⇒ 随「至多」改作**前缀**（与通用读数条同形）⇒ 一并消掉（★ 零新增）
⇒ ⇒ **只需 1 个新 key** ⇒ 7 语言各 1 条。

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

T: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.readout.unitsDisjoint": "两种单位不可相加：能量是燃料，注意力是闸门",
    },
    "en": {
        "zenskill.readout.unitsDisjoint": "These two units cannot be added: energy is fuel, attention is a gate",
    },
    "de": {
        "zenskill.readout.unitsDisjoint": "Diese beiden Einheiten lassen sich nicht addieren: Energie ist Treibstoff, Aufmerksamkeit ist ein Tor",
    },
    "es": {
        "zenskill.readout.unitsDisjoint": "Estas dos unidades no se suman: la energía es combustible, la atención es una compuerta",
    },
    "hu": {
        "zenskill.readout.unitsDisjoint": "E két egység nem adható össze: az energia üzemanyag, a figyelem kapu",
    },
    "ja": {
        "zenskill.readout.unitsDisjoint": "この2つの単位は足し合わせできません：エネルギーは燃料、集中力はゲート",
    },
    "pl": {
        "zenskill.readout.unitsDisjoint": "Te dwie jednostki nie sumują się: energia jest paliwem, uwaga jest bramką",
    },
}


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    bad = 0
    expected = set(T["zh-Hans"])
    for loc, table in T.items():
        if set(table) != expected:
            print(f"[FAIL] {loc}: key 集合与 zh-Hans 不一致")
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
        merged = {**data, **table}
        if check:
            if path.read_text(encoding="utf-8") != dump(merged):
                print(f"[FAIL] {loc}: 文件内容与预期不一致（--check 判红）")
                bad += 1
            else:
                print(f"[OK] {loc}: {len(table)} 条量纲纪律文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条量纲纪律文案（共 {len(merged)}）")

    keysets = {
        loc: set(json.loads((LOCALES_DIR / f"{loc}.json").read_text(encoding="utf-8")))
        for loc in T
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
    print("\n✅ 量纲纪律文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
