"""
DashboardVM — 仪表盘视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("dashboard")
@dataclass
class DashboardVM(ViewModel):
    """技能概览仪表盘"""

    title: str = "仪表盘"
    icon: str = "📊"

    # 数据
    skill_count: int = 0
    active_skills: int = 0
    level_distribution: Dict[str, int] = field(default_factory=dict)
    recent_events: List[str] = field(default_factory=list)
    top_skills: List[Dict] = field(default_factory=list)
    total_events: int = 0

    @classmethod
    def load(cls) -> "DashboardVM":
        """从 DB 加载仪表盘数据"""
        vm = cls()
        try:
            from zenskill.core.skill_profile import SkillProfile
            profiles = SkillProfile.list_all(limit=50)

            vm.skill_count = len(profiles)
            vm.active_skills = sum(1 for p in profiles if p.is_active)

            # 等级分布
            for p in profiles:
                lv = p.level or "NOVICE"
                vm.level_distribution[lv] = vm.level_distribution.get(lv, 0) + 1

            # Top 技能
            sorted_profiles = sorted(profiles, key=lambda p: p.total_interactions, reverse=True)
            for p in sorted_profiles[:5]:
                vm.top_skills.append({
                    "name": p.name,
                    "level": p.level or "NOVICE",
                    "category": p.category,
                    "usage": p.total_interactions,
                    "icon": p.icon or "📦",
                })

            # 最近事件
            try:
                from zenskill.core.skill_dao import SkillDAO
                events = SkillDAO.get_events("zenskill-core", limit=5)
                vm.total_events = SkillDAO.get_event_count("zenskill-core")
                for e in events:
                    content = str(e.get("content", ""))[:60]
                    if content:
                        vm.recent_events.append(content)
            except Exception:
                pass

            vm.level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"

        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        lines = []
        # 统计卡片
        fields = [
            ("已安装技能", str(self.skill_count)),
            ("活跃技能", str(self.active_skills)),
            ("总事件", str(self.total_events)),
        ]
        for lv in ("NOVICE", "APPRENTICE", "JOURNEYMAN", "EXPERT", "MASTER"):
            if self.level_distribution.get(lv):
                icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                        "EXPERT": "⭐", "MASTER": "👑"}.get(lv, "")
                fields.append((f"  {icon} {lv}", str(self.level_distribution[lv])))

        lines.append(r.card(
            type('s', (), {'title': '技能概览', 'icon': 'dashboard',
                           'fields': fields, 'footer': '', 'color': 'primary'})()
        ))

        # Top 技能
        if self.top_skills:
            headers = ["技能", "等级", "分类", "调用"]
            rows = []
            for s in self.top_skills:
                icon_lv = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                           "EXPERT": "⭐", "MASTER": "👑"}.get(s["level"], "")
                rows.append([f"{s['icon']} {s['name']}",
                            f"{icon_lv} {s['level']}",
                            s["category"], str(s["usage"])])
            lines.append(r.table(
                type('s', (), {'headers': headers, 'rows': rows, 'title': 'Top 技能', 'color': 'primary'})()
            ))

        # 最近事件
        if self.recent_events:
            lines.append(r._color_ansi("#4A90D9", "  📋 最近活动"))
            for evt in self.recent_events[:5]:
                lines.append(f"  · {evt}")

        return "\n".join(lines)

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ 加载失败: {self.error}[/red]"

        from zenskill.render import RichRenderer
        r = RichRenderer()
        lines = []

        # 统计卡片
        fields = [
            ("已安装技能", str(self.skill_count)),
            ("活跃技能", str(self.active_skills)),
            ("总事件", str(self.total_events)),
        ]
        for lv in ("NOVICE", "APPRENTICE", "JOURNEYMAN", "EXPERT", "MASTER"):
            if self.level_distribution.get(lv):
                icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                        "EXPERT": "⭐", "MASTER": "👑"}.get(lv, "")
                fields.append((f"  {icon} {lv}", str(self.level_distribution[lv])))

        card_spec = type('s', (), {'title': '技能概览', 'icon': 'dashboard',
                                    'fields': fields, 'footer': '', 'color': 'primary'})()
        lines.append(r.card(card_spec))

        # Top 5 表格
        if self.top_skills:
            headers = ["技能", "等级", "分类", "调用"]
            rows = []
            for s in self.top_skills:
                icon_lv = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                           "EXPERT": "⭐", "MASTER": "👑"}.get(s["level"], "")
                rows.append([f"{s['icon']} {s['name']}",
                            f"{icon_lv} {s['level']}",
                            s["category"], str(s["usage"])])
            lines.append(r.table(
                type('s', (), {'headers': headers, 'rows': rows, 'title': 'Top 技能', 'color': 'primary'})()
            ))

        # 最近事件
        if self.recent_events:
            lines.append("[bold blue]📋 最近活动[/bold blue]")
            for evt in self.recent_events[:5]:
                lines.append(f"  · {evt}")

        return "\n".join(lines)
