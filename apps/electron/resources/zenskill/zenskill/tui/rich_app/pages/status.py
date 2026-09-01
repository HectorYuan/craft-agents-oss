"""统一状态总览页面 -- /status 命令。

一页展示所有核心状态：技能/GTD/LLM/记忆/系统。
"""

from __future__ import annotations

import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class StatusPage:
    """统一状态总览页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染状态总览。"""
        sections = []

        # 1. 系统信息
        sections.append(self._render_system())

        # 2. 技能状态
        sections.append(self._render_skills())

        # 3. GTD 状态
        sections.append(self._render_gtd())

        # 4. LLM 状态
        sections.append(self._render_llm())

        # 5. 记忆状态
        sections.append(self._render_memory())

        # 渲染所有区域
        for section in sections:
            if section:
                self.console.print(section)

    def _render_system(self):
        """系统信息。"""
        try:
            from zenskill import __version__
            ver = __version__
        except Exception:
            ver = "dev"

        summary = self.data.get_dashboard_summary()
        today_usage = summary.get("today_usage", 0)
        active_skills = summary.get("active_skills", 0)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        uptime = time.monotonic()

        return Panel(
            f"📦 v{ver}  │  🕐 {now}  │  📊 今日 {today_usage} 次  │  🎯 {active_skills} 技能",
            title="💻 系统状态",
            border_style="cyan",
        )

    def _render_skills(self):
        """技能状态。"""
        skills = self.data.list_skills()
        if not skills:
            return None

        top = skills[:3]
        levels = {}
        for s in skills:
            level = s.get("level", "NOVICE")
            levels[level] = levels.get(level, 0) + 1

        level_str = ", ".join(f"{v} {k}" for k, v in sorted(levels.items(), key=lambda x: -x[1]))
        top_str = ", ".join(s.get("skill_id", "")[:15] for s in top)

        return Panel(
            f"总计: {len(skills)} 个  │  分布: {level_str}\n"
            f"热门: {top_str}",
            title="🎯 技能",
            border_style="green",
        )

    def _render_gtd(self):
        """GTD 状态。"""
        try:
            from zenskill.core.database import db
            rows = db.execute("SELECT count(*) as c FROM gtd_actions WHERE status != 'done'")
            actions = rows[0]["c"] if rows else 0
            rows = db.execute("SELECT count(*) as c FROM gtd_projects WHERE status = 'active'")
            projects = rows[0]["c"] if rows else 0
        except Exception:
            actions = 0
            projects = 0

        if actions == 0 and projects == 0:
            return None

        return Panel(
            f"📋 {actions} 待办  │  📁 {projects} 活跃项目",
            title="✅ GTD",
            border_style="yellow",
        )

    def _render_llm(self):
        """LLM 状态。"""
        try:
            from zenskill.core.llm_provider import get_llm_provider
            provider = get_llm_provider()
            model = provider.get_model_name() if provider else "未配置"
            available = provider is not None
        except Exception:
            model = "未配置"
            available = False

        status = "[green]● 在线[/green]" if available else "[red]● 离线[/red]"

        return Panel(
            f"状态: {status}  │  模型: {model}",
            title="🤖 LLM",
            border_style="blue",
        )

    def _render_memory(self):
        """记忆状态。"""
        try:
            from zenskill.core.memory.memory_store import MemoryStore
            store = MemoryStore()
            entries = store.list_all(limit=1000)
            total = len(entries)
        except Exception:
            total = 0

        if total == 0:
            return None

        return Panel(
            f"📚 {total} 条记忆",
            title="🧠 记忆",
            border_style="magenta",
        )
