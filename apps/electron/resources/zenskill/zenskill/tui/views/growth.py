"""
GrowthVM — 成长视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import ViewModel, register_viewmodel


@register_viewmodel("growth")
@dataclass
class GrowthVM(ViewModel):
    """五维成长状态"""

    title: str = "成长状态"
    icon: str = "📈"

    skill_id: str = "zenskill-core"
    level: str = "NOVICE"
    dimensions: Dict[str, float] = field(default_factory=dict)
    total_usage: int = 0
    success_rate: float = 0.0

    @classmethod
    def load(cls, skill_id: str = "zenskill-core") -> "GrowthVM":
        vm = cls(skill_id=skill_id)
        try:
            from zenskill.core.skill_profile import SkillProfile
            profile = SkillProfile.load(skill_id)
            if profile:
                vm.level = profile.level or "NOVICE"
                vm.total_usage = profile.total_interactions
                vm.success_rate = profile.success_rate
                vm.dimensions = {
                    "熟练度": profile.proficiency or 0.0,
                    "稳定性": profile.stability or 0.0,
                    "满意度": profile.satisfaction or 0.0,
                    "响应力": profile.responsiveness or 0.0,
                    "记忆力": profile.memory or 0.0,
                }
                vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"

        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        lines = []

        # 等级+统计
        icon_lv = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                   "EXPERT": "⭐", "MASTER": "👑"}.get(self.level, "")
        lines.append(r.card(
            type('s', (), {'title': f'{icon_lv} {self.level}', 'icon': 'growth',
                           'fields': [("总调用", str(self.total_usage)),
                                      ("成功率", f"{self.success_rate:.0%}")],
                           'footer': '', 'color': 'primary'})()
        ))

        # 五维条形图
        data = [(k, v, 1.0) for k, v in self.dimensions.items()]
        colors = ["dim_proficiency", "dim_stability", "dim_satisfaction",
                  "dim_responsiveness", "dim_memory"]
        lines.append(r.bar_chart(
            type('s', (), {'data': data, 'width': 20, 'colors': colors})()
        ))

        return "\n".join(lines)

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ 加载失败: {self.error}[/red]"

        from zenskill.render import RichRenderer
        r = RichRenderer()
        lines = []

        icon_lv = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                   "EXPERT": "⭐", "MASTER": "👑"}.get(self.level, "")
        lines.append(r.card(
            type('s', (), {'title': f'{icon_lv} {self.level}', 'icon': 'growth',
                           'fields': [("总调用", str(self.total_usage)),
                                      ("成功率", f"{self.success_rate:.0%}")],
                           'footer': '', 'color': 'primary'})()
        ))

        data = [(k, v, 1.0) for k, v in self.dimensions.items()]
        colors = ["dim_proficiency", "dim_stability", "dim_satisfaction",
                  "dim_responsiveness", "dim_memory"]
        lines.append(r.bar_chart(
            type('s', (), {'data': data, 'width': 20, 'colors': colors})()
        ))

        return "\n".join(lines)
