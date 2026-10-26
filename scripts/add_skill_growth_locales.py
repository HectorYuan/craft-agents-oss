#!/usr/bin/env python3
"""补技能域成长契约的读数文案（第二十一批 B 段）—— 给 7 个 locale 写回 7 个新 key。

用法：python3 add_skill_growth_locales.py [--check]

★ 为什么要有这个脚本
-------------------
技能域的**域特有读数**（成长契约：等级 / 里程碑 / 使用记录）在设计稿上写着
「ZenSkill 13 字段（等级 / 里程碑 / 使用记录）」，运行时数据也早已存在
（`core/skill_profile.py`）—— 但此前**没有只读出口、没有 GUI 读数条**。
第二十一批 B 段新增只读 MCP 工具 `skill_growth` + 组件 `SkillGrowthReadout`，
这两个组件里的文案**必须**有出处 ⇒ 主仓真相源 `copy_terminology.json` 的
`stateCopy.readout` 段登记了本批 7 条，主仓门禁 C-11 判据 5 守着
（locale 里 `zenskill.readout.*` 必须在册）。

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
★ 口径纪律：7 个 locale **key 集合必须完全一致**，每个 locale 都要给全部条目。
★ 量纲纪律：本批文案只涉及**等级名 / 计数 / 百分比** —— 绝不出现「点」「分钟」
  （那两种量纲属于能量与注意力，读数条里各占一格，不与成长契约混算）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

# ── 本批要写的文案（技能域成长契约读数：7 条）──
T: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.readout.skillLevel": "等级",
        "zenskill.readout.skillProgress": "进度 {p}%",
        "zenskill.readout.skillMilestones": "里程碑",
        "zenskill.readout.skillMilestoneCount": "{n} 个",
        "zenskill.readout.skillUsage": "使用记录",
        "zenskill.readout.skillUsageCount": "{n} 次",
        "zenskill.readout.skillSuccessRate": "成功率 {p}%",
    },
    "en": {
        "zenskill.readout.skillLevel": "Level",
        "zenskill.readout.skillProgress": "Progress {p}%",
        "zenskill.readout.skillMilestones": "Milestones",
        "zenskill.readout.skillMilestoneCount": "{n}",
        "zenskill.readout.skillUsage": "Usage",
        "zenskill.readout.skillUsageCount": "{n} uses",
        "zenskill.readout.skillSuccessRate": "Success rate {p}%",
    },
    "de": {
        "zenskill.readout.skillLevel": "Stufe",
        "zenskill.readout.skillProgress": "Fortschritt {p}%",
        "zenskill.readout.skillMilestones": "Meilensteine",
        "zenskill.readout.skillMilestoneCount": "{n}",
        "zenskill.readout.skillUsage": "Nutzung",
        "zenskill.readout.skillUsageCount": "{n} Nutzungen",
        "zenskill.readout.skillSuccessRate": "Erfolgsquote {p}%",
    },
    "es": {
        "zenskill.readout.skillLevel": "Nivel",
        "zenskill.readout.skillProgress": "Progreso {p}%",
        "zenskill.readout.skillMilestones": "Hitos",
        "zenskill.readout.skillMilestoneCount": "{n}",
        "zenskill.readout.skillUsage": "Uso",
        "zenskill.readout.skillUsageCount": "{n} usos",
        "zenskill.readout.skillSuccessRate": "Tasa de éxito {p}%",
    },
    "hu": {
        "zenskill.readout.skillLevel": "Szint",
        "zenskill.readout.skillProgress": "Előrehaladás {p}%",
        "zenskill.readout.skillMilestones": "Mérföldkövek",
        "zenskill.readout.skillMilestoneCount": "{n}",
        "zenskill.readout.skillUsage": "Használat",
        "zenskill.readout.skillUsageCount": "{n} használat",
        "zenskill.readout.skillSuccessRate": "Sikerarány {p}%",
    },
    "ja": {
        "zenskill.readout.skillLevel": "レベル",
        "zenskill.readout.skillProgress": "進捗 {p}%",
        "zenskill.readout.skillMilestones": "マイルストーン",
        "zenskill.readout.skillMilestoneCount": "{n} 件",
        "zenskill.readout.skillUsage": "利用履歴",
        "zenskill.readout.skillUsageCount": "{n} 回",
        "zenskill.readout.skillSuccessRate": "成功率 {p}%",
    },
    "pl": {
        "zenskill.readout.skillLevel": "Poziom",
        "zenskill.readout.skillProgress": "Postęp {p}%",
        "zenskill.readout.skillMilestones": "Kamienie milowe",
        "zenskill.readout.skillMilestoneCount": "{n}",
        "zenskill.readout.skillUsage": "Użytkowanie",
        "zenskill.readout.skillUsageCount": "{n} użyć",
        "zenskill.readout.skillSuccessRate": "Skuteczność {p}%",
    },
}

# ★ 量纲纪律自检：本批文案里**不得**出现「点」「分钟」两种量纲单位
FORBIDDEN_UNITS = ("点", "分钟")


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    bad = 0

    # ── 自检：本批文案不得混用量纲 ──
    for loc, table in T.items():
        for k, v in table.items():
            for unit in FORBIDDEN_UNITS:
                if unit in v:
                    print(f"[FAIL] {loc}: {k} 含其它量纲单位「{unit}」")
                    bad += 1

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
                print(f"[OK] {loc}: {len(table)} 条成长契约读数文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条成长契约读数文案（共 {len(merged)}）")

    # 全 locale key 集合一致性
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
    print("\n✅ 成长契约读数文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
