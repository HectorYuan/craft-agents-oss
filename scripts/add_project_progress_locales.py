#!/usr/bin/env python3
"""补项目域读数文案（第二十一批 C 段）—— 给 7 个 locale 写回 1 个新 key。

用法：python3 add_project_progress_locales.py [--check]

★ 为什么要有这个脚本
-------------------
项目域的**域特有读数**此前**没有分子分母** —— GUI 的进度条 title 只能显示百分比，
而「46%（7 / 15 行动完成）」这种「完成数 / 总数」的表述才是 GTD 的原话
（稿上「进度 · 46%（7 / 15 行动完成）」）。
⇒ 本批把 `done` / `total` 补进 `project_list` 载荷 ⇒ GUI 显示「7 / 15 行动完成」。

★ ★ 顺带修掉一处**真缺陷**：后端 `project_list.progress` 原先给 **0–100 整数**，
  而 vendor 的 `ProjectsPanel` 按 **0–1 比例**用（`* 100`）⇒ ★ **进度条恒满、title 显示 4600%**。
  ⇒ 本批把口径统一为 **0–1 比例**（与 `delegation_status.ratio`、`AchievementGrid.progress` 一致），
  并让 TUI 侧不再**硬编码 0**（此前 TUI 的项目进度条**恒为空**）。

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
★ 量纲纪律：本批文案只涉及**计数** ⇒ 绝不出现「点」「分钟」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

# ── 本批要写的文案（项目域读数：1 条）──
T: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} 行动完成",
    },
    "en": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} actions done",
    },
    "de": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} Aktionen erledigt",
    },
    "es": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} acciones completadas",
    },
    "hu": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} művelet kész",
    },
    "ja": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} アクション完了",
    },
    "pl": {
        "zenskill.gtd.projects.progressCount": "{done} / {total} ukończonych działań",
    },
}

# ★ 量纲纪律自检：本批文案里**不得**出现「点」「分钟」两种量纲单位
FORBIDDEN_UNITS = ("点", "分钟")


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    bad = 0

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
