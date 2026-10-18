"""
SkillsVM — 技能列表视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


def _governance_map(slugs: List[str]) -> Dict[str, Dict[str, str]]:
    """skill_governance 只读查询：slug -> {tier, state}。

    直接 SELECT（不 import 写函数）；表不存在/库不可达返回空 dict，
    视图降级隐藏 Tier/State 列。
    """
    if not slugs:
        return {}
    try:
        from zenskill.skills.skill_governance import _default_db
        marks = ",".join("?" * len(slugs))
        with _default_db().connect() as conn:
            rows = conn.execute(
                f"SELECT slug, tier, state FROM skill_governance "
                f"WHERE slug IN ({marks})",
                tuple(slugs),
            ).fetchall()
        return {
            str(r["slug"]): {
                "tier": str(r["tier"] or "T2"),
                "state": str(r["state"] or "active"),
            }
            for r in rows
        }
    except Exception:
        return {}


@register_viewmodel("skills")
@dataclass
class SkillsVM(ViewModel):
    """已安装技能列表"""

    title: str = "技能列表"
    icon: str = "📦"

    skills: List[Dict] = field(default_factory=list)
    filter_category: str = ""
    governance: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, category: str = "") -> "SkillsVM":
        vm = cls(filter_category=category)
        try:
            from zenskill.core.skill_profile import SkillProfile
            profiles = SkillProfile.list_all(
                category=category or None,
                limit=30,
            )
            for p in profiles:
                vm.skills.append({
                    "id": p.skill_id,
                    "name": p.name,
                    "level": p.level or "NOVICE",
                    "category": p.category,
                    "source": p.source,
                    "usage": p.total_interactions,
                    "icon": p.icon or "📦",
                })
            vm.governance = _governance_map([p.skill_id for p in profiles])
            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def _table_spec(self) -> tuple:
        """构建表格 headers/rows；governance 数据可用时追加 Tier/State 列"""
        has_gov = bool(self.governance)
        headers = ["技能", "等级", "分类", "来源"] + (["Tier", "State"] if has_gov else [])
        level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                       "EXPERT": "⭐", "MASTER": "👑"}
        rows = []
        for s in self.skills:
            icon = level_icons.get(s["level"], "")
            row = [
                f"{s['icon']} {s['name']}",
                f"{icon} {s['level']}",
                s["category"],
                s["source"],
            ]
            if has_gov:
                g = self.governance.get(s["id"]) or {}
                row.append(g.get("tier", "T2"))
                row.append(g.get("state", "active"))
            rows.append(row)
        return headers, rows

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"
        if not self.skills:
            return "  📭 暂无技能"

        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        headers, rows = self._table_spec()

        return r.table(
            type('s', (), {'headers': headers, 'rows': rows, 'title': '', 'color': 'primary'})()
        )

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ 加载失败: {self.error}[/red]"
        if not self.skills:
            return "  [dim]📭 暂无技能[/dim]"

        from zenskill.render import RichRenderer
        r = RichRenderer()

        headers, rows = self._table_spec()

        return r.table(
            type('s', (), {'headers': headers, 'rows': rows, 'title': '', 'color': 'primary'})()
        )
