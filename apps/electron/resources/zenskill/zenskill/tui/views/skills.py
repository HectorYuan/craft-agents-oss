"""
SkillsVM — 技能列表视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("skills")
@dataclass
class SkillsVM(ViewModel):
    """已安装技能列表"""

    title: str = "技能列表"
    icon: str = "📦"

    skills: List[Dict] = field(default_factory=list)
    filter_category: str = ""

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
            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"
        if not self.skills:
            return "  📭 暂无技能"

        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                       "EXPERT": "⭐", "MASTER": "👑"}
        headers = ["技能", "等级", "分类", "来源"]
        rows = []
        for s in self.skills:
            icon = level_icons.get(s["level"], "")
            rows.append([
                f"{s['icon']} {s['name']}",
                f"{icon} {s['level']}",
                s["category"],
                s["source"],
            ])

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

        level_icons = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                       "EXPERT": "⭐", "MASTER": "👑"}
        headers = ["技能", "等级", "分类", "来源"]
        rows = []
        for s in self.skills:
            icon = level_icons.get(s["level"], "")
            rows.append([
                f"{s['icon']} {s['name']}",
                f"{icon} {s['level']}",
                s["category"],
                s["source"],
            ])

        return r.table(
            type('s', (), {'headers': headers, 'rows': rows, 'title': '', 'color': 'primary'})()
        )
