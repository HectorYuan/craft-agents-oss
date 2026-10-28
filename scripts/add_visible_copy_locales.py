#!/usr/bin/env python3
"""补「用户直接可见」的一批界面文案（第二十二批 D-3 第一批）—— 给 7 个 locale 写回 7 个新 key。

用法：python3 scripts/add_visible_copy_locales.py [--check]

★ 为什么要有这个脚本
-------------------
D-3 的取证结论：`components/zenskill/**` 里除 D-1 已迁的 5 处外，还有 **18 处纯硬编码
中文**（用户直接可见的 tooltip / toast / 按钮 / 兜底文案）。
⇒ 本脚本处理**第一批**（6 个文件位置、**7 个键**）—— 选它们的理由：
  · **用户直接看到**（tooltip / toast）⇒ 优先级最高
  · 文件**已经在用 i18n**（`ActionsPanel` / `ZenSkillDataPanel` 都有 `useTranslation`）
    ⇒ 迁移**不引入新机制**
  · 顺带修两处**同一界面两种语言**的混用（`'Delete'` 英文 vs 「点击再次确认删除」中文）
    与一处**模板字面量**（`⚠ ${n} 个行动已逾期` ⇒ 之前不在任何扫描器射程内）

★ 键的落点：沿用 `zenskill.readout.*` 前缀 ⇒ ★ **零门禁改动**（C-11 判据 5 已在管这个前缀）
  ⇒ ★ 真相源 `stateCopy.readout.entries` 同步登记（**locale 是载体，真相源才是源**）

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
        "zenskill.readout.agentExecute": "用 Agent 执行",
        "zenskill.readout.confirmDeleteAgain": "点击再次确认删除",
        "zenskill.readout.deleteAction": "删除",
        "zenskill.readout.switchBoard": "切换看板",
        "zenskill.readout.switchList": "切换列表",
        "zenskill.readout.energyLowToast": "⚡ 能量不足，建议休息一下",
        "zenskill.readout.actionsOverdue": "⚠ {n} 个行动已逾期",
    },
    "en": {
        "zenskill.readout.agentExecute": "Run with Agent",
        "zenskill.readout.confirmDeleteAgain": "Click again to confirm delete",
        "zenskill.readout.deleteAction": "Delete",
        "zenskill.readout.switchBoard": "Switch to board",
        "zenskill.readout.switchList": "Switch to list",
        "zenskill.readout.energyLowToast": "⚡ Low energy — consider a break",
        "zenskill.readout.actionsOverdue": "⚠ {n} overdue actions",
    },
    "de": {
        "zenskill.readout.agentExecute": "Mit Agent ausführen",
        "zenskill.readout.confirmDeleteAgain": "Erneut klicken zum Löschen",
        "zenskill.readout.deleteAction": "Löschen",
        "zenskill.readout.switchBoard": "Zur Übersicht wechseln",
        "zenskill.readout.switchList": "Zur Liste wechseln",
        "zenskill.readout.energyLowToast": "⚡ Wenig Energie — eine Pause ist sinnvoll",
        "zenskill.readout.actionsOverdue": "⚠ {n} überfällige Aktionen",
    },
    "es": {
        "zenskill.readout.agentExecute": "Ejecutar con el Agente",
        "zenskill.readout.confirmDeleteAgain": "Haz clic de nuevo para confirmar la eliminación",
        "zenskill.readout.deleteAction": "Eliminar",
        "zenskill.readout.switchBoard": "Cambiar a vista de tablero",
        "zenskill.readout.switchList": "Cambiar a lista",
        "zenskill.readout.energyLowToast": "⚡ Energía baja: considera descansar",
        "zenskill.readout.actionsOverdue": "⚠ {n} acciones vencidas",
    },
    "hu": {
        "zenskill.readout.agentExecute": "Futtatás Agenttel",
        "zenskill.readout.confirmDeleteAgain": "Kattintson újra a törlés megerősítéséhez",
        "zenskill.readout.deleteAction": "Törlés",
        "zenskill.readout.switchBoard": "Váltás táblára",
        "zenskill.readout.switchList": "Váltás listára",
        "zenskill.readout.energyLowToast": "⚡ Kevés energia — érdemes pihenni",
        "zenskill.readout.actionsOverdue": "⚠ {n} lejárt feladat",
    },
    "ja": {
        "zenskill.readout.agentExecute": "Agent で実行",
        "zenskill.readout.confirmDeleteAgain": "もう一度クリックで削除を確認",
        "zenskill.readout.deleteAction": "削除",
        "zenskill.readout.switchBoard": "ボード表示に切替",
        "zenskill.readout.switchList": "リスト表示に切替",
        "zenskill.readout.energyLowToast": "⚡ エネルギーが不足しています。休んでください。",
        "zenskill.readout.actionsOverdue": "⚠ 期限超過のアクション {n} 件",
    },
    "pl": {
        "zenskill.readout.agentExecute": "Uruchom przez Agenta",
        "zenskill.readout.confirmDeleteAgain": "Kliknij ponownie, aby potwierdzić usunięcie",
        "zenskill.readout.deleteAction": "Usuń",
        "zenskill.readout.switchBoard": "Przełącz na tablicę",
        "zenskill.readout.switchList": "Przełącz na listę",
        "zenskill.readout.energyLowToast": "⚡ Mało energii — warto odpocząć",
        "zenskill.readout.actionsOverdue": "⚠ {n} zaległych akcji",
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
                print(f"[OK] {loc}: {len(table)} 条界面文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条界面文案（共 {len(merged)}）")

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
    print("\n✅ 界面文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
