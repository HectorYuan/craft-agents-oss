#!/usr/bin/env python3
"""补项目域读数文案（第二十一批 B 段 ·「项目路径 ↔ 项目实体」整合）—— 给 7 个 locale 写回 7 个新 key。

用法：python3 add_project_domain_locales.py [--check]

★ 为什么要有这个脚本
-------------------
craft 项目页要显示**该项目的 GTD 读数**（进度 / 下一步行动）⇒ 新增一组读数文案：
「进度」「7 / 15 行动完成」「还没有行动」「还没有关联的 GTD 项目」「关联到多个，无法确定」
「下一步行动 · 按能量排序」「能量 N 点」。

★ 口径纪律：★ 「**读不到 ≠ 读到 0**」在文案层就要分开 ——
  · 「还没有关联的 GTD 项目」= **读不到**（没建立关联）
  · 「还没有行动」= **确实还没有行动**（关联到了，但这个项目下没有行动）
  ⇒ 两个不同的空 ⇒ 两句不同的文案 ⇒ 绝不共用一句。

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
★ 量纲纪律：本批文案只涉及**计数与百分比** ⇒ 绝不出现「点」「分钟」之外的换算表述。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

T: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.readout.projectProgress": "进度",
        "zenskill.readout.projectProgressCount": "{done} / {total} 行动完成",
        "zenskill.readout.projectNoActions": "还没有行动",
        "zenskill.readout.projectNoLink": "还没有关联的 GTD 项目",
        "zenskill.readout.projectAmbiguous": "这个 craft 项目关联了多个 GTD 项目，无法确定是哪个",
        "zenskill.readout.projectNextActions": "下一步行动 · 按能量排序",
        "zenskill.readout.projectEnergy": "能量 {n} 点",
    },
    "en": {
        "zenskill.readout.projectProgress": "Progress",
        "zenskill.readout.projectProgressCount": "{done} / {total} actions done",
        "zenskill.readout.projectNoActions": "No actions yet",
        "zenskill.readout.projectNoLink": "Not linked to a GTD project yet",
        "zenskill.readout.projectAmbiguous": "This craft project links to multiple GTD projects — can't tell which",
        "zenskill.readout.projectNextActions": "Next actions · by energy",
        "zenskill.readout.projectEnergy": "Energy {n} pts",
    },
    "de": {
        "zenskill.readout.projectProgress": "Fortschritt",
        "zenskill.readout.projectProgressCount": "{done} / {total} Aktionen erledigt",
        "zenskill.readout.projectNoActions": "Noch keine Aktionen",
        "zenskill.readout.projectNoLink": "Noch keinem GTD-Projekt zugeordnet",
        "zenskill.readout.projectAmbiguous": "Dieses craft-Projekt ist mehreren GTD-Projekten zugeordnet — welches ist gemeint?",
        "zenskill.readout.projectNextActions": "Nächste Aktionen · nach Energie",
        "zenskill.readout.projectEnergy": "Energie {n} Punkte",
    },
    "es": {
        "zenskill.readout.projectProgress": "Progreso",
        "zenskill.readout.projectProgressCount": "{done} / {total} acciones completadas",
        "zenskill.readout.projectNoActions": "Aún no hay acciones",
        "zenskill.readout.projectNoLink": "Aún sin proyecto GTD vinculado",
        "zenskill.readout.projectAmbiguous": "Este proyecto de craft está vinculado a varios proyectos GTD — no se puede determinar cuál",
        "zenskill.readout.projectNextActions": "Próximas acciones · por energía",
        "zenskill.readout.projectEnergy": "Energía {n} pts",
    },
    "hu": {
        "zenskill.readout.projectProgress": "Előrehaladás",
        "zenskill.readout.projectProgressCount": "{done} / {total} művelet kész",
        "zenskill.readout.projectNoActions": "Még nincs művelet",
        "zenskill.readout.projectNoLink": "Még nincs GTD-projekthez kötve",
        "zenskill.readout.projectAmbiguous": "Ez a craft-projekt több GTD-projekthez is kötve — nem dönthető el, melyik",
        "zenskill.readout.projectNextActions": "Következő műveletek · energia szerint",
        "zenskill.readout.projectEnergy": "Energia {n} pont",
    },
    "ja": {
        "zenskill.readout.projectProgress": "進捗",
        "zenskill.readout.projectProgressCount": "{done} / {total} アクション完了",
        "zenskill.readout.projectNoActions": "まだアクションがありません",
        "zenskill.readout.projectNoLink": "GTD プロジェクト未連携",
        "zenskill.readout.projectAmbiguous": "この craft プロジェクトは複数の GTD プロジェクトに関連しています（特定できません）",
        "zenskill.readout.projectNextActions": "次のアクション · エネルギー順",
        "zenskill.readout.projectEnergy": "エネルギー {n} ポイント",
    },
    "pl": {
        "zenskill.readout.projectProgress": "Postęp",
        "zenskill.readout.projectProgressCount": "{done} / {total} ukończonych działań",
        "zenskill.readout.projectNoActions": "Brak działań",
        "zenskill.readout.projectNoLink": "Niepowiązano jeszcze z projektem GTD",
        "zenskill.readout.projectAmbiguous": "Ten projekt craft jest powiązany z wieloma projektami GTD — nie da się określić, z którym",
        "zenskill.readout.projectNextActions": "Następne działania · według energii",
        "zenskill.readout.projectEnergy": "Energia {n} pkt",
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
                print(f"[OK] {loc}: {len(table)} 条项目域读数文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条项目域读数文案（共 {len(merged)}）")

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
    print("\n✅ 项目域读数文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
